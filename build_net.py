"""把雙北的步行路網預先打包成小塊，跟網站一起放在 GitHub Pages。

網頁在雙北範圍內直接讀 net/ 的檔案，不必等公用的 Overpass 伺服器（常常忙碌或故障）；範圍外才用 Overpass。
篩選條件和網頁裡的 Overpass 查詢相同：
  way["highway"~"^(trunk|...|track)$"]["foot"!="no"]["access"!~"^(private|no)$"]，以及紅綠燈節點

用法：
  1. 下載 https://download.geofabrik.de/asia/taiwan-latest.osm.pbf 到 cache/
  2. pip install osmium
  3. python build_net.py
輸出：net/index.json、net/<i>_<j>.json（每塊 0.02°，約 2 km）

每塊的格式（為了省空間，不用 Overpass 原本的 JSON）：
  n: 節點 [[id 與前一個的差, 緯度×1e6 − 塊的南緣, 經度×1e6 − 塊的西緣], ...]（依 id 排序）
  w: 道路 [[道路 id, 種類代碼, [節點在 n 裡的索引...]], ...]；代碼 = HW 的索引，人行道（footway=sidewalk）再 +100
     長的道路只存經過這一塊的那幾段（同一條路在不同塊裡各存一段，靠共用的節點 id 接起來）
  s: 紅綠燈節點在 n 裡的索引
"""
import json
import math
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import osmium

PBF = "cache/taiwan-latest.osm.pbf"
OUT = Path("net")
TILE = 0.02
BBOX = (24.67, 121.28, 25.30, 122.01)  # 南、西、北、東：雙北（含一點桃園、基隆、宜蘭邊界）
HW = ["trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
      "residential", "living_street", "service", "pedestrian", "footway", "path", "steps", "cycleway", "track"]
HW_IDX = {h: i for i, h in enumerate(HW)}
NO_ACCESS = re.compile(r"^(private|no)$")


def tile_of(lat, lon):
    return math.floor(lat / TILE), math.floor(lon / TILE)


def inside(lat, lon, pad=0.01):
    s, w, n, e = BBOX
    return s - pad <= lat <= n + pad and w - pad <= lon <= e + pad


class Collector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.loc = {}  # 用到的節點 id → (lat, lon)
        self.signals = set()
        self.ways = []  # (id, 代碼, [節點 id])
        self.tiles = defaultdict(lambda: defaultdict(set))  # 塊 → 道路在 self.ways 的索引 → 經過這塊的路段編號

    def node(self, n):
        t = n.tags
        if (t.get("highway") == "traffic_signals" or t.get("crossing") == "traffic_signals") and inside(n.location.lat, n.location.lon):
            self.signals.add(n.id)

    def way(self, w):
        t = w.tags
        h = t.get("highway")
        if h not in HW_IDX or t.get("foot") == "no" or NO_ACCESS.match(t.get("access", "")):
            return
        try:
            pts = [(nd.ref, nd.location.lat, nd.location.lon) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if not any(inside(la, lo) for _, la, lo in pts):
            return
        k = len(self.ways)
        self.ways.append((w.id, HW_IDX[h] + (100 if t.get("footway") == "sidewalk" else 0), [r for r, _, _ in pts]))
        for r, la, lo in pts:
            self.loc[r] = (la, lo)
        # 道路經過的每一塊都要收（長路段每 500 m 取點，避免跨過整塊卻沒有節點落在裡面）
        for seg, ((_, a1, o1), (_, a2, o2)) in enumerate(zip(pts, pts[1:])):
            n = max(1, int(math.hypot(a2 - a1, (o2 - o1) * 0.9) / 0.0045))
            for j in range(n + 1):
                la, lo = a1 + (a2 - a1) * j / n, o1 + (o2 - o1) * j / n
                if inside(la, lo, 0):
                    self.tiles[tile_of(la, lo)][k].add(seg)


def main():
    t0 = time.time()
    c = Collector()
    c.apply_file(PBF, locations=True, idx="flex_mem")
    print(f"讀取完成：{len(c.ways):,} 條道路、{len(c.loc):,} 個節點、{len(c.signals):,} 個紅綠燈、{len(c.tiles)} 塊（{time.time() - t0:.0f} 秒）")

    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    total = 0
    for (i, j), segs in sorted(c.tiles.items()):
        # 每條路只留經過這塊的路段，連續的路段接成一段
        pieces = []
        for k, ss in sorted(segs.items()):
            ss = sorted(ss)
            run = [ss[0]]
            for a in ss[1:] + [None]:
                if a is not None and a == run[-1] + 1:
                    run.append(a)
                    continue
                pieces.append((c.ways[k][0], c.ways[k][1], c.ways[k][2][run[0]:run[-1] + 2]))
                if a is not None:
                    run = [a]
        ids = sorted({r for _, _, nd in pieces for r in nd})
        pos = {r: n for n, r in enumerate(ids)}
        nodes, prev = [], 0
        la0, lo0 = round(i * TILE * 1e6), round(j * TILE * 1e6)
        for r in ids:
            la, lo = c.loc[r]
            nodes.append([r - prev, round(la * 1e6) - la0, round(lo * 1e6) - lo0])
            prev = r
        ways = [[wid, h, [pos[r] for r in nd]] for wid, h, nd in pieces]
        sig = [pos[r] for r in ids if r in c.signals]
        text = json.dumps({"n": nodes, "w": ways, "s": sig}, separators=(",", ":"))
        (OUT / f"{i}_{j}.json").write_text(text, encoding="utf-8")
        total += len(text)
    s, w, n, e = BBOX
    (OUT / "index.json").write_text(json.dumps({"v": date.today().isoformat(), "tile": TILE, "bbox": [s, w, n, e],
                                                "hw": HW, "tiles": [f"{i}_{j}" for i, j in sorted(c.tiles)]}, separators=(",", ":")),
                                    encoding="utf-8")
    print(f"輸出 {len(c.tiles)} 塊，共 {total / 1e6:.1f} MB（GitHub Pages 會再 gzip 壓縮），{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
