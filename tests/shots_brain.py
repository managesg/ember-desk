"""Takes the Company Brain screenshots in docs/img/ (Playwright + Chrome, 1280x720) against tests/demo_server.py:
mock engine, mocked IMAP mailbox and made-up company files in a temp folder. No real data, no network, no spend."""
import os, shutil, subprocess, sys, tempfile, time, urllib.request
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(ROOT, "docs", "img"); PORT = "8012"
base = r"C:\EmberDemo" if os.name == "nt" else tempfile.gettempdir(); os.makedirs(base, exist_ok=True)  # outside the user profile, so no account name shows up in the screenshots
home = tempfile.mkdtemp(prefix="s", dir=base); srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "demo_server.py"), PORT, home])
for _ in range(60):
    try: urllib.request.urlopen("http://127.0.0.1:%s/api/config" % PORT, timeout=1); break
    except Exception: time.sleep(0.3)
errs = []; PIN = "company-pin-1"; MAILPW = "demo-app-secret-9"
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome"); pg = b.new_context(viewport={"width": 1280, "height": 720}).new_page()
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:%s" % PORT)
        if pg.query_selector("#guideDialog[open]"): pg.click("#gotIt")
        pg.click("#brainBtn"); pg.fill("#bPin", PIN); pg.click("[data-act=setpin]"); pg.wait_for_selector("[data-tab=connect]")
        tab = lambda t: (pg.click("[data-tab=%s]" % t), pg.wait_for_timeout(300))
        # connect a folder, a mailbox (draft-only) and two tools, all mocked or temp
        tab("connect"); pg.fill("#fPath", os.path.join(home, "Company Docs")); pg.fill("#fLabel", "docs"); pg.click("[data-act=addfolder]"); pg.wait_for_selector("[data-act=rmfolder]")
        tab("connect"); pg.fill("#eUser", "owner@example.com"); pg.fill("#ePass", MAILPW); pg.check("input[name=eMode][value=draft]"); pg.click("[data-act=connectmail]"); pg.wait_for_selector("[data-act=ingest]")
        pg.click("[data-act=ingest]"); pg.wait_for_selector("[data-act=rmemail]")
        tab("connect"); pg.fill("#aName", "Run monthly report"); pg.fill("#aCmd", "%s %s" % (sys.executable, os.path.join(home, "report.py"))); pg.click("[data-act=defaction]"); pg.wait_for_selector("[data-act=rmaction]")
        tab("connect"); pg.fill("#aName", "Open price_review.xlsx"); pg.fill("#aFile", os.path.join(home, "Company Docs", "price_review.xlsx")); pg.click("[data-act=defaction]"); pg.wait_for_timeout(500)
        tab("memory"); pg.fill("#nTitle", "Pricing policy"); pg.fill("#nText", "We never raise cold brew prices more than once a quarter.\nAny change needs two weeks notice on the menu and a note to staff.\nThe owner approves all price changes."); pg.click("[data-act=nadd]"); pg.wait_for_timeout(600)
        tab("overview"); pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(OUT, "8-company-brain.png"))
        # approving a desktop tool: the exact command is shown, and nothing runs without the click
        pg.click("[data-act=run] >> nth=0"); pg.wait_for_selector("#apOk"); pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(OUT, "9-approve-action.png")); pg.click("#apNo"); pg.wait_for_timeout(300)
        pg.keyboard.press("Escape")
        # a council that answers from the brain
        pg.click("#newBtn") if pg.query_selector("#newBtn:not([hidden])") else None
        pg.fill("#prompt", "Should we raise cold brew prices again?"); pg.click("#convene"); pg.wait_for_selector("#confirmSeats", timeout=30000)
        for cb in pg.query_selector_all("#proposal input:not(:checked)"): cb.check()
        pg.click("#confirmSeats"); pg.wait_for_timeout(1500)
        for _ in range(40):
            if pg.query_selector("#verdictSheet:not([hidden])"): break
            if pg.is_visible("#skipBtn"): pg.click("#skipBtn")
            pg.wait_for_timeout(1000)
        pg.wait_for_selector("#verdictSheet:not([hidden])", timeout=30000); pg.wait_for_timeout(1500)
        el = pg.query_selector(".v-suggest"); (el or pg.query_selector(".v-files")).scroll_into_view_if_needed(); pg.evaluate("document.querySelector('#verdictSheet').scrollBy(0, 250)"); pg.wait_for_timeout(800)
        pg.screenshot(path=os.path.join(OUT, "10-brain-citations.png")); b.close()
finally: srv.terminate(); shutil.rmtree(home, ignore_errors=True)
assert not errs, errs
print("screenshots saved in docs/img, console errors: 0")
