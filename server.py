"""Ember Council: stdlib-only server. A role-based advisor council for local businesses that answers from the owner's own files.
Default engine: Muse Ember via OpenRouter. Any OpenAI-compatible endpoint works (Ollama, LM Studio, llama.cpp) via LLM_* env."""
import hashlib, json, os, sys, time, glob, subprocess, urllib.request, urllib.error
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
ROOT = os.path.dirname(os.path.abspath(__file__)); PUB = os.path.join(ROOT, "public")
BASE = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "meta/muse-ember")
OPENROUTER = "openrouter.ai" in BASE  # only OpenRouter gets usage.include / reasoning fields and a cost meter
CAP = float(os.environ.get("BUDGET_CAP", "0.20")); HARD = 0.95  # rebuild cap; whole project (old + new log) must stay under $0.95
CACHE_ONLY = os.environ.get("CACHE_ONLY") == "1"
LOG = os.path.join(ROOT, "proof", "council_log.jsonl"); OLD_LOG = os.path.join(ROOT, "proof", "openrouter_log.jsonl")
CITE = '"citations":[{"file":str,"lines":"a-b","quote":str (exact text from that line)}]'
RULES = " Answer ONLY from the owner's files, using the N| line numbers for citations. Return JSON only: no markdown, no code fences."
SYS = {
 "chair": 'You are the Chair of a small-business advisor council. Pick the 3-5 advisors who should sit for this question (prefer all who clearly own part of it).'
          ' Return {"framing":str (<=40 words: the decision and what the files already show),"seated":[{"id":str,"why":str (<=14 words)}]}.' + RULES,
 "speak": 'You are the {role} on the advisor council of a {biz} (focus: {focus}). The question you own: "{owns}". {persona} Tone: {tone}'
          ' It is your turn at the table: give your take from your seat, and react to an earlier speaker if useful. Never name or imitate real people.'
          ' Return {"line":str (<=45 words, spoken first person),"stance":"for"|"against"|"conditional","score":0-10 (how good the idea is from your seat),' + CITE + ' (1-2 items)}.' + RULES,
 "verdict": 'You are the Chair. Weigh the council and write the verdict for the owner. Return {"call":"GO"|"RESHAPE"|"DON\'T","score":0-100 (strength of the idea as asked),'
            '"headline":str (<=14 words),"summary":str (<=60 words),"actions":[3 str, concrete, this week],"dissent":str (<=25 words),' + CITE + ' (2-4 items)}.' + RULES,
 "learn": 'Turn this council decision into a 10-minute lesson that teaches the owner to use AI on their own files for this kind of decision.'
          ' Return {"title":str,"why":str (<=35 words),"steps":[4 str, each <=25 words, timed, e.g. "2 min: ..."],"prompt_to_copy":str (a reusable prompt with [BRACKETED] blanks the owner fills, <=90 words),"try_next":str (<=25 words)}.' + RULES,
}
MAXTOK = {"chair": 3000, "speak": 3000, "verdict": 4000, "learn": 4000}  # reasoning model: thinking tokens count against max_tokens

def key():
    # OpenRouter base prefers OPENROUTER_API_KEY: a machine-wide LLM_API_KEY often belongs to another provider
    if not OPENROUTER: return os.environ.get("LLM_API_KEY") or "local"
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        try: k = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"], capture_output=True, text=True).stdout.strip()
        except Exception: k = ""
    return k or os.environ.get("LLM_API_KEY") or ""
def pack():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "*"))):
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
def call(messages, mode):
    if spent() >= CAP or spent() + spent(OLD_LOG) >= HARD: raise RuntimeError("budget guard: spent $%.4f >= cap $%.2f" % (spent(), CAP))
    body = {"model": MODEL, "messages": messages, "temperature": 0.3, "max_tokens": MAXTOK[mode]}
    if OPENROUTER: body.update(reasoning={"effort": "low"}, usage={"include": True})
    t0 = time.time()
    for attempt in (0, 1):
        try: r = api("/chat/completions", body); break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt: raise
            time.sleep(3)
    u = r.get("usage") or {}
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "generation_id": r.get("id"), "model": r.get("model") or MODEL, "mode": mode,
           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"), "cost": u.get("cost") if OPENROUTER else 0,
           "latency_s": round(time.time() - t0, 1), "cache_hit": False, "provider": "openrouter" if OPENROUTER else "local"}
    os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(json.dumps(rec) + "\n")
    return r["choices"][0]["message"].get("content"), rec

clip = lambda s, n=300: str(s or "")[:n]  # trust boundary: browser-supplied text is length-capped before it reaches the prompt
def messages(mode, p):
    q = "=== QUESTION ===\n" + clip(p.get("question"), 500)
    if mode == "chair":
        cands = "\n".join("- id=%s | %s | owns: %s" % (clip(a.get("id"), 40), clip(a.get("role"), 80), clip(a.get("owns"), 160)) for a in p.get("advisors", [])[:8])
        return SYS["chair"], q + "\n=== BUSINESS TYPE ===\n" + clip(p.get("industry"), 60) + "\n=== CANDIDATE ADVISORS ===\n" + cands
    if mode == "speak":
        a = p.get("advisor") or {}
        s = SYS["speak"].format(role=clip(a.get("role"), 80), biz=clip(p.get("industry"), 60), focus=clip(a.get("focus"), 120),
                                owns=clip(a.get("owns"), 160), persona=clip(a.get("persona"), 400), tone=clip(p.get("tone"), 120))
        prior = "\n".join("%s: %s" % (clip(t.get("role"), 80), clip(t.get("line"), 400)) for t in p.get("prior", [])[:8]) or "(you speak first)"
        return s, q + "\n=== EARLIER AT THE TABLE ===\n" + prior
    if mode == "verdict":
        turns = "\n".join("%s [%s, %s/10]: %s" % (clip(t.get("role"), 80), clip(t.get("stance"), 20), clip(t.get("score"), 4), clip(t.get("line"), 400)) for t in p.get("turns", [])[:8])
        return SYS["verdict"], q + "\n=== THE COUNCIL SAID ===\n" + turns
    if mode == "learn":
        v = p.get("verdict") or {}
        return SYS["learn"], q + "\n=== VERDICT ===\n%s (%s/100): %s\nActions: %s" % (clip(v.get("call"), 10), clip(v.get("score"), 4), clip(v.get("summary"), 500), clip(v.get("actions"), 600))
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
def config():
    return {"model": MODEL, "base": BASE if not OPENROUTER else "openrouter.ai", "openrouter": OPENROUTER, "cache_only": CACHE_ONLY, "cap": CAP,
            "label": ("Muse Ember via OpenRouter" if MODEL == "meta/muse-ember" else MODEL + " via OpenRouter") if OPENROUTER else "local model: " + MODEL}
def proof():
    rd = lambda n: json.load(open(os.path.join(ROOT, "proof", n))) if os.path.exists(os.path.join(ROOT, "proof", n)) else None
    log = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    return {"log": log, "total": spent(), "earlier_total": spent(OLD_LOG), "config": config(),
            "key_before": rd("council_key_before.json"), "key_after": rd("council_key_after.json")}
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body):
        b = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/proof": return self.send(200, proof())
        if self.path == "/api/config": return self.send(200, config())
        if self.path == "/api/files":
            fs = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(ROOT, "data", "*")))]
            return self.send(200, {"files": fs, "lines": sum(len(open(f, encoding="utf8").read().splitlines()) for f in glob.glob(os.path.join(ROOT, "data", "*")))})
        return super().do_GET()
    def do_POST(self):
        if self.path != "/api/ask": return self.send(404, {"error": "not found"})
        try:
            d = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 64000)) or b"{}")
            self.send(200, ask(d.get("mode"), d.get("payload") or {}))
        except Exception as e: self.send(500, {"error": str(e)})
def snap(n):
    k = api("/key"); k.get("data", {})["label"] = "(redacted)"  # labels can contain a key prefix; never write them
    json.dump(k, open(os.path.join(ROOT, "proof", n), "w"), indent=1)
def selftest():
    global LOG, CAP
    assert parse('```json\n{"a":1}\n```') == {"a": 1}
    assert messages("chair", {"question": "x" * 900, "advisors": [{"id": "a"}]})[1].count("x") == 500
    import tempfile; LOG = os.path.join(tempfile.mkdtemp(), "l.jsonl"); CAP = 0.01
    open(LOG, "w").write(json.dumps({"cost": 0.02}) + "\n")
    try: call([], "speak"); assert 0
    except RuntimeError: pass
    for f in glob.glob(os.path.join(ROOT, "cache", "*.json")): assert json.load(open(f, encoding="utf8"))["mode"] in SYS
    print("selftest ok")
if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    elif "--snap" in sys.argv: snap(sys.argv[sys.argv.index("--snap") + 1])
    else:
        h, pt = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")); print("http://%s:%d  (%s)" % (h, pt, config()["label"]), flush=True)
        ThreadingHTTPServer((h, pt), partial(H, directory=PUB)).serve_forever()
