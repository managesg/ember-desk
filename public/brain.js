// Company Brain panel: connect folders, email (IMAP, read-only or draft-only) and desktop tools; approve memory notes; see the audit log.
// Owner-only actions need the PIN. Passwords are sent once to the local server and never shown or stored in the browser.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const say = (m) => { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(say.t); say.t = setTimeout(() => (t.hidden = true), 6000); };
let TOKEN = ""; try { TOKEN = sessionStorage.getItem("ember-owner") || ""; } catch { /* storage blocked: you will unlock again after a reload */ }
const S = { tab: "overview", st: null, cfg: null, audit: [], pending: [], note: "" };
const TABS = [["overview", "Overview"], ["connect", "Connect"], ["memory", "Memory notes"], ["audit", "Audit log"]];

async function api(path, body) {
  const h = { ...(TOKEN ? { "X-Owner-Token": TOKEN } : {}), ...(body === undefined ? {} : { "content-type": "application/json" }) };
  const r = await fetch("/api/brain/" + path, body === undefined ? { headers: h } : { method: "POST", headers: h, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 && TOKEN) { TOKEN = ""; try { sessionStorage.removeItem("ember-owner"); } catch { /* ignore */ } }
  if (!r.ok) throw new Error(j.error || "Request failed");
  return j;
}
const setToken = (t) => { TOKEN = t; try { sessionStorage.setItem("ember-owner", t); } catch { /* ignore */ } };
const chip = (kind, text) => `<span class="bchip ${kind}">${esc(text || kind)}</span>`;
const ago = (t) => (t ? esc(String(t).replace("T", " ").slice(0, 16)) : "never");

async function load() {
  S.st = await api("status");
  S.cfg = await fetch("/api/config").then((x) => x.json()).catch(() => null);
  if (S.st.owner) { S.pending = (await api("pending").catch(() => ({ pending: [] }))).pending; if (S.tab === "audit") S.audit = (await api("audit").catch(() => ({ events: [] }))).events; }
  render(); decorateBiz();
}
function render() {
  const st = S.st, b = $("#brainBody"); if (!st || !b) return;
  const head = `<h3>Company Brain</h3><p class="muted">Your company's second brain: notes, files and email the advisors can quote, under your control. Everything stays on this PC unless you pick a cloud engine.</p>`;
  if (!st.owner) {
    b.innerHTML = head + `<div class="bcard"><h4>${st.configured ? "Unlock with your PIN" : "Set an owner PIN to start"}</h4>
      <p class="muted">${st.configured ? "Only the owner can connect sources or approve actions." : "Choose a PIN (6 characters or more). It is stored hashed (PBKDF2) on this PC and is needed for every change. You can also set <code>EMBER_ADMIN_TOKEN</code> before starting the server."}</p>
      <div class="cfg-row"><label>${st.configured ? "PIN or admin token" : "New PIN"}<input id="bPin" type="password" autocomplete="off" minlength="6"></label><button class="convene" type="button" data-act="${st.configured ? "login" : "setpin"}">${st.configured ? "Unlock" : "Set PIN"}</button></div></div>
      ${st.counts.chunks ? `<p class="muted">Currently indexed: ${st.counts.notes} notes, ${st.counts.files} files, ${st.counts.emails} emails.</p>` : ""}`;
    return;
  }
  b.innerHTML = head + `<div class="btabs" role="tablist">${TABS.map(([k, l]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${S.tab === k}">${l}${k === "memory" && st.pending ? ` <i class="badge">${st.pending}</i>` : ""}</button>`).join("")}<span class="grow"></span><span class="bchip read">Owner unlocked</span><button class="ghost" type="button" data-act="lock">Lock</button></div>` + { overview, connect, memory, audit }[S.tab]();
}
function overview() {
  const st = S.st, c = st.counts, e = st.email, cfg = S.cfg || {}, rows = [];
  rows.push(`<tr><td><b>Memory notes</b><small>brain/*.md</small></td><td>${chip("read", "read")} ${chip("draft", "propose, you approve")}</td><td>${c.notes} note${c.notes === 1 ? "" : "s"}</td><td></td></tr>`);
  for (const f of st.folders) rows.push(`<tr><td><b>${esc(f.label)}</b><small>${esc(f.path)}</small></td><td>${chip("read", "read")}</td><td>${f.files} files</td><td><button class="ghost" type="button" data-act="rmfolder" data-id="${esc(f.id)}">Disconnect</button></td></tr>`);
  if (e) rows.push(`<tr><td><b>Email ${esc(e.user)}</b><small>${esc(e.host)} · ${esc(e.folders.join(", "))} · last ${e.days} days</small></td><td>${chip("read", "read")}${e.mode === "draft" ? " " + chip("draft", "save drafts") : ""}</td><td>${c.emails} emails${e.last_ingest ? `<small>ingested ${ago(e.last_ingest.at)}</small>` : ""}</td><td><button class="ghost" type="button" data-act="rmemail">Disconnect</button></td></tr>`);
  for (const a of st.actions) rows.push(`<tr><td><b>${esc(a.name)}</b><small><code>${esc(a.will_run)}</code></small></td><td>${chip("run", "run: each time you approve")}</td><td></td><td><button class="ghost" type="button" data-act="run" data-id="${esc(a.id)}">Run…</button> <button class="ghost" type="button" data-act="rmaction" data-id="${esc(a.id)}">Remove</button></td></tr>`);
  const eng = st.engine || {}, pr = st.privacy;
  return `<div class="proof-kpis"><div><b>${c.notes}</b><small>memory notes</small></div><div><b>${c.files}</b><small>files indexed</small></div><div><b>${c.emails}</b><small>emails indexed</small></div><div><b>${c.chunks}</b><small>searchable passages</small></div></div>
    <div class="cfg-row"><button class="convene" type="button" data-act="reindex">Re-index now</button><span class="muted">${st.last_index ? `Last index ${ago(st.last_index.at)}: ${st.last_index.files} files, ${st.last_index.unchanged} unchanged, ${st.last_index.ignored} ignored (hidden, linked or unsupported)${st.last_index.pdf_skipped ? `, ${st.last_index.pdf_skipped} PDFs need pypdf` : ""}.` : "Not indexed yet."}</span></div>
    <div class="bcard"><h4>What is connected, and what it may do</h4><table class="btable"><thead><tr><th>Source</th><th>Allowed</th><th>Items</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>
      <p class="muted small">Nothing outside these sources is read. The app never sends email and never runs a tool without your click.</p></div>
    <div class="bcard"><h4>Engine and privacy</h4>
      <div class="cfg-row"><label>Engine<select id="bProv">${(cfg.providers || []).map((p) => `<option value="${esc(p.id)}" ${p.id === cfg.provider ? "selected" : ""}>${esc(p.label)} (${esc(p.model)})</option>`).join("")}</select></label>${eng.cloud ? chip("draft", "cloud engine") : chip("read", "stays on this PC")}</div>
      <p class="muted small">${eng.cloud ? "A cloud engine receives the question and the few passages retrieved for it, not your whole drive." : "A local engine (Ollama or LM Studio) is recommended for regulated data: nothing leaves this PC."}</p>
      <label class="check"><input type="checkbox" data-priv="redact" ${pr.redact ? "checked" : ""}> Redact emails, phone numbers and card or IBAN-like numbers before sending to a cloud engine</label>
      <label class="check"><input type="checkbox" data-priv="deny_collection" ${pr.deny_collection ? "checked" : ""}> With OpenRouter, only use providers that do not store prompts (<code>data_collection: deny</code>)</label></div>
    <div class="cfg-row"><button class="ghost danger" type="button" data-act="disconnect_all">Disconnect everything</button></div>`;
}
function connect() {
  const st = S.st, e = st.email;
  return `<div class="bcard"><h4>1. Connect a folder (read only)</h4><p class="muted small">Indexes .txt, .md, .csv, .docx, .xlsx${st.pdf ? ", .pdf" : " (PDF needs <code>pip install pypdf</code>)"}. Hidden files, links and anything outside the folder are ignored.</p>
      <div class="cfg-row"><label>Folder path<input id="fPath" size="44" placeholder="C:\\Company\\Documents"></label><label>Name<input id="fLabel" size="14" placeholder="docs" maxlength="30"></label><button class="convene" type="button" data-act="addfolder">Connect folder</button></div></div>
    <div class="bcard"><h4>2. Connect email (IMAP)</h4>${e ? `<p>Connected: <b>${esc(e.user)}</b> on ${esc(e.host)}. ${chip("read", "read")}${e.mode === "draft" ? " " + chip("draft", "save drafts") : ""}</p>
        <div class="cfg-row"><label>Days to ingest<input id="eDays" type="number" min="1" max="365" value="${e.days}" style="width:80px"></label><button class="convene" type="button" data-act="ingest">Ingest recent email</button>
          <label class="check"><input type="checkbox" data-act="emode" ${e.mode === "draft" ? "checked" : ""}> Draft-only mode (save replies to Drafts)</label></div>
        ${e.mode === "draft" ? `<h4 class="sub">Save a reply draft</h4><div class="cfg-row"><label>To<input id="dTo" size="26" placeholder="name@example.com"></label><label>Subject<input id="dSub" size="30"></label></div><textarea id="dBody" class="mtext" rows="3" placeholder="Your reply. It is saved to Drafts, never sent."></textarea><div class="cfg-row"><button class="convene" type="button" data-act="draft">Save to Drafts</button><span class="muted small">The app has no way to send. You review and send from your mail app.</span></div>` : ""}`
      : `<p class="muted small">Use an <b>app password</b>, not your normal password. Gmail and Google Workspace: turn on 2-step verification, then create an app password. Many Microsoft 365 tenants block app-password IMAP; sign-in with OAuth is planned.</p>
        <div class="cfg-row"><label>Provider<select id="ePre"><option value="gmail">Gmail / Google Workspace</option><option value="microsoft365">Microsoft 365</option><option value="">Other IMAP server</option></select></label><label>Server<input id="eHost" value="imap.gmail.com" size="22"></label><label>Mailbox<input id="eUser" size="26" placeholder="you@company.com" autocomplete="off"></label><label>App password<input id="ePass" type="password" size="18" autocomplete="new-password"></label></div>
        <div class="cfg-row"><label>Folders (comma separated)<input id="eFolders" value="INBOX" size="26"></label><label>Recent days<input id="eDays" type="number" min="1" max="365" value="30" style="width:80px"></label>
          <label class="check"><input type="radio" name="eMode" value="read" checked> Read only</label><label class="check"><input type="radio" name="eMode" value="draft"> Read + save drafts</label><button class="convene" type="button" data-act="connectmail">Connect mailbox</button></div>`}
      <p class="muted small">Credentials go to a restricted file in your user profile (or the OS keyring if installed), never into this folder, the logs or the model.</p></div>
    <div class="bcard"><h4>3. Desktop tools (you approve every run)</h4><p class="muted small">Name an action with a fixed command. Advisors may suggest it; nothing runs until you click Approve. Shells and inline commands are refused.</p>
      <div class="cfg-row"><label>Name<input id="aName" size="26" placeholder="Run monthly report"></label><label>Command<input id="aCmd" size="46" placeholder="python C:\\reports\\monthly_report.py"></label><button class="convene" type="button" data-act="defaction">Add action</button></div>
      <div class="cfg-row"><label>Or open a file<input id="aFile" size="44" placeholder="C:\\Company\\sales.xlsx"></label><span class="muted small">Opens it with its default app (needs a name above).</span></div></div>`;
}
function memory() {
  const st = S.st;
  return `<div class="bcard"><h4>Awaiting your approval ${st.pending ? `<i class="badge">${st.pending}</i>` : ""}</h4>${S.pending.length ? S.pending.map((n) => `<div class="pnote"><b>${esc(n.title)}</b><p>${esc(n.text)}</p><small class="muted">Proposed by the council${n.source ? " in session " + esc(n.source) : ""}. Nothing is remembered until you approve.</small><div class="cfg-row"><button class="convene" type="button" data-act="napprove" data-id="${esc(n.id)}">Approve and remember</button><button class="ghost" type="button" data-act="nreject" data-id="${esc(n.id)}">Reject</button></div></div>`).join("") : `<p class="muted">No proposed notes. After a council, the advisors can propose a note to save (a decision, a price, a policy). You approve each one.</p>`}</div>
    <div class="bcard"><h4>Add a note yourself</h4><div class="cfg-row"><label>Title<input id="nTitle" size="40" maxlength="80" placeholder="Pricing policy"></label></div><textarea id="nText" class="mtext" rows="3" placeholder="Plain text or Markdown: decisions, who does what, prices, policies."></textarea><div class="cfg-row"><button class="convene" type="button" data-act="nadd">Save note</button></div></div>
    <div class="bcard"><h4>Notes in your brain (${st.notes.length})</h4>${st.notes.length ? `<ul class="nlist">${st.notes.map((n) => `<li><code>brain/${esc(n.file)}</code> ${esc(n.title)}</li>`).join("")}</ul>` : `<p class="muted">None yet. They are plain Markdown files in <code>${esc(st.home)}/brain</code>.</p>`}</div>`;
}
function audit() {
  return `<div class="cfg-row"><span class="muted">Every source added, index run, email ingest, draft and action. No file contents or passwords are logged. File: <code>logs/brain_audit.jsonl</code></span><button class="ghost" type="button" data-act="auditrefresh">Refresh</button></div>
    <div class="ptable-wrap"><table class="btable"><thead><tr><th>When</th><th>Event</th><th>Details</th></tr></thead><tbody>${S.audit.slice(0, 40).map((x) => { const { ts, event, ...rest } = x; return `<tr><td class="mono">${esc(ts.replace("T", " "))}</td><td><b>${esc(event)}</b></td><td class="mono small">${esc(Object.entries(rest).map(([k, v]) => `${k}=${v}`).join("  "))}</td></tr>`; }).join("") || `<tr><td colspan="3" class="muted">No events yet.</td></tr>`}</tbody></table></div>`;
}

async function act(name, el) {
  const v = (id) => ($("#" + id)?.value ?? "").trim();
  try {
    if (name === "setpin" || name === "login") { const j = await api(name === "setpin" ? "setup" : "login", { pin: $("#bPin").value }); setToken(j.token); say(name === "setpin" ? "PIN set. Company Brain is unlocked." : "Unlocked."); }
    else if (name === "lock") { await api("logout", {}).catch(() => {}); TOKEN = ""; try { sessionStorage.removeItem("ember-owner"); } catch { /* ignore */ } }
    else if (name === "reindex") { const j = await api("index", {}); say(`Indexed: ${j.files} files, ${j.notes} notes (${j.unchanged} unchanged).`); }
    else if (name === "addfolder") { const j = await api("folders/add", { path: v("fPath"), label: v("fLabel") }); say(`Folder connected: ${j.index.files} files indexed.`); S.tab = "overview"; }
    else if (name === "rmfolder") { await api("folders/remove", { id: el.dataset.id }); say("Folder disconnected and removed from the index."); }
    else if (name === "connectmail") { await api("email/connect", { preset: v("ePre"), host: v("eHost"), user: v("eUser"), password: $("#ePass").value, folders: v("eFolders"), days: +v("eDays") || 30, mode: $("input[name=eMode]:checked").value }); $("#ePass").value = ""; say("Mailbox connected. Press Ingest to read recent email."); }
    else if (name === "ingest") { const j = await api("email/ingest", { days: +v("eDays") || 30 }); say(`Read ${j.emails} emails from the last ${j.days} days (read-only).`); S.tab = "overview"; }
    else if (name === "rmemail") { await api("email/disconnect", {}); say("Mailbox disconnected, its emails removed from the index and its password deleted."); }
    else if (name === "draft") { const j = await api("email/draft", { to: v("dTo"), subject: v("dSub"), body: $("#dBody").value }); say(`Draft saved in ${j.saved_to}. It was not sent.`); $("#dBody").value = ""; }
    else if (name === "defaction") { await api("actions/define", { name: v("aName"), command: v("aCmd") || undefined, open_file: v("aFile") || undefined }); say("Action added. Each run will need your approval."); S.tab = "overview"; }
    else if (name === "rmaction") { await api("actions/remove", { id: el.dataset.id }); say("Action removed."); }
    else if (name === "run") return requestRun(el.dataset.id);
    else if (name === "napprove" || name === "nreject") { await api("notes/decide", { id: el.dataset.id, approve: name === "napprove" }); say(name === "napprove" ? "Remembered." : "Rejected."); }
    else if (name === "nadd") { await api("notes/add", { title: v("nTitle"), text: $("#nText").value }); say("Note saved and indexed."); }
    else if (name === "auditrefresh") { S.audit = (await api("audit")).events; return render(); }
    else if (name === "disconnect_all") { if (!confirm("Disconnect every folder, the mailbox and all tools? Your memory notes are kept.")) return; await api("disconnect_all", {}); say("Everything is disconnected."); }
    await load();
  } catch (e) { say(e.message); }
}
export async function requestRun(id) {  // the owner (or a council suggestion) asks; a human click on the exact command is still required
  if (!TOKEN) { await open(); return say("Unlock the Company Brain first to approve actions."); }
  try {
    const r = await api("actions/request", { id }), d = $("#approveDialog");
    $("#approveBody").innerHTML = `<h3>Approve this action?</h3><p class="muted">This is exactly what will run on your PC. It runs once, only if you click Approve.</p><p><b>${esc(r.name)}</b></p><pre class="cmd">${esc(r.will_run)}</pre><div class="cfg-row"><button class="convene" type="button" id="apOk">Approve and run</button><button class="ghost" type="button" id="apNo">Deny</button></div><p id="apRes" class="muted"></p>`;
    $("#apNo").onclick = async () => { await api("actions/decide", { run: r.run, approve: false }).catch(() => {}); d.close(); load().catch(() => {}); };
    $("#apOk").onclick = async () => { $("#apOk").disabled = true; try { const o = await api("actions/decide", { run: r.run, approve: true }); $("#apRes").textContent = o.still_running ? "Started. It is still running in the background." : `Finished with exit code ${o.exit_code}.`; } catch (e) { $("#apRes").textContent = e.message; } load().catch(() => {}); };
    if (!d.open) d.showModal();
  } catch (e) { say(e.message); }
}
export async function open() { await load().catch((e) => say(e.message)); const d = $("#brainDialog"); if (!d.open) d.showModal(); }
function decorateBiz() {
  const c = S.st?.counts, el = $("#bizFiles"); if (!el || !c || !(c.notes + c.files + c.emails)) return;
  const tag = ` + Company Brain: ${c.notes} notes, ${c.files} files, ${c.emails} emails`; if (!el.textContent.includes("Company Brain")) el.textContent += tag;
}

$("#brainBtn")?.addEventListener("click", open);
$("#brainBody")?.addEventListener("click", (e) => {
  const t = e.target.closest("[data-tab]"); if (t) { S.tab = t.dataset.tab; return (S.tab === "audit" ? api("audit").then((j) => (S.audit = j.events)).catch(() => {}) : Promise.resolve()).then(render); }
  const a = e.target.closest("button[data-act]"); if (a) act(a.dataset.act, a);
});
$("#brainBody")?.addEventListener("change", async (e) => {
  try {
    if (e.target.dataset.priv) { await api("privacy", { [e.target.dataset.priv]: e.target.checked }); say("Privacy setting saved."); return load(); }
    if (e.target.id === "bProv") { const r = await fetch("/api/provider", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: e.target.value }) }); const j = await r.json(); if (!r.ok) throw new Error(j.error); say("Engine: " + j.label); return load(); }
    if (e.target.id === "ePre") { const h = { gmail: "imap.gmail.com", microsoft365: "outlook.office365.com" }[e.target.value]; if (h) $("#eHost").value = h; return; }
    if (e.target.dataset.act === "emode") { await api("email/mode", { mode: e.target.checked ? "draft" : "read" }); say(e.target.checked ? "Draft-only mode on: replies can be saved to Drafts. Nothing is ever sent." : "Read-only."); return load(); }
  } catch (err) { say(err.message); load(); }
});
$("#brainBody")?.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "bPin") act(S.st.configured ? "login" : "setpin"); });
document.addEventListener("click", (e) => { const b = e.target.closest("[data-suggest]"); if (b) requestRun(b.dataset.suggest); });  // "Suggested by the council" buttons in the verdict
window.EmberBrain = { open, requestRun };
fetch("/api/brain/status").then((r) => r.json()).then((st) => { S.st = st; decorateBiz(); new MutationObserver(decorateBiz).observe($("#bizFiles") || document.body, { childList: true, characterData: true, subtree: true }); }).catch(() => {});
