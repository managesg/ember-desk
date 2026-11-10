"""Records demo/ember_council_demo.webm by replaying cached Muse Ember answers (zero API spend, CACHE_ONLY on port 8001)."""
import subprocess, sys, time, glob, shutil, os, urllib.request
from playwright.sync_api import sync_playwright
os.chdir(os.path.dirname(os.path.abspath(__file__))); os.makedirs("demo", exist_ok=True)
env = {**os.environ, "PORT": "8001", "CACHE_ONLY": "1"}
srv = subprocess.Popen([sys.executable, "server.py"], env=env)
for _ in range(50):
    try: urllib.request.urlopen("http://127.0.0.1:8001/api/config", timeout=1); break
    except Exception: time.sleep(0.2)
errs = []
CAP = """(t) => { let c = document.getElementById('demoCap'); if (!c) { c = document.createElement('div'); c.id = 'demoCap';
  c.style.cssText = 'position:fixed;left:50%;bottom:18px;translate:-50% 0;z-index:9999;pointer-events:none;background:rgba(8,23,57,.94);color:#fff;border:1px solid #71CACD;border-radius:999px;padding:10px 22px;font:600 17px "IBM Plex Sans",sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.4);max-width:90vw;text-align:center';
  document.body.appendChild(c); } c.textContent = t; }"""
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        c = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir="demo/tmp", record_video_size={"width": 1280, "height": 720})
        pg = c.new_page()
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
        cap = lambda t: pg.evaluate(CAP, t)
        pg.goto("http://127.0.0.1:8001"); pg.wait_for_selector("#guideDialog[open]", timeout=5000)
        cap("Ember Council: a local-business advisor council on Muse Ember (OpenRouter)"); pg.wait_for_timeout(3500)
        pg.click("#gotIt"); pg.wait_for_timeout(1000)
        pg.click("#councilBtn"); pg.select_option("#industry", "restaurant"); cap("Pick your industry: Restaurant / cafe. Rename, recolour or add advisors.")
        pg.wait_for_timeout(3500); pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
        cap("Ask a real decision (typed, or by voice)")
        pg.type("#prompt", "Should we raise cold brew prices again?", delay=35); pg.wait_for_timeout(500); pg.click("#convene")
        pg.wait_for_selector("#confirmSeats", timeout=20000)
        cap("The Chair reads the owner's files (SAMPLE DATA) and proposes who should sit"); pg.wait_for_timeout(3500)
        for cb in pg.query_selector_all("#proposal input:not(:checked)"): cb.check()
        pg.click("#confirmSeats")
        cap("Chef, marketer, psychologist, ops and finance speak in turns, citing the files"); pg.wait_for_timeout(14000)
        pg.click(".speed button[data-speed='2.5']")
        cap("Fault lines, then the debate: who pushes back on whom"); pg.wait_for_timeout(12000)
        cap("The vote"); pg.click("#skipBtn"); pg.wait_for_timeout(1500)
        pg.wait_for_selector("#verdictSheet:not([hidden])", timeout=60000)
        cap("A scored verdict with next steps; quotes checked against the files"); pg.wait_for_timeout(4000)
        pg.mouse.move(640, 400); pg.mouse.wheel(0, 700); pg.wait_for_timeout(2500)
        pg.click("#verdictSheet [data-learn]"); pg.wait_for_selector("#copyPrompt", timeout=20000)
        cap("Learn it: the decision becomes a 10-minute AI lesson with a reusable prompt"); pg.wait_for_timeout(5000)
        pg.keyboard.press("Escape"); pg.click("#proofBtn")
        cap("Proof: every OpenRouter generation id, tokens and real cost"); pg.wait_for_timeout(5500)
        c.close(); b.close()
finally:
    srv.terminate()
assert not errs, errs
f = glob.glob("demo/tmp/*.webm")[0]; shutil.move(f, "demo/ember_council_demo.webm"); shutil.rmtree("demo/tmp")
if shutil.which("ffmpeg"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "demo/ember_council_demo.webm", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-movflags", "+faststart", "demo/ember_council_demo.mp4"], check=True)
print("saved demo/ember_council_demo.webm, console errors: 0")
