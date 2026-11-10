"""Records demo/ember_desk_demo.webm by replaying cached answers (zero API spend)."""
import subprocess, sys, time, glob, shutil, os
from playwright.sync_api import sync_playwright
os.makedirs("demo", exist_ok=True)
srv = subprocess.Popen([sys.executable, "server.py"], env={**os.environ, "OPENROUTER_API_KEY": "unused-replay"}); time.sleep(1.5)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome"); c = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir="demo/tmp", record_video_size={"width": 1280, "height": 720})
    pg = c.new_page(); pg.goto("http://127.0.0.1:8000"); pg.wait_for_timeout(5000)
    pg.click("button:has-text('Why did sales drop?')"); pg.wait_for_timeout(8000)
    pg.click("button:has-text('What do customers complain about?')"); pg.wait_for_timeout(8000)
    pg.click("#tC"); pg.wait_for_timeout(1500); pg.click("#bc"); pg.wait_for_timeout(7000)
    pg.click("button:has-text('Grade my attempt')"); pg.wait_for_timeout(6000); pg.mouse.wheel(0, 2000); pg.wait_for_timeout(3000)
    pg.click("#tP"); pg.wait_for_timeout(8000)
    c.close(); b.close()
srv.terminate()
f = glob.glob("demo/tmp/*.webm")[0]; shutil.move(f, "demo/ember_desk_demo.webm"); shutil.rmtree("demo/tmp")
