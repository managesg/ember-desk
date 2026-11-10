"""Ember Council: stdlib-only server. A role-based advisor council for local businesses that debates the owner's question
from the owner's own files (Roast Room table UI, MIT). Default engine: Muse Ember via OpenRouter; any OpenAI-compatible
endpoint works (Ollama, LM Studio, llama.cpp) via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY."""
import hashlib, json, os, sys, time, glob, re, subprocess, threading, uuid, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
ROOT = os.path.dirname(os.path.abspath(__file__)); PUB = os.path.join(ROOT, "public"); HIST = os.path.join(ROOT, "data", "history")
BASE = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "meta/muse-ember")
OPENROUTER = "openrouter.ai" in BASE  # only OpenRouter gets usage.include / reasoning fields and a cost meter
CAP = float(os.environ.get("BUDGET_CAP", "0.20")); HARD = 0.95  # rebuild cap; whole project (old + new log) must stay under $0.95
CACHE_ONLY = os.environ.get("CACHE_ONLY") == "1"
LOG = os.path.join(ROOT, "proof", "council_log.jsonl"); OLD_LOG = os.path.join(ROOT, "proof", "openrouter_log.jsonl")
CITE = '"citations":[{"file":str,"lines":"a-b","quote":str (exact words copied from that line)}]'
RULES = " Answer ONLY from the owner's files, citing them with the N| line numbers. Never name or imitate real people. Return JSON only: no markdown, no code fences."
SEAT = 'You are the {role} ("{short}") on the advisor council of a {biz} (your focus: {focus}). The question you own: "{owns}". {persona} Tone: {tone} '
SCORES = '"optionScores":{"A":0-10,"B":0-10,...} (one score per option id)'
SYS = {
 "chair": 'You are the Chair of a small-business advisor council. Turn the owner\'s question into a decision with 2-3 options (one may be "keep as is"),'
          ' and pick the 3-5 candidate advisors who should sit (prefer all who clearly own part of it).'
          ' Return {"title":str (<=12 words),"framing":str (<=40 words: the decision and what the files already show),"options":[{"id":"A","label":str (<=8 words)}],'
          '"seated":[{"id":str,"why":str (<=14 words),"weight":1-3 (how much this seat matters here)}]}.' + RULES,
 "open": SEAT + 'Round 1, opening position. Return {"stance":"strong yes"|"conditional yes"|"no"|"strong no","call":str (<=40 words, spoken first person),' + SCORES + ',' + CITE + ' (1-2)}.' + RULES,
 "cruxes": 'You are the Chair. Read the opening positions and name the 1-2 fault lines where the advisors disagree.'
           ' Return {"unanimous":bool,"cruxes":[{"question":str (<=14 words),"sides":[{"position":str (<=10 words),"seats":[seat ids]}]}]}.' + RULES,
 "rebut": SEAT + 'Round 2, the debate. Push back on ONE other advisor by id, using the files. Return {"disagreeWith":seat id,"disagreeLine":str (<=40 words, spoken to them),'
          '"moved":"yes"|"no","stance":"strong yes"|"conditional yes"|"no"|"strong no",' + SCORES + ',' + CITE + ' (1-2)}.' + RULES,
 "draft": 'You are the Chair. Turn the debate into one proposal for a vote. Return {"label":"GO"|"RESHAPE"|"WAIT"|"DON\'T","option":option id,"recommendation":str (<=40 words)}.' + RULES,
 "vote": SEAT + 'Round 3, the vote on the Chair\'s proposal. Return {"vote":"endorse"|"amend"|"dissent","oneLine":str (<=30 words, spoken),"amendment":str (<=20 words or ""),' + SCORES + ',' + CITE + ' (1)}.' + RULES,
 "verdict": 'You are the Chair. Write the council\'s verdict for the owner. Return {"label":"GO"|"RESHAPE"|"WAIT"|"DON\'T","recommended":option id,"call":str (<=45 words),"confidence":0-10,'
            '"why":[{"seat":seat id,"point":str (<=30 words)}] (3),"minority":{"seat":seat id,"quote":str (<=35 words),"would_have_to_be_true":str (<=25 words)},'
            '"next_steps":[{"when":"Today"|"This week"|"In 30 days","action":str (<=25 words)}] (3),"kill_criteria":str (<=25 words),"fights":[{"crux":str,"story":str (<=30 words)}],'
            '"conditions":[str],"cheapest_test":str (<=25 words),"revisit":str (<=15 words),' + CITE + ' (2-4)}.' + RULES,
 "learn": 'Turn this council decision into a 10-minute lesson that teaches the owner to use AI on their own files for this kind of decision.'
          ' Return {"title":str,"why":str (<=35 words),"steps":[4 str, each <=25 words, timed, e.g. "2 min: ..."],"prompt_to_copy":str (a reusable prompt with [BRACKETED] blanks the owner fills, <=90 words),"try_next":str (<=25 words)}.' + RULES,
}
MAXTOK = {"chair": 3000, "open": 3000, "cruxes": 3000, "rebut": 3000, "draft": 2500, "vote": 2500, "verdict": 5000, "learn": 4000}  # reasoning tokens count against max_tokens

def key():
    if not OPENROUTER: return os.environ.get("LLM_API_KEY") or "local"
    k = os.environ.get("OPENROUTER_API_KEY")  # a machine-wide LLM_API_KEY often belongs to another provider, so it is the last resort here
    if not k:
        try: k = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"], capture_output=True, text=True).stdout.strip()
        except Exception: k = ""
    return k or os.environ.get("LLM_API_KEY") or ""
def data_files(): return [p for p in sorted(glob.glob(os.path.join(ROOT, "data", "*"))) if os.path.isfile(p)]
def pack():
    out = []
    for p in data_files():
        out.append("=== FILE: %s ===" % os.path.basename(p))
        out += ["%d| %s" % (i, l) for i, l in enumerate(open(p, encoding="utf8").read().splitlines(), 1)]
    return "\n".join(out)
def spent(path=None):
    path = path or LOG
    return sum(json.loads(l).get("cost") or 0 for l in open(path)) if os.path.exists(path) else 0.0
def parse(t):
    t = (t or "").strip()
    if t.startswith("```"): t = t.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)
def api(path, body=None):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=180))
LOCK = threading.Lock()
def call(messages, mode):
    if spent() >= CAP or spent() + spent(OLD_LOG) >= HARD: raise RuntimeError("budget guard: spent $%.4f >= cap $%.2f" % (spent(), CAP))
    body = {"model": MODEL, "messages": messages, "temperature": 0.3, "max_tokens": MAXTOK[mode]}
    if OPENROUTER: body.update(reasoning={"effort": "low"}, usage={"include": True})
    t0 = time.time()
    for attempt in (0, 1, 2):
        try: r = api("/chat/completions", body); break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503) or attempt == 2: raise
            time.sleep(3)
    u = r.get("usage") or {}
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "generation_id": r.get("id"), "model": r.get("model") or MODEL, "mode": mode,
           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"), "cost": u.get("cost") if OPENROUTER else 0,
           "latency_s": round(time.time() - t0, 1), "cache_hit": False, "provider": "openrouter" if OPENROUTER else "local"}
    with LOCK:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(json.dumps(rec) + "\n")
    return r["choices"][0]["message"].get("content"), rec

clip = lambda s, n=300: str(s if s is not None else "")[:n]  # trust boundary: browser-supplied text is length-capped before it reaches the prompt
def seat_sys(mode, p):
    a = p.get("seat") or {}; s = SYS[mode]  # str.replace, not .format: the JSON schema in the prompt is full of braces
    for k, v in dict(role=clip(a.get("role"), 80), short=clip(a.get("short"), 40), biz=clip(p.get("industry"), 60), focus=clip(a.get("focus"), 120),
                     owns=clip(a.get("owns"), 160), persona=clip(a.get("persona"), 400), tone=clip(p.get("tone"), 120)).items(): s = s.replace("{%s}" % k, v)
    return s
def messages(mode, p):
    q = "=== QUESTION ===\n" + clip(p.get("question"), 600)
    opts = "\n=== OPTIONS ===\n" + "\n".join("%s: %s" % (clip(o.get("id"), 3), clip(o.get("label"), 80)) for o in (p.get("options") or [])[:4])
    lines = lambda k: "\n".join("%s (id=%s): %s" % (clip(t.get("short"), 40), clip(t.get("seat"), 40), clip(t.get("line"), 400)) for t in (p.get(k) or [])[:9])
    if mode == "chair":
        cands = "\n".join("- id=%s | %s | owns: %s" % (clip(a.get("id"), 40), clip(a.get("role"), 80), clip(a.get("owns"), 160)) for a in (p.get("advisors") or [])[:12])
        return SYS["chair"], q + "\n=== BUSINESS TYPE ===\n" + clip(p.get("industry"), 60) + "\n=== CANDIDATE ADVISORS ===\n" + cands
    if mode == "open": return seat_sys(mode, p), q + opts
    if mode == "cruxes": return SYS[mode], q + opts + "\n=== OPENINGS ===\n" + lines("openings")
    if mode == "rebut": return seat_sys(mode, p), q + opts + "\n=== OPENINGS ===\n" + lines("openings") + "\n=== FAULT LINES ===\n" + clip(p.get("cruxes"), 600)
    if mode == "draft": return SYS[mode], q + opts + "\n=== DEBATE ===\n" + lines("debate")
    if mode == "vote": return seat_sys(mode, p), q + opts + "\n=== PROPOSAL ===\n" + clip(p.get("proposal"), 400) + "\n=== DEBATE ===\n" + lines("debate")
    if mode == "verdict": return SYS[mode], q + opts + "\n=== THE COUNCIL ===\n" + lines("record") + "\n=== SCORES ===\n" + clip(p.get("scores"), 400)
    if mode == "learn":
        v = p.get("verdict") or {}
        return SYS["learn"], q + "\n=== VERDICT ===\n%s: %s\nNext steps: %s" % (clip(v.get("label"), 10), clip(v.get("call"), 500), clip(v.get("next_steps"), 700))
    raise ValueError("unknown mode")
def ask(mode, payload):
    if mode not in SYS: raise ValueError("unknown mode")
    p = pack(); ck = os.path.join(ROOT, "cache", hashlib.sha256((MODEL + mode + json.dumps(payload, sort_keys=True) + p).encode()).hexdigest() + ".json")
    if os.path.exists(ck):
        c = json.load(open(ck, encoding="utf8")); c["meta"].update(cache_hit=True, cost_this_call=0, total=spent()); return c
    if CACHE_ONLY: raise RuntimeError("cache miss in CACHE_ONLY mode (%s)" % mode)
    sysmsg, user = messages(mode, payload)
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": p + "\n\n" + user}]
    raw, rec = call(msgs, mode); cost = rec["cost"] or 0; parsed = None
    for _ in (0, 1):
        try: parsed = parse(raw); break
        except Exception:  # empty content (reasoning ate the budget) -> plain retry; bad JSON -> ask for JSON
            retry = msgs if not raw else msgs + [{"role": "assistant", "content": raw}, {"role": "user", "content": "Return only valid JSON, nothing else."}]
            raw, rec2 = call(retry, mode); cost += rec2["cost"] or 0
    if parsed is None:
        try: parsed = parse(raw)
        except Exception: pass
    rec["cost_this_call"] = cost; rec["total"] = spent()
    out = {"mode": mode, "payload": payload, "parsed": parsed, "raw": raw, "meta": rec}
    if parsed is not None:
        os.makedirs(os.path.join(ROOT, "cache"), exist_ok=True); json.dump(out, open(ck, "w", encoding="utf8"), indent=1)
    return out
def must(mode, payload):
    d = ask(mode, payload)
    if not isinstance(d.get("parsed"), dict): raise RuntimeError("%s: the model did not return valid JSON" % mode)
    return d["parsed"], d["meta"]

# ---------- citations: check every quote against the cited file ----------
def verify(cites):
    files = {os.path.basename(p): open(p, encoding="utf8").read().splitlines() for p in data_files()}
    out = []
    for c in (cites or [])[:4]:
        if not isinstance(c, dict): continue
        f, q = clip(c.get("file"), 60), clip(c.get("quote"), 200)
        nums = [int(n) for n in re.findall(r"\d+", str(c.get("lines")))][:2] or [0]
        lo, hi = min(nums), max(nums)
        text = " ".join(files.get(f, [])[max(lo - 2, 0):hi + 1]).lower()  # +-1 line of slack
        out.append({"quote": q, "source": "%s L%s" % (f, clip(c.get("lines"), 12)), "verified": bool(q) and (q.lower().strip(' ."') in text)})
    return out

# ---------- the council runner: emits Roast Room's event protocol ----------
SESS = {}
def hist_path(sid): return os.path.join(HIST, re.sub(r"[^\w-]", "", sid) + ".json")
def save(s):
    os.makedirs(HIST, exist_ok=True)
    json.dump({k: s[k] for k in ("id", "title", "mode", "status", "question", "created", "cost", "events", "votes")}, open(hist_path(s["id"]), "w", encoding="utf8"), indent=1)
def emit(s, ev):
    ev.setdefault("at", int(time.time() * 1000)); s["events"].append(ev)
    if ev["type"] in ("setup", "round_done", "verdict", "end", "error"): save(s)
STANCE = {"strong yes": 9, "conditional yes": 6, "no": 3, "strong no": 1}
def seat_text(line, cites):
    return line + ("\n\nFrom your files:\n" + "\n".join('- %s: "%s"%s' % (c["source"], c["quote"], "" if c["verified"] else " (not found at that line)") for c in cites) if cites else "")
def scores_of(cards, weights, options):
    out = {}
    for o in options:
        num = den = 0; parts = []
        for k, c in cards.items():
            v = (c.get("optionScores") or {}).get(o["id"])
            if isinstance(v, (int, float)): w = weights.get(k, {}).get("weight", 1); num += w * v; den += w; parts.append("%sx%s" % (w, v))
        out[o["id"]] = {"score": round(num / den, 1) if den else None, "math": "(" + " + ".join(parts) + ") / %d" % den if den else ""}
    return out
def run_council(s, prop, seats, tone, industry):
    q, mode, opts = s["question"], s["mode"], prop["options"]
    weights = {k: {"weight": int(prop["weights"].get(k, {}).get("weight") or 1), "reason": prop["weights"].get(k, {}).get("reason", "")} for k in seats}
    base = {"question": q, "options": opts, "industry": industry, "tone": tone}
    seat = lambda k: {f: s["seats"][k].get(f) for f in ("role", "short", "focus", "owns", "persona")}
    pool = ThreadPoolExecutor(5)
    def rnd(n, mode_, extra, line_key):
        emit(s, {"type": "round_start", "round": n})
        for k in seats: emit(s, {"type": "seat_start", "seat": k, "round": n})
        futs = {k: pool.submit(must, mode_, {**base, **extra, "seat": seat(k)}) for k in seats}
        cards = {}
        for k in seats:  # emitted in seat order so the room plays them in order
            p, m = futs[k].result(); s["cost"] += m.get("cost_this_call") or 0
            cites = verify(p.get("citations")); cards[k] = p
            if mode_ == "rebut" and p.get("disagreeWith") not in seats: p["disagreeWith"] = None
            emit(s, {"type": "seat_done", "round": n, "seat": k, "parsed": p, "quotes": cites, "text": seat_text(str(p.get(line_key) or ""), cites)})
        emit(s, {"type": "round_done", "round": n, "scores": scores_of(cards, weights, opts)})
        return cards
    try:
        emit(s, {"type": "phase", "phase": "setup", "label": "The Chair is setting the table"})
        emit(s, {"type": "setup", "seats": seats, "options": opts, "weights": weights, "title": prop["title"], "mode": mode,
                 "defs": [{k: v for k, v in s["seats"][k].items() if k != "persona"} for k in seats], "engine": config()["label"]})
        emit(s, {"type": "phase", "phase": "round1", "label": "Round 1: opening positions"})
        short = lambda k: s["seats"][k].get("short")
        r1 = rnd(1, "open", {}, "call")
        openings = [{"seat": k, "short": short(k), "line": "[%s] %s" % (r1[k].get("stance"), r1[k].get("call"))} for k in seats]
        emit(s, {"type": "phase", "phase": "cruxes", "label": "The Chair is finding the fault lines"})
        cx, m = must("cruxes", {"question": q, "options": opts, "openings": openings}); s["cost"] += m.get("cost_this_call") or 0
        for c in cx.get("cruxes") or []:
            for sd in c.get("sides") or []: sd["seats"] = [k for k in (sd.get("seats") or []) if k in seats]
        emit(s, {"type": "cruxes", "cruxes": (cx.get("cruxes") or [])[:2], "unanimous": bool(cx.get("unanimous"))})
        emit(s, {"type": "phase", "phase": "round2", "label": "Round 2: the debate"})
        r2 = rnd(2, "rebut", {"openings": openings, "cruxes": json.dumps(cx.get("cruxes"))}, "disagreeLine")
        debate = openings + [{"seat": k, "short": short(k), "line": "to %s: %s" % (r2[k].get("disagreeWith"), r2[k].get("disagreeLine"))} for k in seats]
        last = r2
        if mode == "full":
            emit(s, {"type": "phase", "phase": "draft", "label": "The Chair is drafting a proposal"})
            dr, m = must("draft", {"question": q, "options": opts, "debate": debate}); s["cost"] += m.get("cost_this_call") or 0
            emit(s, {"type": "draft", "draft": dr})
            emit(s, {"type": "phase", "phase": "round3", "label": "Round 3: the vote"})
            last = rnd(3, "vote", {"proposal": json.dumps(dr), "debate": debate}, "oneLine")
            record = debate + [{"seat": k, "short": short(k), "line": "votes %s: %s" % (last[k].get("vote"), last[k].get("oneLine"))} for k in seats]
        else:
            emit(s, {"type": "phase", "phase": "skip3", "label": "The Chair is scoring the room"}); record = debate
        emit(s, {"type": "phase", "phase": "verdict", "label": "The Chair is writing the verdict"})
        sc = scores_of(last, weights, opts)
        v, m = must("verdict", {"question": q, "options": opts, "record": record, "scores": json.dumps({k: x["score"] for k, x in sc.items()})}); s["cost"] += m.get("cost_this_call") or 0
        v["scores"] = sc
        v["votes"] = {x: sum(1 for k in seats if last[k].get("vote") == x) for x in ("endorse", "amend", "dissent")} if mode == "full" else None
        v["quotes"] = verify(v.get("citations"))
        v["amendments"] = [{"seat": short(k), "amendment": last[k]["amendment"], "adopted": False, "reason": "for the owner to decide"} for k in seats if mode == "full" and last[k].get("amendment")]
        for f, d in (("why", []), ("next_steps", []), ("fights", []), ("conditions", []), ("minority", {"seat": "", "quote": "", "would_have_to_be_true": ""})): v.setdefault(f, d)
        v["disclaimer"] = "Role-based AI advisors (%s), answering from SAMPLE business files. Not real people; check the numbers before you act." % config()["label"]
        line = lambda k: last[k].get("oneLine") or last[k].get("disagreeLine") or ""
        emit(s, {"type": "verdict", "verdict": v, "seats": [{"key": k, "weight": weights[k]["weight"], "optionScores": last[k].get("optionScores"), "oneLine": line(k)} for k in seats]})
        s["status"] = "done"
    except Exception as e:
        s["status"] = "error"; emit(s, {"type": "error", "error": str(e)[:200]})
    emit(s, {"type": "end"}); pool.shutdown(wait=False)

def config():
    return {"model": MODEL, "base": BASE if not OPENROUTER else "openrouter.ai", "openrouter": OPENROUTER, "cache_only": CACHE_ONLY, "cap": CAP,
            "label": ("Muse Ember via OpenRouter" if MODEL == "meta/muse-ember" else MODEL + " via OpenRouter") if OPENROUTER else "local model: " + MODEL}
def proof():
    rd = lambda n: json.load(open(os.path.join(ROOT, "proof", n))) if os.path.exists(os.path.join(ROOT, "proof", n)) else None
    log = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    return {"log": log, "total": spent(), "earlier_total": spent(OLD_LOG), "config": config(),
            "key_before": rd("council_key_before.json"), "key_after": rd("council_key_after.json")}
def sessions():
    out = []
    for f in sorted(glob.glob(os.path.join(HIST, "*.json")), reverse=True):
        try: d = json.load(open(f, encoding="utf8")); out.append({k: d.get(k) for k in ("id", "title", "mode", "status", "cost", "created")})
        except Exception: pass
    running = next((k for k, s in SESS.items() if s["status"] == "running"), None)
    return {"sessions": out, "running": running, "live": None}
def load(sid):
    if sid in SESS: return SESS[sid]
    p = hist_path(sid)
    return json.load(open(p, encoding="utf8")) if os.path.exists(p) else None
def presets(): return json.load(open(os.path.join(PUB, "presets.json"), encoding="utf8"))
def seats_for(industry):
    pr = presets(); ind = pr["industries"].get(industry) or pr["industries"]["restaurant"]
    conv = lambda a: {"key": a["id"], "name": a.get("short") or a["role"], "short": a.get("short") or a["role"], "pillar": a["role"], "role": a["role"], "focus": a["focus"],
                      "question": a["owns"], "owns": a["owns"], "persona": a.get("persona", ""), "portrait": a.get("portrait", "advisor"), "color": a.get("color", "#71CACD")}
    return [conv(a) for a in ind["advisors"]], [conv(a) for a in pr["extras"]], [a["id"] for a in ind["advisors"]]
def clean_seat(a):
    a = a if isinstance(a, dict) else {}
    d = {"key": re.sub(r"[^\w-]", "", clip(a.get("key"), 40)) or "seat", **{f: clip(a.get(f), n) for f, n in (("short", 40), ("role", 80), ("focus", 120), ("owns", 160), ("persona", 400))}}
    d["owns"] = d["owns"] or clip(a.get("question"), 160); d["role"] = d["role"] or clip(a.get("pillar"), 80)
    d.update(name=d["short"], pillar=d["role"], question=d["owns"], portrait=re.sub(r"[^\w]", "", clip(a.get("portrait"), 20)) or "drawn",
             color=a.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(a.get("color"))) else "#71CACD", custom=bool(a.get("custom")))
    return d

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body):
        b = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self): return json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 64000)) or b"{}")
    def do_GET(self):
        u = urlparse(self.path); path, qs = u.path, parse_qs(u.query)
        if path == "/api/proof": return self.send(200, proof())
        if path == "/api/config": return self.send(200, config())
        if path == "/api/usage":
            log = proof()["log"]; return self.send(200, {"calls": len(log), "cost": spent(), "label": config()["label"], "openrouter": OPENROUTER})
        if path == "/api/files":
            fs = data_files(); return self.send(200, {"files": [os.path.basename(f) for f in fs], "lines": sum(len(open(f, encoding="utf8").read().splitlines()) for f in fs)})
        if path == "/api/seats":
            board, extras, default = seats_for((qs.get("industry") or ["restaurant"])[0])
            return self.send(200, {"seats": board + extras, "board": {"default": default}, "runner": "api", "hasKey": bool(key()), "industries": {k: v["label"] for k, v in presets()["industries"].items()}, "tones": presets()["tones"]})
        if path == "/api/sessions": return self.send(200, sessions())
        if path.startswith("/api/sessions/"):
            s = load(path.rsplit("/", 1)[1]); return self.send(200, {"events": s["events"], "votes": s.get("votes", {})} if s else {"events": []})
        if path.startswith("/api/stream/"): return self.stream(path.rsplit("/", 1)[1])
        return super().do_GET()
    def stream(self, sid):
        s = load(sid)
        if not s: return self.send(404, {"error": "no such session"})
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
        i = 0
        try:
            while True:
                evs = s["events"]
                while i < len(evs):
                    self.wfile.write(("data: " + json.dumps(evs[i]) + "\n\n").encode()); i += 1
                    if evs[i - 1]["type"] == "end": self.wfile.flush(); return
                self.wfile.flush(); time.sleep(0.3)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
    def do_POST(self):
        try:
            d = self.body()
            if self.path == "/api/ask": return self.send(200, ask(d.get("mode"), d.get("payload") or {}))
            if self.path == "/api/propose":
                cands = [clean_seat(a) for a in (d.get("seats") or [])[:12]]
                p, m = must("chair", {"question": clip(d.get("prompt"), 600), "industry": clip(d.get("industry"), 60), "advisors": [{"id": a["key"], "role": a["role"], "owns": a["owns"]} for a in cands]})
                ids = {a["key"] for a in cands}; p["seated"] = [x for x in (p.get("seated") or []) if isinstance(x, dict) and x.get("id") in ids]
                return self.send(200, {"proposal": p, "meta": m})
            if self.path == "/api/council":
                if any(s["status"] == "running" for s in SESS.values()): return self.send(409, {"error": "A council is already running. Watch it, then ask again."})
                cands = {a["key"]: a for a in (clean_seat(x) for x in (d.get("seats") or [])[:9])}
                seats = [k for k in (d.get("seated") or []) if k in cands][:7]
                if len(seats) < 2: return self.send(400, {"error": "Seat at least two advisors."})
                pr = d.get("proposal") or {}
                opts = [{"id": clip(o.get("id"), 3), "label": clip(o.get("label"), 80)} for o in (pr.get("options") or []) if isinstance(o, dict)][:4] or [{"id": "A", "label": "Do it"}, {"id": "B", "label": "Keep as is"}]
                prop = {"title": clip(pr.get("title") or d.get("prompt"), 120), "options": opts,
                        "weights": {x.get("id"): {"weight": x.get("weight") if x.get("weight") in (1, 2, 3) else 1, "reason": clip(x.get("why"), 120)} for x in (pr.get("seated") or []) if isinstance(x, dict)}}
                sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
                s = SESS[sid] = {"id": sid, "title": prop["title"], "mode": "quick" if d.get("mode") == "quick" else "full", "status": "running", "question": clip(d.get("prompt"), 600),
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "cost": 0.0, "events": [], "seats": cands, "votes": {}}
                threading.Thread(target=run_council, args=(s, prop, seats, clip(d.get("tone"), 120), clip(d.get("industry"), 60)), daemon=True).start()
                return self.send(200, {"id": sid})
            if self.path.startswith("/api/vote/"):  # viewers vote on a verdict: {name, vote}
                s = load(self.path.rsplit("/", 1)[1])
                if not s: return self.send(404, {"error": "no such session"})
                s.setdefault("votes", {})[clip(d.get("name"), 30) or "guest"] = clip(d.get("vote"), 10)
                if "seats" in s: save(s)
                else: json.dump(s, open(hist_path(s["id"]), "w", encoding="utf8"), indent=1)
                return self.send(200, {"votes": s["votes"]})
            return self.send(404, {"error": "not found"})
        except Exception as e: self.send(500, {"error": str(e)[:300]})

def snap(n):
    k = api("/key"); k.get("data", {})["label"] = "(redacted)"  # labels can contain a key prefix; never write them
    json.dump(k, open(os.path.join(ROOT, "proof", n), "w"), indent=1)
def selftest():
    global LOG, CAP
    assert parse('```json\n{"a":1}\n```') == {"a": 1}
    assert messages("chair", {"question": "x" * 900, "advisors": [{"id": "a"}]})[1].count("x") == 600
    assert "{role}" not in seat_sys("open", {"seat": {"role": "Chef"}}) and "Chef" in seat_sys("open", {"seat": {"role": "Chef"}})
    assert scores_of({"a": {"optionScores": {"A": 8}}, "b": {"optionScores": {"A": 2}}}, {"a": {"weight": 3}, "b": {"weight": 1}}, [{"id": "A"}])["A"]["score"] == 6.5
    v = verify([{"file": "price_list.md", "lines": "1", "quote": "nonexistent words zzz"}]); assert v[0]["verified"] is False
    import tempfile; LOG = os.path.join(tempfile.mkdtemp(), "l.jsonl"); CAP = 0.01
    open(LOG, "w").write(json.dumps({"cost": 0.02}) + "\n")
    try: call([], "open"); assert 0
    except RuntimeError: pass
    for f in glob.glob(os.path.join(ROOT, "cache", "*.json")): assert json.load(open(f, encoding="utf8"))["mode"] in SYS
    print("selftest ok")
if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    elif "--snap" in sys.argv: snap(sys.argv[sys.argv.index("--snap") + 1])
    else:
        h, pt = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")); print("http://%s:%d  (%s)" % (h, pt, config()["label"]), flush=True)
        ThreadingHTTPServer((h, pt), partial(H, directory=PUB)).serve_forever()
