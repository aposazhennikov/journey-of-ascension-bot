"""Render a posed body variant (PIL, orthographic, painter's algorithm) with the meridian points.

Usage:
    python3 -I preview_pose.py --body padmasana --hand gyan --variant female --view front --out /tmp/x.png
    python3 -I preview_pose.py --all <out_dir>      # every body pose (front+left), every mudra (close-ups),
                                                    # and the three variants side by side
Points come from webapp/assets/points3d.json: stored tri/bary when present, otherwise the point
(and its mirror) is projected onto the neutral mesh once; then it is evaluated on the posed mesh
as w0*v[t0] + w1*v[t1] + w2*v[t2], exactly like the page does.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import posekit as pk  # noqa: E402

SKIN, EYE = (226, 196, 174), (245, 245, 245)
PCOL = (200, 40, 40)


def compose(poses, body, hand, variant):
    b = poses["body"][body]
    h = poses["hand"][hand]
    loc = {k: np.array(v) for k, v in b["rot"][variant].items()}
    if hand != "open" and "arms" not in h and variant in b.get("mudraArms", {}):
        loc.update({k: np.array(v) for k, v in b["mudraArms"][variant].items()})   # same rule as pose.js
    if "arms" in h:
        loc.update({k: np.array(v) for k, v in h["arms"][variant].items()})
    own = b.get("openRot", {}).get(variant) if hand == "open" else None   # same rule as pose.js: lotus dhyana
    for k, q in (own or h["rot"][variant]).items():
        loc[k] = np.array(q)
        loc[k.replace(".L", ".R")] = pk.qmirror(np.array(q))
    return loc, np.array(b["root"][variant])


class Scene:
    def __init__(self, variant, poses_path=pk.ASSETS / "poses.json"):
        self.rig = pk.Rig()
        self.poses = json.loads(Path(poses_path).read_text(encoding="utf-8"))
        self.variant = variant
        self.prims = pk.load_glb(pk.GLB[variant])
        neutral = pk.load_glb(pk.GLB["neutral"])[0]
        self.points = pk.load_points(rest_pos=neutral[0], tris=neutral[1])

    def pose(self, body, hand):
        loc, root = compose(self.poses, body, hand, self.variant)
        Q, H = self.rig.fk(self.variant, loc, root)
        skin = self.rig.skin(self.prims[0][0], self.variant, Q, H)
        eyes = [self.rig.rigid(p, self.rig.eye_bone, Q, H, self.variant) for p, _ in self.prims[1:]]
        return skin, eyes, Q, H

    def meshes(self, skin, eyes, offset=(0, 0, 0)):
        off = np.asarray(offset, float)
        m = [(skin + off, self.prims[0][1], SKIN)]
        m += [(e + off, t, EYE) for e, (_, t) in zip(eyes, self.prims[1:])]
        return m

    def point_marks(self, skin, view, offset=(0, 0, 0)):
        v, _, _ = pk.view_basis(view)
        tris = self.prims[0][1]
        caster = None
        try:
            from meshlib import RayCaster
            caster = RayCaster(skin, tris)
        except Exception:  # noqa: BLE001
            pass
        marks = []
        for code, t, bary in self.points:
            p = pk.point_on_mesh(skin, tris, t, bary)
            a, b, c = skin[tris[t]]
            n = np.cross(b - a, c - a)
            n /= np.linalg.norm(n) + 1e-12
            vis = True if caster is None else caster.first_hit(p + n * 0.002, v) is None
            marks.append((p + offset, PCOL, vis))
        return marks


def hand_box(skin, rig, side="L", pad=0.02, other=False):
    dom = np.array(rig.names)[rig.joints[np.arange(len(skin)), rig.weights.argmax(1)]]
    base = np.array([n.split(".")[0] for n in dom])
    hand = np.isin(base, ["wrist"] + [f"finger{k}-{j}" for k in range(1, 6) for j in range(1, 4)] +
                   [f"metacarpal{k}" for k in range(1, 5)])
    if not other:
        hand &= np.array([n.endswith("." + side) for n in dom])
    p = skin[hand]
    return p.min(axis=0) - pad, p.max(axis=0) + pad


def render_one(sc, body, hand, view, out, region="full", size=800, title=None):
    skin, eyes, Q, H = sc.pose(body, hand)
    bbox = None
    if region == "hand":
        bbox = hand_box(skin, sc.rig)
    elif region == "hands":
        bbox = hand_box(skin, sc.rig, other=True)
    marks = sc.point_marks(skin, view)
    pk.render(sc.meshes(skin, eyes), view, out, size=size, bbox=bbox, points=marks, title=title)
    return skin


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body", default="stand")
    ap.add_argument("--hand", default="open")
    ap.add_argument("--variant", default="neutral")
    ap.add_argument("--view", default="front")
    ap.add_argument("--region", default="full", choices=["full", "hand", "hands"])
    ap.add_argument("--size", type=int, default=800)
    ap.add_argument("--out")
    ap.add_argument("--all", metavar="OUT_DIR")
    ap.add_argument("--part", choices=["body", "hand", "variants"], help="with --all: only this group")
    args = ap.parse_args()
    if not args.all:
        render_one(Scene(args.variant), args.body, args.hand, args.view, args.out, args.region, args.size,
                   f"{args.variant} {args.body} + {args.hand} ({args.view})")
        print("saved", args.out)
        return
    out = Path(args.all)
    out.mkdir(parents=True, exist_ok=True)
    sc = Scene(args.variant)
    if args.part in (None, "body"):
        for body in sc.poses["body"]:
            hand = sc.poses["body"][body].get("defaultHand", "open")
            for view in ("front", "left"):
                f = out / f"body_{body}_{view}.png"
                render_one(sc, body, hand, view, f, size=700, title=f"{args.variant} {body} ({view})")
                print("saved", f)
    if args.part in (None, "hand"):
        for hand in sc.poses["hand"]:
            if hand in ("anjali", "hakini"):
                for view in ("front", "left"):
                    f = out / f"hand_{hand}_{view}.png"
                    render_one(sc, "sukhasana", hand, view, f, region="hands", size=600, title=f"{hand} ({view})")
                    print("saved", f)
                continue
            for view in ("top", "left"):
                f = out / f"hand_{hand}_{view}.png"
                render_one(sc, "sukhasana", hand, view, f, region="hand", size=500, title=f"{hand} ({view})")
                print("saved", f)
            f = out / f"hand_{hand}_stand_palm.png"
            render_one(sc, "stand", hand, "right", f, region="hand", size=500, title=f"{hand} stand (from medial)")
    if args.part in (None, "variants"):
        meshes, marks = [], []
        for i, variant in enumerate(("female", "neutral", "male")):
            s = Scene(variant)
            skin, eyes, _, _ = s.pose("padmasana", "gyan")
            off = np.array([(i - 1) * 0.9, 0, 0])
            meshes += s.meshes(skin, eyes, off)
            marks += s.point_marks(skin, "front", off)
        pk.render(meshes, "front", out / "variants_padmasana_front.png", size=1100, points=marks)
        meshes = []
        for i, variant in enumerate(("female", "neutral", "male")):
            s = Scene(variant)
            skin, eyes, _, _ = s.pose("stand", "open")
            meshes += s.meshes(skin, eyes, [(i - 1) * 1.1, 0, 0])
        pk.render(meshes, "front", out / "variants_stand_front.png", size=1100)
        print("saved variants")


if __name__ == "__main__":
    main()
