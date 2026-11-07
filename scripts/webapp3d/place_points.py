"""Cast the rays from specs/*.py against the body and write points3d.json.

Usage:
    python3 -I scripts/webapp3d/place_points.py                     # all specs -> webapp/assets/points3d.json
    python3 -I scripts/webapp3d/place_points.py --modules arms --check   # report only, write nothing
    python3 -I scripts/webapp3d/place_points.py --modules arms --out /tmp/arms.json
"""
import argparse
import importlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from placement import ASSETS, RC  # noqa: E402


def load_specs(names=None):
    """Return {module_name: module} for specs/*.py (or only `names`)."""
    available = sorted(p.stem for p in (HERE / "specs").glob("*.py") if p.stem != "__init__")
    chosen = names or available
    unknown = [n for n in chosen if n not in available]
    if unknown:
        raise SystemExit(f"unknown spec modules: {unknown}; available: {available}")
    return {n: importlib.import_module(f"specs.{n}") for n in chosen}


def cast(ray):
    origin, direction = ray
    hit = RC.first_hit_full(origin, direction)
    if hit is None:
        return None
    p, n, tri, (u, v) = hit
    return {
        "p": np.round(p, 4).tolist(),
        "n": np.round(n, 3).tolist(),
        "tri": tri,
        "bary": [round(1 - u - v, 5), round(u, 5), round(v, 5)],
    }


def place(modules):
    points, via, chains, misses, owner = {}, {}, {}, [], {}
    for name, mod in modules.items():
        for code, ray in mod.SPEC.items():
            if code in owner:
                raise SystemExit(f"{code} defined in both {owner[code]} and {name}")
            owner[code] = name
            entry = cast(ray)
            if entry is None:
                misses.append(code)
                continue
            points[code] = entry
        for key, rays in getattr(mod, "VIA", {}).items():
            via[key] = [e for e in (cast(r) for r in rays) if e]
        chains.update(getattr(mod, "CHAINS", {}))
    return points, via, chains, misses


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modules", nargs="*", help="spec module names (default: all)")
    ap.add_argument("--out", default=str(ASSETS / "points3d.json"))
    ap.add_argument("--check", action="store_true", help="print results, do not write")
    args = ap.parse_args()

    points, via, chains, misses = place(load_specs(args.modules))
    for code, e in points.items():
        print(f"{code:6s} p={e['p']} n={e['n']}")
    for code in misses:
        print(f"MISS {code}")
    print(f"placed {len(points)}, missed {len(misses)}")
    if args.check:
        return
    doc = {
        "version": 2,
        "status": "draft",
        "note": ("Left-side draft positions on the MakeHuman hm08 body (meters, y up, +x = body's left, "
                 "+z = front). Mirror x for the right side. tri/bary locate each point on the base mesh "
                 "triangle so it can follow a morphed body."),
        "points": points,
        "via": via,
        "chains": chains,
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", args.out)


if __name__ == "__main__":
    main()
