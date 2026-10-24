"""把 routes/*.gpx、*.kml 轉成網頁可直接載入的 routes.js。

用法：
    1. 到 Garmin / 運動筆記登入後下載 GPX
    2. 依 index.html 的 HOT 清單 id 命名，放進 routes/，例如 routes/east-godzilla.gpx
    3. python build_routes.py
"""
import json
import sys
import math
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
TOLERANCE_M = 3  # Douglas-Peucker 簡化容許誤差（公尺）


def read_gpx(path):
    root = ET.parse(path).getroot()
    pts = [(float(e.get("lat")), float(e.get("lon")))
           for e in root.iter() if e.tag.split("}")[-1] in ("trkpt", "rtept")]
    return pts


def read_kml(path):
    """Google My Maps 匯出的 KML；有多條線時取最長那條（例如吉娃娃的舌頭是另外一筆）"""
    lines = []
    for e in ET.parse(path).getroot().iter():
        if e.tag.split("}")[-1] == "coordinates":
            lines.append([(float(c.split(",")[1]), float(c.split(",")[0])) for c in e.text.split()])
    return max(lines, key=len) if lines else []


def simplify(pts, tol):
    lat0 = pts[0][0]
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    xy = [(lon * kx, lat * ky) for lat, lon in pts]
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = xy[a], xy[b]
        L = math.hypot(x2 - x1, y2 - y1)
        best, idx = 0, None
        for i in range(a + 1, b):
            # 封閉路線起終點重合時，改用到端點的距離
            d = (abs((x2 - x1) * (y1 - xy[i][1]) - (x1 - xy[i][0]) * (y2 - y1)) / L
                 if L else math.hypot(xy[i][0] - x1, xy[i][1] - y1))
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep.add(idx)
            stack += [(a, idx), (idx, b)]
    return [pts[i] for i in sorted(keep)]


routes = {}
for f in sorted((HERE / "routes").iterdir()):
    if f.suffix.lower() not in (".gpx", ".kml"):
        continue
    pts = read_gpx(f) if f.suffix.lower() == ".gpx" else read_kml(f)
    if len(pts) < 2:
        print(f"跳過 {f.name}：沒有軌跡點")
        continue
    small = simplify(pts, TOLERANCE_M)
    routes[f.stem] = [[round(a, 6), round(b, 6)] for a, b in small]
    print(f"{f.stem}: {len(pts)} -> {len(small)} 點")

(HERE / "routes.js").write_text(
    "window.ROUTES = " + json.dumps(routes, separators=(",", ":")) + ";\n", encoding="utf-8")
print(f"已寫入 routes.js（{len(routes)} 條路線）")
