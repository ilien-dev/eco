"""Rasterises the symbol into the web icon set with headless Chromium (path in CHROME env var) and Pillow."""
import os, sys, time, subprocess, tempfile, base64, json
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "web"); os.makedirs(OUT, exist_ok=True)
CHROME = os.environ["CHROME"]

def render(svg, size, bg=None, pad=0.0):
    data = base64.b64encode(open(svg, "rb").read()).decode()
    p = size * pad
    html = (f"<!doctype html><html><body style='margin:0;width:{size}px;height:{size}px;overflow:hidden;"
            f"background:{bg or 'transparent'}'><img style='display:block;margin:{p}px;width:{size-2*p}px;height:{size-2*p}px' "
            f"src='data:image/svg+xml;base64,{data}'></body></html>")
    tmp = tempfile.mkdtemp()
    h = os.path.join(tmp, "p.html"); open(h, "w").write(html)
    shot = os.path.join(tmp, "s.png")
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    "--default-background-color=00000000", f"--window-size={size},{size}",
                    f"--screenshot={shot}",
                    "file:///" + h.replace("\\", "/")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last = -1
    for _ in range(240):  # Chromium may stay alive after writing the screenshot: wait for a stable file, then stop it
        if os.path.exists(shot) and os.path.getsize(shot) > 0 and os.path.getsize(shot) == last:
            break
        last = os.path.getsize(shot) if os.path.exists(shot) else -1
        time.sleep(0.25)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    return Image.open(shot).convert("RGBA").crop((0, 0, size, size))

LIME, INK, PAPER = "#C4F03A", "#151515", "#F4F4F2"
small = os.path.join(ROOT, "eco-symbol-tile-small.svg")  # tabs can be light or dark: the tile reads on both
ink = os.path.join(ROOT, "symbol", "eco-symbol-mono-151515.svg")
app = os.path.join(ROOT, "symbol", "eco-symbol-app-icon.svg")
big = render(small, 512)
for s in (16, 32, 48):
    big.resize((s, s), Image.LANCZOS).save(os.path.join(OUT, f"favicon-{s}.png"))
big.save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
render(ink, 180, bg=LIME, pad=0.16).save(os.path.join(OUT, "apple-touch-icon.png"))  # iOS masks it: opaque, full-bleed
render(app, 192).save(os.path.join(OUT, "icon-192.png"))
render(app, 512).save(os.path.join(OUT, "icon-512.png"))
render(ink, 512, bg=LIME, pad=0.2).save(os.path.join(OUT, "maskable-512.png"))
json.dump({"name": "Eco", "short_name": "Eco", "theme_color": INK, "background_color": PAPER, "display": "standalone",
           "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                     {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                     {"src": "maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]},
          open(os.path.join(OUT, "site.webmanifest"), "w"), indent=2)
open(os.path.join(OUT, "head-snippet.html"), "w").write(
    '<link rel="icon" href="/favicon.ico" sizes="any">\n<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n<link rel="manifest" href="/site.webmanifest">\n'
    '<meta name="theme-color" content="#151515">\n')
import shutil; shutil.copy(small, os.path.join(OUT, "favicon.svg"))
print("ok", sorted(os.listdir(OUT)))
