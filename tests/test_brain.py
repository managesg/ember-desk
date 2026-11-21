"""Company Brain tests (stdlib unittest). Run: python -m unittest discover tests   (also run by: python server.py --selftest)
Everything uses temp folders, a mocked IMAP server and the offline mock engine: no network, no real mailbox, no cost."""
import warnings; warnings.simplefilter("ignore", ResourceWarning)  # legacy one-liner file reads in server.py
import glob, hashlib, http.client, io, json, os, shutil, sqlite3, stat, sys, tempfile, threading, time, unittest, uuid, zipfile
from contextlib import redirect_stdout, redirect_stderr
from http.server import ThreadingHTTPServer
from functools import partial
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import brain, fake_imap, server

def make_docx(path, paras):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paras)
    with zipfile.ZipFile(path, "w") as z: z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % body)
def make_xlsx(path, sheet, rows):  # rows of strings/numbers; strings go through sharedStrings like Excel does
    sst, xml_rows = [], ""
    for r, row in enumerate(rows, 1):
        cs = ""
        for c, v in enumerate(row):
            ref = "%s%d" % ("ABCDEF"[c], r)
            if isinstance(v, str): sst.append(v); cs += '<c r="%s" t="s"><v>%d</v></c>' % (ref, len(sst) - 1)
            else: cs += '<c r="%s"><v>%s</v></c>' % (ref, v)
        xml_rows += '<row r="%d">%s</row>' % (r, cs)
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook %s xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>' % (ns, sheet))
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", "<sst %s>%s</sst>" % (ns, "".join("<si><t>%s</t></si>" % s for s in sst)))
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet %s><sheetData>%s</sheetData></worksheet>" % (ns, xml_rows))

class Base(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)  # legacy one-line file reads in server.py
        self.tmp = tempfile.mkdtemp(); self.old = (brain.HOME, os.environ.get("EMBER_SECRETS_DIR"), os.environ.get("EMBER_NO_KEYRING"), brain.ITER)
        brain.HOME = os.path.join(self.tmp, "home"); os.makedirs(brain.HOME)
        os.environ["EMBER_SECRETS_DIR"] = os.path.join(self.tmp, "secrets"); os.environ["EMBER_NO_KEYRING"] = "1"; brain.ITER = 1000
        brain.TOK.clear(); brain.FAIL.update(n=0, until=0.0); brain.RUNS.clear()
        self.docs = os.path.join(self.tmp, "company"); os.makedirs(self.docs)
    def tearDown(self):
        brain.HOME, sd, nk, brain.ITER = self.old
        for k, v in (("EMBER_SECRETS_DIR", sd), ("EMBER_NO_KEYRING", nk)):
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)
    def w(self, rel, text="x", base=None):
        p = os.path.join(base or self.docs, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w", encoding="utf8").write(text); return p

class Auth(Base):
    def test_pin_hashing_and_lockout(self):
        brain.ITER = 310000; h = brain.hash_pin("correct horse"); self.assertTrue(h.startswith("pbkdf2_sha256$310000$")); self.assertNotIn("correct horse", h)
        self.assertTrue(brain.check_pin("correct horse", h)); self.assertFalse(brain.check_pin("wrong", h)); self.assertNotEqual(h, brain.hash_pin("correct horse"))  # salted
        brain.ITER = 1000; tok = brain.set_pin("123456"); self.assertTrue(brain.is_owner({"X-Owner-Token": tok})); self.assertFalse(brain.is_owner({"X-Owner-Token": "nope"}))
        self.assertNotIn("123456", open(os.path.join(brain.HOME, "brain", "state.json")).read())
        with self.assertRaises(PermissionError): brain.set_pin("abcdef")  # cannot be re-set without the owner
        for _ in range(5):
            with self.assertRaises(PermissionError): brain.login("bad")
        with self.assertRaises(ConnectionRefusedError): brain.login("123456")  # locked out even for the right PIN

    def test_admin_token_and_owner_only_api(self):
        os.environ["EMBER_ADMIN_TOKEN"] = "adm-" + uuid.uuid4().hex
        try:
            code, _ = brain.handle("POST", "/api/brain/index", {}, {}, {}); self.assertEqual(code, 401)
            code, _ = brain.handle("POST", "/api/brain/index", {}, {}, {"Authorization": "Bearer wrong"}); self.assertEqual(code, 401)
            code, _ = brain.handle("POST", "/api/brain/index", {}, {}, {"Authorization": "Bearer " + os.environ["EMBER_ADMIN_TOKEN"]}); self.assertEqual(code, 200)
        finally: os.environ.pop("EMBER_ADMIN_TOKEN")

class Folders(Base):
    def test_allowlist_and_traversal(self):
        self.w("a.txt", "alpha"); self.w("sub/b.md", "beta"); self.w(".hidden.txt", "no"); self.w("sub/.git/c.txt", "no"); self.w("passwords.txt", "no"); self.w("pic.jpg", "no")
        outside = self.w("outside.txt", "secret outside", base=os.path.join(self.tmp, "elsewhere")); f = brain.add_folder(self.docs, "docs")
        self.assertTrue(brain.in_allowlist(os.path.join(self.docs, "a.txt"))); self.assertTrue(brain.in_allowlist(os.path.join(self.docs, "sub", "b.md")))
        self.assertFalse(brain.in_allowlist(outside)); self.assertFalse(brain.in_allowlist(os.path.join(self.docs, "..", "elsewhere", "outside.txt")))
        self.assertFalse(brain.in_allowlist(os.path.join(self.docs, ".hidden.txt"))); self.assertFalse(brain.in_allowlist(os.path.join(self.docs, "sub", ".git", "c.txt")))
        self.assertFalse(brain.in_allowlist(os.path.join(self.docs, "passwords.txt"))); self.assertFalse(brain.in_allowlist(os.path.join(self.docs, "pic.jpg")))
        for bad in ("../x", self.docs + os.sep + ".." + os.sep + "elsewhere", os.path.abspath(os.sep), os.path.expanduser("~"), os.path.join(self.docs, "nope"), os.path.join(self.docs, "a.txt"), ""):
            with self.assertRaises(ValueError, msg=bad): brain.add_folder(bad)
        with self.assertRaises(ValueError): brain.add_folder(self.docs)  # duplicate
        st = brain.index_all(); self.assertEqual(st["files"], 2); names = [r[0] for r in sqlite3.connect(os.path.join(brain.HOME, "brain", "index.sqlite")).execute("select name from docs")]
        self.assertEqual(sorted(names), ["docs/a.txt", "docs/sub/b.md"])

    def test_symlink_out_of_allowlist(self):
        outside = self.w("o.txt", "TOPSECRETWORD", base=os.path.join(self.tmp, "elsewhere")); link = os.path.join(self.docs, "link.txt")
        try: os.symlink(outside, link)
        except (OSError, NotImplementedError): self.skipTest("symlinks need privileges on this OS")
        brain.add_folder(self.docs, "docs"); self.assertFalse(brain.in_allowlist(link)); brain.index_all(); self.assertEqual(brain.search("TOPSECRETWORD"), [])
        d = os.path.join(self.tmp, "dirlink")
        try: os.symlink(os.path.dirname(outside), d, target_is_directory=True)
        except (OSError, NotImplementedError): return
        with self.assertRaises(ValueError): brain.add_folder(d)

    def test_parsers(self):
        make_docx(os.path.join(self.docs, "contract.docx"), ["Supplier agreement", "Payment terms are net 30 days."]); make_xlsx(os.path.join(self.docs, "prices.xlsx"), "Prices", [["Item", "Price"], ["Cold brew", 5], ["Espresso", 3.5]])
        self.assertEqual(brain.read_docx(os.path.join(self.docs, "contract.docx")), ["Supplier agreement", "Payment terms are net 30 days."])
        self.assertEqual(brain.read_xlsx(os.path.join(self.docs, "prices.xlsx")), ["Prices!R1: Item | Price", "Prices!R2: Cold brew | 5", "Prices!R3: Espresso | 3.5"])
        self.w("sales.csv", "month,units\nOct,120\n"); brain.add_folder(self.docs, "docs"); st = brain.index_all(); self.assertEqual(st["files"], 3)
        self.assertEqual(brain.index_all()["unchanged"], 3)  # incremental
        os.remove(os.path.join(self.docs, "sales.csv")); self.assertEqual(brain.index_all()["removed"], 1)

class Retrieval(Base):
    def test_fts_citations_and_empty_brain(self):
        self.assertEqual(brain.context("raise cold brew prices?"), ""); self.assertEqual(server.pack({"question": "raise cold brew prices?"}), server.pack())  # demo prompt is untouched
        brain.add_note("Pricing policy", "We never raise cold brew prices above 5 dollars.\nPrice changes need two weeks notice.")
        make_docx(os.path.join(self.docs, "contract.docx"), ["Supplier agreement", "Payment terms are net 30 days."]); brain.add_folder(self.docs, "docs"); brain.index_all()
        ctx = brain.context('Should we raise "cold-brew" prices?'); self.assertIn("=== FILE: brain/pricing-policy.md ===", ctx); self.assertIn("3| We never raise cold brew prices", ctx)
        self.assertIn("=== FILE: docs/contract.docx ===", brain.context("what are our supplier payment terms?"))
        for q in ('raise "cold-brew" prices?', "AND OR NOT", '"""', "a", "x" * 500, "price*", "(", "NEAR(a b)", "col:umn"): brain.context(q)  # query sanitising never raises
        ok = server.verify([{"file": "brain/pricing-policy.md", "lines": "3-3", "quote": "We never raise cold brew prices above 5 dollars"}, {"file": "brain/pricing-policy.md", "lines": "3", "quote": "invented words zzz"}])
        self.assertTrue(ok[0]["verified"]); self.assertEqual(ok[0]["kind"], "brain"); self.assertFalse(ok[1]["verified"])
        self.assertTrue(server.verify([{"file": "docs/contract.docx", "lines": "2", "quote": "Payment terms are net 30 days"}])[0]["verified"])

    def test_demo_cache_keys_unchanged(self):  # proves saved councils still replay for free: every cache file's name is still the hash of its own request
        n = 0
        for f in glob.glob(os.path.join(ROOT, "cache", "*.json")):
            d = json.load(open(f, encoding="utf8")); h = hashlib.sha256(("meta/muse-ember" + d["mode"] + json.dumps(d["payload"], sort_keys=True) + server.pack(d["payload"])).encode()).hexdigest()
            self.assertEqual(os.path.basename(f), h + ".json"); n += 1
        self.assertGreater(n, 0)

class Email(Base):
    def setUp(self):
        super().setUp(); self.pw = "S3ntinel-" + uuid.uuid4().hex; self.real = fake_imap.install(self.pw); sys.modules["smtplib"] = None  # any `import smtplib` now raises
    def tearDown(self): sys.modules.pop("smtplib", None); fake_imap.uninstall(self.real); super().tearDown()
    def connect(self, mode="read"): return brain.connect_email("imap.gmail.com", "owner@example.com", self.pw, mode=mode)
    def test_read_only_ingest_and_never_smtp(self):
        self.connect(); r = brain.ingest_email(30); self.assertEqual(r["emails"], 3)
        calls = fake_imap.FakeIMAP.calls; self.assertTrue(all(c[2] is True for c in calls if c[0] == "select"))  # selected read-only
        self.assertTrue(all("PEEK" in c[1] for c in calls if c[0] == "fetch")); self.assertFalse([c for c in calls if c[0] == "append"])
        with self.assertRaises(PermissionError): brain.save_draft("a@b.example", "Re: hi", "hello")  # read-only mailbox cannot even draft
        self.assertFalse([c for c in calls if c[0] == "append"])
        ctx = brain.context("invoice 4471 due"); self.assertIn("=== FILE: email:2026-11-16 Invoice 4471 due Friday ===", ctx)
        self.assertTrue(server.verify([{"file": "email:2026-11-16 Invoice 4471 due Friday", "lines": "5", "quote": "Invoice 4471 for $812 is due Friday"}])[0]["verified"])
        for src in ("brain.py", "server.py", "mock_llm.py"): self.assertNotIn("smtplib", open(os.path.join(ROOT, src), encoding="utf8").read().lower())
        self.assertNotIn("sendmail", open(os.path.join(ROOT, "brain.py"), encoding="utf8").read())

    def test_draft_mode_appends_to_drafts_only(self):
        self.connect("draft"); out = brain.save_draft("dana@beanco.example", "Re: Invoice 4471", "Thanks, paying Friday.\nAlex", "<abc@mail>")
        self.assertEqual(out, {"saved_to": "[Gmail]/Drafts", "sent": False})  # found through the \Drafts special-use flag, not the English name
        ap = [c for c in fake_imap.FakeIMAP.calls if c[0] == "append"]; self.assertEqual(len(ap), 1); self.assertEqual(ap[0][2], "\\Draft"); self.assertIn(b"never sent", ap[0][3]); self.assertIn(b"To: dana@beanco.example", ap[0][3])
        self.assertFalse([c for c in fake_imap.FakeIMAP.calls if c[0] in ("send", "sendmail", "store", "copy", "delete", "expunge")])
        for bad in (("a@b.example\r\nBcc: x@y.example", "s", "b"), ("not an address", "s", "b"), ("a@b.example", "", "b"), ("a@b.example", "s\nBcc: x@y.example", "b")):
            with self.assertRaises(ValueError): brain.save_draft(*bad)
        self.assertEqual(len([c for c in fake_imap.FakeIMAP.calls if c[0] == "append"]), 1)

    def test_bad_login_and_disconnect(self):
        with self.assertRaises(ValueError) as e: brain.connect_email("imap.gmail.com", "owner@example.com", "wrong-" + uuid.uuid4().hex)
        self.assertIn("app password", str(e.exception)); self.assertIsNone(brain.cfg()["email"]); self.assertEqual(brain.secret_get("email"), "")
        self.connect(); brain.ingest_email(); self.assertEqual(brain.counts()["emails"], 3); brain.disconnect_email()
        self.assertEqual(brain.counts()["emails"], 0); self.assertEqual(brain.secret_get("email"), ""); self.assertIsNone(brain.cfg()["email"])

    def test_secrets_never_in_logs_index_or_model_context(self):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            self.connect("draft"); brain.ingest_email(); brain.save_draft("dana@beanco.example", "Re: x", "body text here")
            replies = [brain.handle("GET", "/api/brain/status", {}, {}, {}), brain.handle("POST", "/api/brain/email/connect", {}, {"host": "imap.gmail.com", "user": "owner@example.com", "password": "bad-" + uuid.uuid4().hex}, {"X-Owner-Token": brain.set_pin("123456")})]
            ctx = brain.context("invoice")
        blob = buf.getvalue() + json.dumps(replies) + ctx + json.dumps(brain.status(True)) + json.dumps(fake_imap.FakeIMAP.calls, default=str)
        self.assertNotIn(self.pw, blob)
        for root, _, files in os.walk(brain.HOME):  # every file the app wrote: audit log, state, index, notes
            for fn in files: self.assertNotIn(self.pw.encode(), open(os.path.join(root, fn), "rb").read(), fn)
        sf = os.path.join(os.environ["EMBER_SECRETS_DIR"], "secrets.json"); self.assertIn(self.pw, open(sf).read())  # it lives only here, outside the repo/home
        if os.name != "nt": self.assertEqual(stat.S_IMODE(os.stat(sf).st_mode), 0o600)
        audit = brain.rd(os.path.join(brain.HOME, "logs", "brain_audit.jsonl"))
        for ev in ("source_added", "email_ingest", "draft_saved"): self.assertIn(ev, audit)
        self.assertNotIn("body text here", audit); self.assertNotIn("Invoice 4471 for", audit)  # no contents in the audit log

class Actions(Base):
    def setUp(self):
        super().setUp(); self.mark = os.path.join(self.tmp, "ran.txt"); self.script = self.w("report.py", "import sys; open(sys.argv[1], 'w').write('done')", base=self.tmp)
    def define(self): return brain.define_action("Run monthly report", [sys.executable, self.script, self.mark])
    def test_unknown_and_unapproved_actions_never_run(self):
        with self.assertRaises(ValueError): brain.request_action("a-nope")
        with self.assertRaises(ValueError): brain.decide_action("r-nope", True)
        a = self.define(); req = brain.request_action(a["id"]); self.assertIn(self.script, req["will_run"]); time.sleep(0.2); self.assertFalse(os.path.exists(self.mark))  # a request alone runs nothing
        brain.decide_action(req["run"], False); self.assertFalse(os.path.exists(self.mark))
        with self.assertRaises(ValueError): brain.decide_action(req["run"], True)  # a denied request cannot be approved later
        req = brain.request_action(a["id"]); out = brain.decide_action(req["run"], True); self.assertEqual(out["exit_code"], 0); self.assertEqual(open(self.mark).read(), "done")
        with self.assertRaises(ValueError): brain.decide_action(req["run"], True)  # single use
        ev = [json.loads(l)["event"] for l in brain.rd(os.path.join(brain.HOME, "logs", "brain_audit.jsonl")).splitlines()]
        for e in ("action_requested", "action_denied", "action_approved", "action_run"): self.assertIn(e, ev)
    def test_definition_changed_after_request_is_refused(self):
        a = self.define(); req = brain.request_action(a["id"]); c = brain.cfg(); c["actions"][0]["argv"][-1] = self.mark + "2"; brain.save_cfg(c)
        with self.assertRaises(ValueError): brain.decide_action(req["run"], True)
        self.assertFalse(os.path.exists(self.mark + "2"))
    def test_no_shells_no_free_form(self):
        shells = [["cmd", "/c", "dir"], ["powershell", "-Command", "ls"], ["bash", "-c", "ls"], [sys.executable, "-c", "print(1)"], ["nonexistent-program-xyz"], []]
        if os.name == "nt": bat = self.w("x.bat", "echo hi", base=self.tmp); shells.append([bat])
        for argv in shells:
            with self.assertRaises(ValueError, msg=argv): brain.define_action("bad %s" % uuid.uuid4().hex[:4], argv)
    def test_advisors_only_suggest(self):
        a = self.define(); self.assertEqual(brain.suggested(["Run monthly report", "Format disk", 5]), [{"id": a["id"], "name": "Run monthly report"}]); self.assertIn("Run monthly report", brain.verdict_extra())
        self.assertFalse(os.path.exists(self.mark))

class Redaction(Base):
    def test_redaction(self):
        t = "Mail dana@beanco.example or call +44 20 7946 0958, (555) 123-4567, 555-123-4567. Card 4111 1111 1111 1111. IBAN GB82 WEST 1234 5698 7654 32. Pay DE89370400440532013000."
        r = brain.redact(t); self.assertEqual(r.count("[email]"), 1); self.assertEqual(r.count("[phone]"), 3); self.assertIn("[card]", r); self.assertEqual(r.count("[iban]"), 2)
        for leak in ("dana@", "7946", "4111", "WEST 1234", "0440532013000"): self.assertNotIn(leak, r)
        keep = "Cold brew $5.00, espresso $3.50. 2026-11-09. Invoice 4471 due, 1234567 units, 12.50 13.00 14.00, rent 2,400, 120 130 4500."
        self.assertEqual(brain.redact(keep), keep)  # prices, dates and numbers survive
    def test_sample_data_only_loses_emails(self):
        packed = server.pack(); red = brain.redact(packed); a, b = packed.split("\n"), red.split("\n"); self.assertEqual(len(a), len(b))
        diff = [(x, y) for x, y in zip(a, b) if x != y]; self.assertTrue(all("@" in x and "[email]" in y for x, y in diff), diff); self.assertLessEqual(len(diff), 3)
    def test_cloud_calls_are_redacted_local_are_not(self):
        sent = []; old = (server.api, server.PROV, server.BASE, server.OPENROUTER, server.LOG, server.MOCK)
        server.api = lambda path, body=None: (sent.append(json.dumps(body)), {"id": "g", "choices": [{"message": {"content": "{}"}}], "usage": {}})[1]
        server.LOG = os.path.join(self.tmp, "l.jsonl"); server.MOCK = False
        try:
            msg = lambda t: [{"role": "user", "content": t}]; server.use("openrouter")
            server.call(msg("write to dana@beanco.example"), "test"); self.assertNotIn("dana@", sent[-1]); self.assertNotIn("provider", json.loads(sent[-1]))  # plain demo: only redaction applies
            brain.set_pin("123456"); server.call(msg("x"), "test"); self.assertEqual(json.loads(sent[-1])["provider"], {"data_collection": "deny"})  # company data connected: providers must not store prompts
            c = brain.cfg(); c["privacy"].update(redact=False, deny_collection=False); brain.save_cfg(c); server.call(msg("write to dana@beanco.example"), "test"); self.assertIn("dana@", sent[-1]); self.assertNotIn("provider", json.loads(sent[-1]))
            c["privacy"].update(redact=True); brain.save_cfg(c); server.use("local"); server.call(msg("write to dana@beanco.example"), "test"); self.assertIn("dana@", sent[-1])  # a local engine keeps the data on this PC
        finally: server.api, server.MOCK, server.LOG = old[0], old[5], old[4]; server.use(old[1])

class Notes(Base):
    def test_proposed_notes_need_approval(self):
        ids = brain.propose([{"title": "Decision: price", "text": "Cold brew stays at $5."}, {"title": "", "text": "x"}], "s1"); self.assertEqual(len(ids), 1)
        self.assertEqual(brain.counts()["notes"], 0); self.assertFalse(os.path.exists(os.path.join(brain.HOME, "brain", "decision-price.md")))  # not memory yet
        brain.decide_note(ids[0], True); self.assertTrue(os.path.exists(os.path.join(brain.HOME, "brain", "decision-price.md"))); self.assertEqual(brain.counts()["notes"], 1); self.assertEqual(brain.pending(), [])
        i2 = brain.propose([{"title": "Other", "text": "y"}]); brain.decide_note(i2[0], False); self.assertEqual(brain.counts()["notes"], 1)

class EndToEnd(Base):
    def test_http_guard_and_mock_council(self):
        old = (server.MOCK, server.MODEL, server.LOG, server.HIST, server.LOGS); server.MOCK = True; server.MODEL = "mock-llm"; server.LOG = os.path.join(self.tmp, "mock.jsonl"); server.HIST = os.path.join(self.tmp, "hist"); server.LOGS = os.path.join(self.tmp, "council.jsonl")
        brain.add_note("Pricing policy", "We never raise cold brew prices above 5 dollars without two weeks notice."); self.w("report.py", "pass", base=self.tmp); brain.define_action("Run monthly report", [sys.executable, os.path.join(self.tmp, "report.py")])
        srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.H, directory=server.PUB)); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
        def post(path, body, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", port); c.request("POST", path, json.dumps(body), {"Content-Type": "application/json", **(headers or {})}); r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")
        try:
            c = http.client.HTTPConnection("127.0.0.1", port); c.request("GET", "/api/brain/status", headers={"Host": "evil.example:80"}); self.assertEqual(c.getresponse().status, 403)  # DNS rebinding
            self.assertEqual(post("/api/brain/setup", {"pin": "123456"}, {"Origin": "http://evil.example"})[0], 403)  # cross-site POST
            code, j = post("/api/brain/setup", {"pin": "123456"}); self.assertEqual(code, 200); tok = j["token"]
            self.assertEqual(post("/api/brain/index", {})[0], 401); self.assertEqual(post("/api/brain/index", {}, {"X-Owner-Token": tok})[0], 200)
            seats, _, default = server.seats_for("restaurant"); code, j = post("/api/council", {"prompt": "Should we raise cold brew prices again?", "industry": "restaurant", "seats": seats, "seated": default[:3], "mode": "quick", "proposal": {"title": "Cold brew price", "options": [{"id": "A", "label": "Raise"}, {"id": "B", "label": "Keep"}]}})
            self.assertEqual(code, 200); s = server.SESS[j["id"]]
            for _ in range(100):
                if s["status"] != "running": break
                time.sleep(0.1)
            self.assertEqual(s["status"], "done", s["events"][-1]); ev = next(e for e in s["events"] if e["type"] == "verdict"); v = ev["verdict"]
            self.assertEqual(v["suggested_actions"][0]["name"], "Run monthly report"); self.assertFalse(os.path.exists(os.path.join(self.tmp, "ran")))  # suggested, never run by the council
            cites = [q for e in s["events"] if e["type"] == "seat_done" for q in e["quotes"]]; self.assertTrue(any(q["kind"] == "brain" and q["verified"] for q in cites), cites)  # cited from the brain note, checked against its real line
            self.assertEqual(len(brain.pending()), 1); self.assertEqual(brain.counts()["notes"], 1)  # the proposal waits for approval
            self.assertEqual(os.listdir(os.path.join(ROOT, "cache")).__len__(), len(glob.glob(os.path.join(ROOT, "cache", "*.json"))))  # mock never writes the tracked cache
        finally: srv.shutdown(); server.MOCK, server.MODEL, server.LOG, server.HIST, server.LOGS = old

if __name__ == "__main__": unittest.main()
