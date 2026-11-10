"""Ember Desk: stdlib-only server. Files -> AI COO with citations + 7-day learn-AI course. Muse Ember via OpenRouter."""
import hashlib, json, os, sys, time, glob, subprocess, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL = "meta/muse-ember"; CAP = float(os.environ.get("BUDGET_CAP", "0.40")); HARD = 0.95  # unused headroom note: project total must stay <= $1
LOG = os.path.join(ROOT, "proof", "openrouter_log.jsonl"); URL = "https://openrouter.ai/api/v1"
SYS = {
 "coo": 'You are the COO of this business. Answer ONLY from the files. Return JSON: {"answer": str (<=120 words), "citations":[{"file":str,"lines":"a-b","quote":str}], "actions":[3 str], "confidence":0-1}. Every claim needs a citation using the N| line numbers. No markdown, no code fences.',
 "course": 'Build a 7-day course teaching this owner to use AI on their own files. Return JSON only, no code fences: {"days":[{"day":int,"title":str,"lesson":str (<=100 words, names their files),"prompt_to_copy":str,"exercise":str}]}',
 "grade": 'You grade the owner\'s attempt at a Day-1 AI exercise on their own files. Return JSON only, no code fences: {"score":0-10,"feedback":str (<=60 words),"next_day":{"day":2,"title":str,"lesson":str (<=100 words, adapted to their weakness),"prompt_to_copy":str,"exercise":str}}',
}
MAXTOK = {"coo": 4000, "course": 7000, "grade": 4000}  # reasoning model: thinking tokens count against max_tokens

def key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        try: k = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"], capture_output=True, text=True).stdout.strip()
        except Exception: k = ""
    return k
def pack():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "*"))):
        out.append("=== FILE: %s ===" % os.path.basename(p))
        out += ["%d| %s" % (i, l) for i, l in enumerate(open(p, encoding="utf8").read().splitlines(), 1)]
    return "\n".join(out)
def spent():
    return sum(json.loads(l).get("cost") or 0 for l in open(LOG)) if os.path.exists(LOG) else 0.0
def parse(t):
    t = t.strip()
    if t.startswith("```"): t = t.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)
def api(path, body=None):
    r = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120))
def call(messages, mode):
    if spent() >= CAP or 0.11 + spent() >= HARD: raise RuntimeError("budget guard: spent $%.4f >= cap $%.2f" % (spent(), CAP))
    t0 = time.time()
    for attempt in (0, 1):
        try: r = api("/chat/completions", {"model": MODEL, "messages": messages, "temperature": 0.2,
                "max_tokens": MAXTOK[mode], "reasoning": {"effort": "low"}, "usage": {"include": True}}); break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt: raise
            time.sleep(3)
    u = r.get("usage", {})
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "generation_id": r.get("id"), "model": r.get("model"), "mode": mode,
           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"), "cost": u.get("cost"),
           "latency_s": round(time.time() - t0, 1), "cache_hit": False}
    os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(json.dumps(rec) + "\n")
    return r["choices"][0]["message"]["content"], rec
def ask(mode, question=""):
    p = pack(); ck = os.path.join(ROOT, "cache", hashlib.sha256((mode + question + p).encode()).hexdigest() + ".json")
    if os.path.exists(ck):
        c = json.load(open(ck)); c["meta"]["cache_hit"] = True; c["meta"]["cost_this_call"] = 0; c["meta"]["total"] = spent(); return c
    msgs = [{"role": "system", "content": SYS[mode]}, {"role": "user", "content": p + "\n\n=== " + {"coo": "QUESTION", "course": "TASK", "grade": "OWNER ATTEMPT"}[mode] + " ===\n" + (question or "Create the course.")}]
    raw, rec = call(msgs, mode); cost = rec["cost"] or 0
    try: parsed = parse(raw)
    except Exception:
        raw, rec2 = call(msgs + [{"role": "assistant", "content": raw}, {"role": "user", "content": "Return only valid JSON, nothing else."}], mode)
        cost += rec2["cost"] or 0
        try: parsed = parse(raw)
        except Exception: parsed = None
    rec["cost_this_call"] = cost; rec["total"] = spent()
    out = {"mode": mode, "question": question, "parsed": parsed, "raw": raw, "meta": rec}
    json.dump(out, open(ck, "w"), indent=1); return out
def proof():
    rd = lambda n: json.load(open(os.path.join(ROOT, "proof", n))) if os.path.exists(os.path.join(ROOT, "proof", n)) else None
    log = [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
    return {"log": log, "total": spent(), "key_before": rd("key_before.json"), "key_after": rd("key_after.json")}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ct="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/proof": return self.send(200, proof())
        if self.path == "/api/files": return self.send(200, {"pack": pack()})
        self.send(200, open(os.path.join(ROOT, "index.html"), "rb").read(), "text/html")
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try: self.send(200, ask(d.get("mode", "coo"), d.get("question", "")))
        except Exception as e: self.send(500, {"error": str(e)})
def live():
    snap = lambda n: json.dump(api("/key"), open(os.path.join(ROOT, "proof", n), "w"), indent=1)
    snap("key_before.json")
    for m, q in [("coo", "Why did sales drop?"), ("coo", "What do customers complain about?"), ("coo", "What should I do this week?"),
                 ("course", ""), ("grade", "Summarize my reviews.")]:
        o = ask(m, q); print(m, "ok" if o["parsed"] else "NOJSON", o["meta"]["cost_this_call"], "total", o["meta"]["total"], flush=True)
    snap("key_after.json")
def selftest():
    global LOG, CAP
    assert parse('```json\n{"a":1}\n```') == {"a": 1}
    import tempfile; LOG = os.path.join(tempfile.mkdtemp(), "l.jsonl"); CAP = 0.01
    open(LOG, "w").write(json.dumps({"cost": 0.02}) + "\n")
    try: call([], "coo"); assert 0
    except RuntimeError: pass
    for f in glob.glob(os.path.join(ROOT, "cache", "*.json")): assert json.load(open(f))["mode"] in SYS
    print("selftest ok")
if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    elif "--live" in sys.argv: live()
    else:
        h, pt = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")); print("http://%s:%d" % (h, pt), flush=True); HTTPServer((h, pt), H).serve_forever()
