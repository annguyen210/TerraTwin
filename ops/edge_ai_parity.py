"""So AI trên máy (onnxruntime-web trong Chromium) với AI máy chủ (field_water.water_ratio, Python) trên cùng ảnh."""
import functools
import http.server
import mimetypes
import sys
import threading
from pathlib import Path

sys.path.insert(0, r"D:\terratwin\backend")
SITE = Path(r"D:\tt-scratch\edgeai\site")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".mjs")


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), functools.partial(H, directory=str(SITE)))
threading.Thread(target=srv.serve_forever, daemon=True).start()

from PIL import Image
from app.services import field_water

server = {}
for n in ("a", "b", "c", "d"):
    server[n] = field_water.water_ratio(Image.open(SITE / "img" / f"{n}.png"))

from playwright.sync_api import sync_playwright

exe = None
import glob, os
c = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1248\chrome-win*\chrome.exe"))
exe = c[0] if c else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe, headless=True)
    pg = b.new_page()
    pg.goto("http://127.0.0.1:8765/index.html")
    res = pg.evaluate("""async () => {
      const out = {};
      for (const n of ["a","b","c","d"]) {
        const blob = await (await fetch(`/img/${n}.png`)).blob();
        const f = new File([blob], n + ".png", {type: "image/png"});
        out[n] = await window.ttFieldCheck(f);
        out[n].margins = await window.ttFieldCheckMargins(f);
      }
      return out;
    }""")
    b.close()
srv.shutdown()
worst = 0.0
for n in ("a", "b", "c", "d"):
    d = abs(res[n]["ratio"] - server[n])
    worst = max(worst, d)
    print(f"{n}: máy chủ {server[n]:.3f} · trên máy {res[n]['ratio']:.3f} ({res[n]['ms']} ms) · lệch {d:.3f}")
print("lệch lớn nhất", round(worst, 3))
import numpy as np
for n in ("a", "b", "c", "d"):
    lg = field_water._session().run(None, {"image": field_water._tensor(Image.open(SITE / "img" / f"{n}.png"))})[0][0]
    ms = (lg[1] - lg[0]).ravel()
    mw = np.array(res[n]["margins"])
    agree = float(((ms > 0) == (mw > 0)).mean())
    print(f"{n}: biên logit tương quan {np.corrcoef(ms, mw)[0,1]:.4f} · lệch TB {np.abs(ms-mw).mean():.3f} · cùng nhãn {agree:.4f} · biên máy chủ [{ms.min():.1f}, {ms.max():.1f}]")
