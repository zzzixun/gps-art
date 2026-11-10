"""把 city-shapes 掃描全大台北找到的「每個範本最像的 3 個位置」轉成網頁用的 recommended.js。

掃描方法見 city-shapes 的 scan_report.py（132 個中心點 × 17 個範本，目標 10 km）。
用法：python build_recommended.py ../06-city-shapes/out/scan/best.json
"""
import json
import sys
from pathlib import Path

from build_routes import TOLERANCE_M, simplify

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent

best = json.load(open(sys.argv[1], encoding="utf-8"))
rec = [{"k": k, "rank": i + 1, "area": r["area"], "c": [[round(a, 6), round(b, 6)] for a, b in simplify(r["coords"], TOLERANCE_M)]}
       for k, rs in best.items() for i, r in enumerate(rs)]
(HERE / "recommended.js").write_text("window.RECOMMENDED = " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
print(f"已寫入 recommended.js（{len(rec)} 條、{sum(len(r['c']) for r in rec):,} 點）")
