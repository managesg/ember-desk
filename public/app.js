// Ember Council front end. Table geometry and word-by-word captions adapted from Roast Room (MIT, (c) 2026 AI Automation Society).
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const S = { presets: null, industry: "restaurant", off: new Set(), custom: [], tone: "straight", seated: [], turns: [], verdict: null, busy: false, cfg: {} };
const SAMPLES = ["Should we raise cold brew prices again?", "Why did sales drop in October?", "Should we fix the grinder or buy a new one?"];
const mono = (role) => role.split(/[\s&/-]+/).filter((w) => /^[A-Za-z]/.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const pool = () => [...S.presets.industries[S.industry].advisors, ...S.custom];
const active = () => pool().filter((a) => !S.off.has(a.id));
const byId = (id) => pool().find((a) => a.id === id);

function toast(t) { const el = $("#toast"); el.textContent = t; el.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (el.hidden = true), 3500); }
function step(name) {
  const order = $$("#stepper li").map((l) => l.dataset.step), i = order.indexOf(name);
  $$("#stepper li").forEach((l, j) => (l.className = j < i ? "done" : j === i ? "active" : ""));
}
function tab(name) {
  $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  $$(".tabpanel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
  if (name === "proof") proof();
}
function meter(m) {
  if (!S.cfg.openrouter) { $("#meter").textContent = "$0 local"; return; }
  $("#meter").textContent = (m.cache_hit ? "cached replay $0 | " : "call $" + (m.cost_this_call || 0).toFixed(4) + " | ") + "spent $" + (m.total || 0).toFixed(4);
}
async function ask(mode, payload) {
  const r = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode, payload }) });
  const d = await r.json();
  if (!r.ok || d.error) throw new Error(d.error || "request failed");
  meter(d.meta);
  if (!d.parsed) throw new Error("the model did not return valid JSON");
  return d;
}
const citeHtml = (cs) => (cs || []).map((c) => `<div class="cite"><b>${esc(c.file)} L${esc(c.lines)}</b> "${esc(c.quote)}"</div>`).join("");

// ---------- setup ----------
function renderSetup() {
  $("#industry").innerHTML = Object.entries(S.presets.industries).map(([k, v]) => `<option value="${k}" ${k === S.industry ? "selected" : ""}>${esc(v.label)}</option>`).join("");
  $("#tone").innerHTML = Object.entries(S.presets.tones).map(([k, v]) => `<option value="${k}" ${k === S.tone ? "selected" : ""}>${esc(v.split(":")[0])}</option>`).join("");
  $("#roster").innerHTML = pool().map((a) => `<label class="adv ${S.off.has(a.id) ? "off" : ""}"><input type="checkbox" data-id="${esc(a.id)}" ${S.off.has(a.id) ? "" : "checked"}><b>${esc(a.role)}</b><span>${esc(a.owns || a.focus)}</span></label>`).join("");
  seat(active().map((a) => a.id));
}
function seat(ids) {
  S.table = ids.slice(0, 7);
  const list = S.table.map(byId);
  $("#seats").innerHTML = list.map((a) => `<div class="seat ${a.custom ? "custom" : ""}" id="seat-${a.id}" title="${esc(a.role)}"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="head" cx="50" cy="34" r="20"/><path class="body" d="M14 100c0-24 16-40 36-40s36 16 36 40z"/><text class="mono" x="50" y="39">${esc(mono(a.role))}</text></svg></div>`).join("");
  $("#plates").innerHTML = list.map((a) => `<div class="nameplate" id="plate-${a.id}"><b>${esc(a.role)}</b><small>${esc(a.focus)}</small><span class="score" hidden></span></div>`).join("");
  layout();
}
// The table is an ellipse seen from the front; seats sit along its far edge (Roast Room layoutStage, simplified).
function layout() {
  const st = $("#stage"), W = st.clientWidth, H = st.clientHeight, n = S.table.length;
  const cx = W / 2, cy = H * 0.98, rx = W * 0.5, ry = H * 0.5;
  Object.assign($("#table").style, { left: `${cx - rx}px`, top: `${cy - ry}px`, width: `${rx * 2}px`, height: `${ry * 2}px` });
  const edge = (x) => cy - ry * Math.sqrt(Math.max(0, 1 - ((x - cx) / rx) ** 2));
  S.geo = {};
  S.table.forEach((id, i) => {
    const x = W * (n === 1 ? 0.5 : 0.1 + (0.8 * i) / (n - 1)), d = ((x - cx) / rx) ** 2;
    const size = Math.min(H * (0.2 + 0.05 * d), W / (n + 1.6)), bottom = edge(x) + size * 0.12;
    Object.assign($(`#seat-${id}`).style, { left: `${x - size / 2}px`, top: `${bottom - size}px`, width: `${size}px`, height: `${size}px` });
    Object.assign($(`#plate-${id}`).style, { left: `${x}px`, top: `${edge(x) + 22}px` });
    S.geo[id] = { x, y: bottom - size * 0.55, size };
  });
  const top = Math.max(H * 0.5, ...S.table.map((id) => $(`#plate-${id}`).offsetTop + 44));
  Object.assign($("#center").style, { left: `${W * 0.12}px`, width: `${W * 0.76}px`, top: `${Math.min(top, H * 0.56)}px`, height: `${H - top}px` });
  if (S.speaking) spot(S.speaking);
}
function spot(id) {
  const g = S.geo[id], el = $("#spot");
  if (!g) return el.classList.remove("on");
  Object.assign(el.style, { left: `${g.x}px`, top: `${g.y}px`, width: `${g.size * 1.6}px`, height: `${g.size * 1.6}px` });
  el.classList.add("on");
}
function show(which) { ["composer", "proposal", "caption"].forEach((k) => ($("#" + k).hidden = k !== which)); }

// ---------- chair ----------
async function askChair(question) {
  if (S.busy) return; S.busy = true; S.question = question; $("#convene").disabled = true;
  const cands = active();
  if (cands.length < 2) { S.busy = false; $("#convene").disabled = false; return toast("Turn on at least two advisors."); }
  step("chair"); chairSays("Reading your files and choosing who should sit...", true);
  try {
    const d = await ask("chair", { question, industry: S.presets.industries[S.industry].label, advisors: cands.map(({ id, role, owns }) => ({ id, role, owns })) });
    const valid = (d.parsed.seated || []).filter((s) => cands.some((a) => a.id === s.id));
    S.why = Object.fromEntries(valid.map((s) => [s.id, s.why]));
    $("#proposal").innerHTML = `<div class="label">The Chair proposes</div><h2>${esc(d.parsed.framing)}</h2>
      <div class="prop-list">${cands.map((a) => `<label><input type="checkbox" data-seat="${esc(a.id)}" ${S.why[a.id] ? "checked" : ""}><b>${esc(a.role)}</b><span>${esc(S.why[a.id] || "Not proposed: tick to seat anyway")}</span></label>`).join("")}</div>
      <button class="primary" id="confirm" type="button">Confirm the council</button>`;
    show("proposal"); seat(cands.map((a) => a.id)); markOff();
    $("#proposal").addEventListener("change", markOff);
    $("#confirm").onclick = runCouncil;
  } catch (e) { toast(e.message); show("composer"); step("setup"); }
  S.busy = false; $("#convene").disabled = false;
}
function markOff() {
  const on = new Set($$("#proposal input:checked").map((i) => i.dataset.seat));
  S.table.forEach((id) => { $(`#seat-${id}`).classList.toggle("off", !on.has(id)); $(`#plate-${id}`).classList.toggle("off", !on.has(id)); });
}
function chairSays(text, dots) {
  show("caption"); $("#capAv").textContent = "CH"; $("#capWho").textContent = "The Chair"; $("#capTag").textContent = "";
  $("#capText").innerHTML = esc(text) + (dots ? " ..." : ""); $("#capSub").textContent = "";
}

// ---------- the table ----------
async function runCouncil() {
  if (S.busy) return; S.busy = true;
  S.seated = $$("#proposal input:checked").map((i) => i.dataset.seat);
  if (S.seated.length < 2) { S.busy = false; return toast("Seat at least two advisors."); }
  seat(S.seated); step("talk"); tab("feed"); $("#tab-feed").innerHTML = "";
  $("#stage").classList.add("live"); S.turns = [];
  const industry = S.presets.industries[S.industry].label, tone = S.presets.tones[S.tone];
  try {
    for (const id of S.seated) {
      const a = byId(id); $(`#seat-${id}`).classList.add("thinking");
      const d = await ask("speak", { question: S.question, industry, tone, advisor: { id: a.id, role: a.role, focus: a.focus, owns: a.owns, persona: a.persona },
        prior: S.turns.map((t) => ({ role: t.role, line: t.line })) });
      $(`#seat-${id}`).classList.remove("thinking");
      const p = d.parsed, t = { id, role: a.role, line: String(p.line || ""), stance: p.stance || "conditional", score: p.score ?? "?", citations: p.citations || [] };
      S.turns.push(t);
      await speak(t);
    }
    await verdict();
  } catch (e) { toast(e.message); }
  S.busy = false;
}
async function speak(t) {
  S.speaking = t.id; spot(t.id);
  $$(".seat").forEach((s) => s.classList.toggle("speaking", s.id === "seat-" + t.id));
  $$(".nameplate").forEach((s) => s.classList.toggle("speaking", s.id === "plate-" + t.id));
  show("caption"); $("#capAv").textContent = mono(t.role); $("#capWho").textContent = t.role; $("#capTag").textContent = byId(t.id).owns || "";
  const words = t.line.split(" ").filter(Boolean), p = $("#capText");
  p.innerHTML = words.map((w) => `<span class="w">${esc(w)}</span>`).join(" "); $("#capSub").innerHTML = "";
  const spans = $$(".w", p);
  for (let i = 0; i < spans.length; i++) { spans[i].classList.add("on"); await sleep(55 + (/[.!?]$/.test(words[i]) ? 160 : 0)); }
  $("#capSub").innerHTML = citeHtml(t.citations);
  const sc = $(`#plate-${t.id} .score`); sc.hidden = false; sc.className = "score st-" + t.stance; sc.textContent = `${t.stance} ${t.score}/10`;
  $("#tab-feed").insertAdjacentHTML("beforeend", `<div class="card"><div class="h">${esc(t.role)}<span class="score st-${esc(t.stance)}">${esc(t.stance)} ${esc(t.score)}/10</span></div><p>${esc(t.line)}</p>${citeHtml(t.citations)}</div>`);
  $("#tab-feed").scrollTop = 1e6;
  await sleep(1500);
  $(`#seat-${t.id}`).classList.remove("speaking"); $(`#seat-${t.id}`).classList.add("spoke");
}

// ---------- verdict + learn ----------
async function verdict() {
  S.speaking = null; $("#spot").classList.remove("on"); $$(".speaking").forEach((s) => s.classList.remove("speaking"));
  step("verdict"); chairSays("Weighing the council and checking the files...", true);
  const d = await ask("verdict", { question: S.question, turns: S.turns.map(({ role, stance, score, line }) => ({ role, stance, score, line })) });
  const v = (S.verdict = d.parsed), cls = String(v.call || "").replace(/[^A-Z]/g, "");
  $("#sheetBody").innerHTML = `<div class="v-top"><div><div class="label">Council verdict &middot; ${esc(S.question)}</div><div class="v-head">${esc(v.headline)}</div><span class="v-call ${cls}">${esc(v.call)}</span></div>
    <div class="v-score">${esc(v.score)}<small>score / 100</small></div></div>
    <div class="v-grid"><div><h4>Why</h4><p>${esc(v.summary)}</p><h4>Dissent</h4><p>${esc(v.dissent)}</p>
      <div class="v-seats">${S.turns.map((t) => `<span>${esc(t.role)}: <b class="st-${esc(t.stance)}">${esc(t.stance)} ${esc(t.score)}/10</b></span>`).join("")}</div></div>
    <div><h4>Next 3 actions</h4><ol>${(v.actions || []).map((a) => `<li>${esc(a)}</li>`).join("")}</ol><h4>From your files</h4>${citeHtml(v.citations)}</div></div>
    <div class="v-actions"><button class="primary" id="learnBtn">Learn it: 10-minute lesson</button><button class="ghost" id="hearBtn">Read verdict aloud</button><button class="ghost" id="printBtn">Print / PDF</button><button class="ghost" id="proofBtn">Proof</button><button class="ghost" id="closeBtn">Back to the table</button></div>
    <div id="learnBody"></div>`;
  $("#sheet").hidden = false; $("#sheet").scrollTop = 0;
  $("#learnBtn").onclick = learn; $("#printBtn").onclick = () => window.print(); $("#closeBtn").onclick = () => ($("#sheet").hidden = true);
  $("#proofBtn").onclick = () => { $("#sheet").hidden = true; tab("proof"); };
  $("#hearBtn").onclick = () => say(`${v.call}. ${v.headline}. ${v.summary} Next actions: ${(v.actions || []).join(". ")}`);
}
async function learn() {
  $("#learnBtn").disabled = true; step("learn"); $("#learnBody").innerHTML = `<div class="learn"><p class="empty">Turning this decision into a lesson...</p></div>`;
  try {
    const d = await ask("learn", { question: S.question, verdict: { call: S.verdict.call, score: S.verdict.score, summary: S.verdict.summary, actions: S.verdict.actions } }), l = d.parsed;
    $("#learnBody").innerHTML = `<div class="learn"><div class="label">Learn AI by doing your real work &middot; 10 minutes</div><h3>${esc(l.title)}</h3><p>${esc(l.why)}</p>
      <ol>${(l.steps || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol><h4 class="label">Your reusable prompt</h4>
      <div class="prompt-box"><button id="copyBtn">Copy</button>${esc(l.prompt_to_copy)}</div><p><b>Try next:</b> ${esc(l.try_next)}</p></div>`;
    $("#copyBtn").onclick = () => navigator.clipboard.writeText(l.prompt_to_copy).then(() => toast("Prompt copied"), () => toast("Copy blocked: select the text instead"));
    $("#learnBody").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { toast(e.message); }
  $("#learnBtn").disabled = false;
}

// ---------- proof ----------
async function proof() {
  const p = await (await fetch("/api/proof")).json(), log = p.log, n = log.length;
  const toks = log.reduce((s, l) => s + (l.prompt_tokens || 0) + (l.completion_tokens || 0), 0);
  const kb = p.key_before?.data?.usage, ka = p.key_after?.data?.usage;
  $("#tab-proof").innerHTML = `<div class="kpis"><div class="big">$${p.total.toFixed(4)}<small>logged spend, this rebuild (cap $${p.config.cap.toFixed(2)})</small></div>
    <div class="big">${n}<small>${esc(p.config.label)} calls, ${toks.toLocaleString()} tokens</small></div></div>
    <div class="files">Every call: generation id, model, tokens and cost from OpenRouter <b>usage.include</b>, logged to <b>proof/council_log.jsonl</b>. Replays come from <b>cache/</b> at $0.${kb != null && ka != null ? ` Key usage before/after the live run: $${kb.toFixed(4)} &rarr; $${ka.toFixed(4)}.` : ""} Earlier Ember Desk build: $${p.earlier_total.toFixed(4)}.</div>
    <table class="ptable"><tr><th>generation id</th><th>mode</th><th>in/out</th><th>cost</th></tr>${log.slice().reverse().map((l) => `<tr><td title="${esc(l.generation_id)}">${esc(String(l.generation_id).slice(0, 14))}</td><td>${esc(l.mode)}</td><td>${l.prompt_tokens}/${l.completion_tokens}</td><td>${l.cost == null ? "-" : "$" + Number(l.cost).toFixed(5)}</td></tr>`).join("")}</table>`;
}

// ---------- voice (Web Speech API; typing always works) ----------
function say(text) {
  if (!("speechSynthesis" in window)) return toast("This browser cannot read aloud.");
  speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}
function bindMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition, btn = $("#mic");
  if (!SR) { btn.hidden = true; return; }
  let rec = null;
  btn.onclick = () => {
    if (rec) return rec.stop();
    rec = new SR(); rec.lang = navigator.language || "en-US"; rec.interimResults = true;
    rec.onresult = (e) => ($("#prompt").value = [...e.results].map((r) => r[0].transcript).join(""));
    rec.onend = () => { rec = null; btn.classList.remove("on"); };
    rec.onerror = (e) => toast("Voice: " + e.error + ". You can type instead.");
    btn.classList.add("on"); rec.start();
  };
}

// ---------- boot ----------
async function boot() {
  const [pr, cfg, files] = await Promise.all(["/presets.json", "/api/config", "/api/files"].map((u) => fetch(u).then((r) => r.json())));
  S.presets = pr; S.cfg = cfg;
  $("#runs").innerHTML = `Runs on: <b>${esc(cfg.label)}</b>`;
  if (!cfg.openrouter) $("#meter").textContent = "$0 local";
  $("#files").innerHTML = `<b>${files.files.length} business files loaded</b> (SAMPLE DATA, ${files.lines} lines): ${files.files.map(esc).join(", ")}. Every advisor cites them by line.`;
  $("#samples").innerHTML = SAMPLES.map((s) => `<button type="button">${esc(s)}</button>`).join("");
  $("#samples").onclick = (e) => { if (e.target.tagName === "BUTTON") $("#prompt").value = e.target.textContent; };
  $("#industry").onchange = (e) => { S.industry = e.target.value; S.off.clear(); renderSetup(); };
  $("#tone").onchange = (e) => (S.tone = e.target.value);
  $("#roster").onchange = (e) => { const id = e.target.dataset.id; e.target.checked ? S.off.delete(id) : S.off.add(id); renderSetup(); };
  $("#cAdd").onclick = () => {
    const role = $("#cRole").value.trim(), focus = $("#cFocus").value.trim();
    if (!role || !focus) return toast("Give the advisor a role and a focus.");
    S.custom.push({ id: "custom" + (S.custom.length + 1), role, focus, owns: "What does this mean for " + focus + "?", persona: "You are an experienced " + role + " focused on " + focus + ".", custom: true });
    $("#cRole").value = $("#cFocus").value = ""; renderSetup(); toast(role + " joined the council.");
  };
  $$(".tabs button").forEach((b) => (b.onclick = () => tab(b.dataset.tab)));
  $("#composer").onsubmit = (e) => { e.preventDefault(); const q = $("#prompt").value.trim(); if (q.length < 8) return toast("Ask a full question."); askChair(q); };
  addEventListener("resize", layout);
  bindMic(); renderSetup(); step("setup");
}
boot();
