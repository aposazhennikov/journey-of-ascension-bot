"""Render a labelled orthographic preview of placed points (PNG), no browser needed.

Usage:
    python3 -I scripts/webapp3d/preview_points.py --modules arms --view front --region arm --out /tmp/arm.png
Views: front, back, left, right, top, below, palmar, dorsal.
Regions: full, head, torso, arm, hand, leg, foot.
Filled dots are visible from the camera, hollow dots are hidden behind the body.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from meshlib import RayCaster  # noqa: E402
from placement import ELBOW, POS, SHOULDER, TRIS, WRIST, J, _arm_frame, unit  # noqa: E402
from place_points import load_specs, place  # noqa: E402

COLORS = {
    "P": (150, 160, 172), "GI": (110, 122, 138), "E": (211, 154, 18), "RP": (231, 181, 42),
    "C": (224, 82, 58), "IG": (239, 122, 95), "V": (60, 111, 216), "R": (42, 82, 173),
    "MC": (214, 69, 95), "TR": (240, 138, 75), "VB": (47, 158, 80), "F": (31, 122, 60),
    "VG": (142, 91, 214), "VC": (176, 123, 232),
}

REGIONS = {
    "full": ((-0.55, -0.02, -0.25), (0.55, 1.70, 0.25)),
    "head": ((-0.12, 1.39, -0.18), (0.12, 1.69, 0.12)),
    "torso": ((-0.23, 0.74, -0.23), (0.23, 1.46, 0.10)),
    "arm": ((0.10, 0.90, -0.20), (0.53, 1.43, 0.26)),
    "hand": ((0.36, 0.91, 0.02), (0.53, 1.10, 0.24)),
    "leg": ((-0.02, -0.01, -0.23), (0.31, 0.93, 0.07)),
    "foot": ((0.14, -0.01, -0.17), (0.30, 0.14, 0.12)),
}


def view_basis(name):
    _, palmar, _ = _arm_frame(ELBOW, WRIST)
    proximal = unit(ELBOW - WRIST)
    table = {
        "front": ((0, 0, 1), (0, 1, 0)), "back": ((0, 0, -1), (0, 1, 0)),
        "left": ((1, 0, 0), (0, 1, 0)), "right": ((-1, 0, 0), (0, 1, 0)),
        "top": ((0, 1, 0), (0, 0, -1)), "below": ((0, -1, 0), (0, 0, 1)),
        "palmar": (tuple(palmar), tuple(proximal)), "dorsal": (tuple(-palmar), tuple(proximal)),
    }
    v, up = (unit(x) for x in table[name])
    up = unit(up - v * (up @ v))
    return v, up, np.cross(up, v)


def arm_triangles():
    """Triangles of the left arm (to hide it when looking at the trunk from the side)."""
    c = POS[TRIS].mean(axis=1)
    near = np.zeros(len(c), bool)
    for a, b in [(SHOULDER, ELBOW), (ELBOW, WRIST), (WRIST, J["l-finger-3-4"])]:
        ab = b - a
        t = np.clip(((c - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(c - (a + t[:, None] * ab), axis=1)
        near |= d < 0.065
    return near & (c[:, 0] > 0.13)


def chain_edges(codes, chains):
    edges = []
    in_chain = set()
    for chain in chains:
        in_chain.update(chain)
        edges += list(zip(chain, chain[1:]))
    groups = {}
    for code in codes:
        if code in in_chain:
            continue
        m = re.match(r"([A-Za-z]+)(\d+)$", code)
        if m:
            groups.setdefault(m.group(1), []).append((int(m.group(2)), code))
    for items in groups.values():
        items.sort()
        edges += [(a[1], b[1]) for a, b in zip(items, items[1:])]
    return edges


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modules", nargs="*")
    ap.add_argument("--view", default="front")
    ap.add_argument("--region", default="full")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1000)
    ap.add_argument("--no-arm", action="store_true", help="hide the left arm (side views of the trunk)")
    ap.add_argument("--only", help="regex: draw only matching codes")
    args = ap.parse_args()

    modules = load_specs(args.modules)
    points, _, chains, misses = place(modules)
    if args.only:
        points = {k: v for k, v in points.items() if re.match(args.only, k)}

    v, up, right = view_basis(args.view)
    lo, hi = (np.array(x) for x in REGIONS[args.region])
    keep = np.ones(len(TRIS), bool)
    cent = POS[TRIS].mean(axis=1)
    pad = 0.05
    keep &= np.all((cent > lo - pad) & (cent < hi + pad), axis=1)
    if args.no_arm:
        keep &= ~arm_triangles()
    tris = TRIS[keep]
    caster = RayCaster(POS, tris)

    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    sx, sy = corners @ right, corners @ up
    w, h = sx.max() - sx.min(), sy.max() - sy.min()
    scale = (args.size - 40) / max(w, h)
    W, H = int(w * scale) + 40, int(h * scale) + 40

    def to_px(p):
        return (20 + (p @ right - sx.min()) * scale, 20 + (sy.max() - p @ up) * scale)

    img = Image.new("RGB", (W, H), (246, 243, 238))
    draw = ImageDraw.Draw(img)
    tri_pos = POS[tris]
    normals = np.cross(tri_pos[:, 1] - tri_pos[:, 0], tri_pos[:, 2] - tri_pos[:, 0])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    facing = normals @ v
    order = np.argsort(tri_pos.mean(axis=1) @ v)
    light = unit(v + up * 0.5 + right * 0.3)
    for i in order:
        if facing[i] <= 0:
            continue
        shade = 0.45 + 0.55 * max(0.0, float(normals[i] @ light))
        col = tuple(int(c * shade) for c in (226, 196, 174))
        draw.polygon([to_px(q) for q in tri_pos[i]], fill=col)

    font = ImageFont.load_default()
    pts = {k: np.array(e["p"]) for k, e in points.items()}
    nrm = {k: np.array(e["n"]) for k, e in points.items()}
    visible = {k: caster.first_hit(pts[k] + nrm[k] * 0.003, v) is None for k in pts}
    all_chains = [c for chain_list in chains.values() for c in chain_list]
    for a, b in chain_edges(list(pts), all_chains):
        if a in pts and b in pts:
            prefix = re.match(r"[A-Za-z]+", a).group(0)
            draw.line([to_px(pts[a]), to_px(pts[b])], fill=COLORS.get(prefix, (90, 90, 90)), width=1)
    for k, p in pts.items():
        prefix = re.match(r"[A-Za-z]+", k).group(0)
        col = COLORS.get(prefix, (90, 90, 90))
        x, y = to_px(p)
        r = 4
        if visible[k]:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=(30, 30, 30))
            draw.text((x + 6, y - 6), k, fill=(20, 20, 20), font=font)
        else:
            draw.ellipse([x - r, y - r, x + r, y + r], outline=col, width=2)
            draw.text((x + 6, y - 6), k, fill=(150, 150, 150), font=font)
    if misses:
        draw.text((10, 5), "MISS: " + " ".join(misses), fill=(200, 0, 0), font=font)
    img.save(args.out)
    print(f"saved {args.out} ({W}x{H}), points {len(pts)}, hidden {sum(not x for x in visible.values())}, misses {misses}")


if __name__ == "__main__":
    main()
