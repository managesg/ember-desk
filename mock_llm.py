"""Deterministic offline stand-in for the model (LLM_MOCK=1). Zero cost, no network. Used by tests and screenshots.
It reads the packed files out of the prompt and cites real lines, so citations verify like the real thing.
The wording is canned: it shows the plumbing (retrieval, citations, suggestions), not real advice."""
import json, re, zlib

def _lines(text):  # [(file, n, line, from_company_brain)] out of the "=== FILE: x ===" / "N| line" packing
    out, f, b = [], None, False
    for l in text.split("\n"):
        if l.startswith("=== COMPANY BRAIN"): b = True
        m = re.match(r"=== FILE: (.+) ===$", l)
        if m: f = m.group(1); continue
        m = re.match(r"(\d+)\| (.*)$", l)
        if m and f and len(m.group(2)) > 25: out.append((f, int(m.group(1)), m.group(2), b))
    return out
def _rank(user, question):  # best-matching lines first; company-brain lines (notes, files, email) outrank the sample data
    ts = re.findall(r"[a-z0-9]{4,}", question.lower())
    return sorted(_lines(user), key=lambda x: -(sum(t in x[2].lower() for t in ts) + 2 * x[3]))
def _cite(x):
    f, n, line, _ = x; q = line.strip()
    return {"file": f, "lines": "%d-%d" % (n, n), "quote": q if len(q) <= 90 else q[:90].rsplit(" ", 1)[0]}
def _ids(user):  # [(short, id)] from "Short (id=key): line" or "- id=key | role"
    out = re.findall(r"^(.+?) \(id=([\w-]+)\):", user, re.M)
    return out or [(b, b) for b in re.findall(r"id=([\w-]+) \|", user)]
def reply(messages, mode):
    sysm, user = messages[0]["content"], messages[-1]["content"]
    qm = re.search(r"=== QUESTION ===\n(.*?)\n===", user, re.S); question = qm.group(1) if qm else ""
    rank = _rank(user, question); pick = rank[zlib.crc32((sysm + mode).encode()) % min(len(rank), 2)] if rank else None
    cites = [_cite(pick)] if pick else []; ids = _ids(user); sc = {"A": 7, "B": 4, "C": 3}
    said = ('From %s: "%s"' % (pick[0], pick[2].strip()[:70])) if pick else "From the files"
    if mode == "test": return "Ember Council is online."
    if mode == "chair":
        cand = re.findall(r"- id=([\w-]+) \|", user)[:4]
        return json.dumps({"title": question[:70] or "The decision", "framing": "Mock engine: a deterministic stand-in so the room can be shown offline.",
                           "options": [{"id": "A", "label": "Do it"}, {"id": "B", "label": "Keep as is"}], "seated": [{"id": c, "why": "owns part of this", "weight": 2} for c in cand]})
    if mode == "open": return json.dumps({"stance": "conditional yes", "call": said + ". That supports a careful first step.", "optionScores": sc, "citations": cites})
    if mode == "cruxes":
        s = [i for _, i in ids]; h = max(len(s) // 2, 1)
        return json.dumps({"unanimous": False, "cruxes": [{"question": "How big should the first step be?", "sides": [{"position": "Start small", "seats": s[:h]}, {"position": "Go bigger", "seats": s[h:]}]}]})
    if mode == "rebut":
        me = re.search(r'\("([^"]+)"\)', sysm); mine = me.group(1) if me else ""
        other = next((i for sh, i in ids if sh != mine), ids[0][1] if ids else "")
        return json.dumps({"disagreeWith": other, "disagreeLine": said + ". I read the risk differently.", "moved": "no", "stance": "conditional yes", "optionScores": sc, "citations": cites})
    if mode == "draft": return json.dumps({"label": "RESHAPE", "option": "A", "recommendation": "Take the small first step, measure it for two weeks, then decide."})
    if mode == "vote": return json.dumps({"vote": "endorse", "oneLine": "I endorse the small first step, with a check after two weeks.", "amendment": "", "optionScores": sc, "citations": cites})
    if mode == "verdict":
        seats = [i for _, i in ids][:3] or ["a"]; other = next((x for x in rank if pick and x[0] != pick[0]), None)
        top = [_cite(x) for x in (rank[:1] + ([other] if other else rank[1:2]))]
        v = {"label": "RESHAPE", "recommended": "A", "call": "Take the small first step the files support, then review after two weeks.", "confidence": 7,
             "why": [{"seat": s, "point": ('"%s" (%s)' % (c["quote"][:80], c["file"]))} for s, c in zip(seats, top + top)],
             "minority": {"seat": seats[0], "quote": "I would wait for one more month of data.", "would_have_to_be_true": "Sales stay flat."},
             "next_steps": [{"when": "Today", "action": "Write down the decision and who owns it."}, {"when": "This week", "action": "Make the small change."}, {"when": "In 30 days", "action": "Review results against the files."}],
             "kill_criteria": "Stop if results drop two weeks in a row.", "fights": [{"crux": "First step size", "story": "Start small won the vote."}], "conditions": ["Check the numbers first."], "cheapest_test": "Try it for one week.", "revisit": "In 30 days", "citations": top}
        if "memory_proposals" in sysm: v["memory_proposals"] = [{"title": "Decision: small first step", "text": "The council recommended a small first step, reviewed after two weeks."}]
        am = re.search(r"exact names from (\[.*?\])", sysm)
        if am:
            try: v["suggested_actions"] = json.loads(am.group(1))[:1]
            except Exception: pass
        return json.dumps(v)
    if mode == "learn": return json.dumps({"title": "Decide with your own files", "why": "Your files already hold the evidence for this kind of decision.", "steps": ["2 min: Name the decision.", "3 min: Find the file lines that matter.", "3 min: Ask for a pro and a con.", "2 min: Write down your call."], "prompt_to_copy": "Using my files, list the evidence for and against [DECISION] with the file and line for each.", "try_next": "Try it on [YOUR NEXT DECISION]."})
    raise ValueError("unknown mode")
