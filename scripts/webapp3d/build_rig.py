"""Build webapp/assets/rig.json: a compact skeleton + skin weights for linear blend skinning.

Usage: python3 -I build_rig.py <base.obj> <targets_dir> <rig.default.json> <weights.default.json> <out.json>

Source: the MakeHuman "default" rig and weights from mpfb2 (src/mpfb/data/rigs/standard/
rig.default.json + weights.default.json, commit 6ff1eb358f6c1959ced77e79e6dd2406d9a71f49),
CC0 1.0 per the repository's LICENSE.ASSETS.md and the "license": "CC0" field of the weights file.

Joint positions are recomputed from the rig's own vertex-based definitions
(CUBE = mean of a joint-* helper group of base.obj, VERTEX = one vertex, MEAN = mean of
vertex indices) on each body variant (neutral / female / male, see build_variants.py),
so the skeleton fits every shape.  Face, tongue, breast and toe bones are folded into their
nearest kept ancestor (their weights move there), leaving body + finger bones.

Output (all positions in glb metres, +x = body's left, +y up, +z front):
  bones[i] = {name, parent (index or -1), head: {variant: [x,y,z]}, tail: {variant: [x,y,z]}}
  bones are ordered so a parent always precedes its children.
  joints / weights: flat arrays, 4 influences per skin vertex in glb vertex order
  (primitive 0); weights are uint8 summing to exactly 255 per vertex.
  eyeBone: index of the bone the eye primitives follow rigidly (head).
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_body import triangulate  # noqa: E402
from build_variants import VARIANTS, variant_world  # noqa: E402

DROP_PREFIX = ("breast", "eye", "jaw", "levator", "oculi", "orbicularis", "oris", "risorius",
               "special", "temporalis", "tongue", "toe")
INFL = 4


def keep_bone(name):
    return not name.startswith(DROP_PREFIX)


def end_position(spec, world, groups):
    s = spec["strategy"]
    if s == "CUBE":
        ids = np.unique(np.concatenate([np.asarray(f) for f in groups[spec["cube_name"]]]))
        return world[ids].mean(axis=0)
    if s == "VERTEX":
        return world[spec["vertex_index"]]
    if s == "MEAN":
        return world[np.array(spec["vertex_indices"])].mean(axis=0)
    raise ValueError(s)


def main():
    base_obj, targets_dir, rig_path, weights_path, out_path = (Path(a) for a in sys.argv[1:6])
    rig = json.loads(rig_path.read_text(encoding="utf-8"))
    wdata = json.loads(weights_path.read_text(encoding="utf-8"))
    assert wdata.get("license") == "CC0"

    parent = {n: (b.get("parent") or None) for n, b in rig.items()}

    def kept_ancestor(n):
        while n is not None and not keep_bone(n):
            n = parent[n]
        return n

    # order: parents first (DFS from roots), keep only kept bones
    children = {}
    for n in rig:
        children.setdefault(parent[n], []).append(n)
    order = []

    def visit(n):
        if keep_bone(n):
            order.append(n)
        for c in sorted(children.get(n, [])):
            visit(c)
    for r in sorted(children[None]):
        visit(r)
    index = {n: i for i, n in enumerate(order)}

    # positions per variant
    heads = {n: {} for n in order}
    tails = {n: {} for n in order}
    groups = None
    for variant in VARIANTS:
        world, groups = variant_world(base_obj, targets_dir, variant)
        for n in order:
            heads[n][variant] = np.round(end_position(rig[n]["head"], world, groups), 5).tolist()
            tails[n][variant] = np.round(end_position(rig[n]["tail"], world, groups), 5).tolist()

    # glb vertex k = k-th smallest original index of group "body"
    body_idx = np.unique(triangulate(groups["body"]))
    remap = -np.ones(int(body_idx.max()) + 1 + 100000, dtype=np.int64)
    remap[body_idx] = np.arange(len(body_idx))
    nv = len(body_idx)
    dense = np.zeros((nv, len(order)), dtype=np.float64)
    skipped = 0
    for bname, lst in wdata["weights"].items():
        target = kept_ancestor(bname)
        if target is None:
            continue
        col = index[target]
        for vi, w in lst:
            k = remap[vi] if vi < len(remap) else -1
            if k < 0:
                skipped += 1
                continue
            dense[k, col] += w
    empty = np.where(dense.sum(axis=1) <= 0)[0]
    print("bones kept", len(order), "of", len(rig), "| weight entries outside skin", skipped, "| unweighted verts", len(empty))
    if len(empty):  # give them the weights of the nearest weighted vertex (neutral mesh)
        world, _ = variant_world(base_obj, targets_dir, "neutral")
        pos = world[body_idx]
        good = np.where(dense.sum(axis=1) > 0)[0]
        for k in empty:
            j = good[np.argmin(np.linalg.norm(pos[good] - pos[k], axis=1))]
            dense[k] = dense[j]

    top = np.argsort(-dense, axis=1)[:, :INFL]
    tw = np.take_along_axis(dense, top, axis=1)
    tw /= tw.sum(axis=1, keepdims=True)
    q = np.floor(tw * 255).astype(np.int64)
    rem = 255 - q.sum(axis=1)
    frac = tw * 255 - q
    for k in np.where(rem > 0)[0]:  # largest-remainder rounding so each row sums to 255
        for j in np.argsort(-frac[k])[: rem[k]]:
            q[k, j] += 1
    top[q == 0] = 0
    assert np.all(q.sum(axis=1) == 255)
    lost = 1 - np.take_along_axis(dense / dense.sum(axis=1, keepdims=True), np.argsort(-dense, axis=1)[:, :INFL], axis=1).sum(axis=1)
    print(f"weight mass dropped by top-{INFL}: mean {lost.mean():.4f} max {lost.max():.4f}")

    bones = []
    for n in order:
        p = kept_ancestor(parent[n])
        bones.append({"name": n, "parent": index[p] if p else -1, "head": heads[n], "tail": tails[n]})
    out = {
        "version": 1,
        "source": "MakeHuman default rig + weights (mpfb2, CC0), joints refit per body variant",
        "units": "metres; +x body's left, +y up, +z front (same frame as body*.glb)",
        "variants": list(VARIANTS),
        "vertexCount": nv,
        "influences": INFL,
        "weightScale": 255,
        "eyeBone": index["head"],
        "bones": bones,
        "joints": top.reshape(-1).tolist(),
        "weights": q.reshape(-1).tolist(),
    }
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("wrote", out_path, out_path.stat().st_size, "bytes")
    for b in bones:
        print(f'{b["name"]:<14} parent={order[b["parent"]] if b["parent"] >= 0 else "-":<14} head={b["head"]["neutral"]}')


if __name__ == "__main__":
    main()
