"""Build female / male body variants from the MakeHuman hm08 base mesh and macro targets.

Usage: python3 -I build_variants.py <base.obj> <targets_dir> <out_dir>

<targets_dir> holds the MakeHuman (mpfb2, CC0) macro targets
    macrodetails/{african,asian,caucasian}-{female,male}-young.target.gz
    macrodetails/universal-{female,male}-young-averagemuscle-averageweight.target.gz
from https://github.com/makehumancommunity/mpfb2/tree/master/src/mpfb/data/targets/macrodetails
(fetched at commit 6ff1eb358f6c1959ced77e79e6dd2406d9a71f49; LICENSE.ASSETS.md of that
repository: CC0 1.0 Universal).

The macro settings follow MakeHuman's own modifier maths for an adult (age 25 -> "young" = 1),
average muscle and weight (universal-*-averagemuscle-averageweight, which is an empty target),
average height and proportions (no target) and an even race mix (1/3 each):
    female = base + sum_race 1/3 * <race>-female-young + universal-female-young-avg-avg
    male   = base + sum_race 1/3 * <race>-male-young   + universal-male-young-avg-avg
The neutral body.glb (written by build_body.py) is the raw base mesh and stays the reference.

Writes <out_dir>/body_female.glb and <out_dir>/body_male.glb with exactly the same primitives,
vertex order and triangle order as body.glb (build_body.py's triangulation and compaction),
so points3d.json "tri"/"bary" stay valid on every variant.
Transform: the variant's own feet go to y=0; x/z use the neutral body's centre so the
bodies overlap when switching.
"""
import gzip
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_body import KEEP, SCALE, compact, parse_obj, triangulate, vertex_normals, write_glb  # noqa: E402

RACES = ("african", "asian", "caucasian")
VARIANTS = ("neutral", "female", "male")


def read_target(path):
    idx, delta = [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 4 or line.startswith("#"):
                continue
            idx.append(int(parts[0]))
            delta.append([float(x) for x in parts[1:]])
    return np.array(idx, dtype=np.int64), np.array(delta, dtype=np.float64).reshape(-1, 3)


def morph(verts, targets_dir, gender):
    out = verts.copy()
    tdir = Path(targets_dir)
    weights = {f"{race}-{gender}-young.target.gz": 1.0 / len(RACES) for race in RACES}
    weights[f"universal-{gender}-young-averagemuscle-averageweight.target.gz"] = 1.0
    for name, w in weights.items():
        idx, delta = read_target(tdir / name)
        if len(idx):
            out[idx] += w * delta
    return out


def world_transform(verts, groups, ref_verts=None):
    """Same transform as build_body.py: feet at y=0, x/z centred, decimeters -> meters.
    With ref_verts the x/z centre is taken from the reference (neutral) mesh."""
    body_idx = np.unique(triangulate(groups["body"]))
    body = verts[body_idx]
    ref = body if ref_verts is None else ref_verts[body_idx]
    center = np.array([(ref[:, 0].min() + ref[:, 0].max()) / 2, body[:, 1].min(),
                       (ref[:, 2].min() + ref[:, 2].max()) / 2])
    return (verts - center) * SCALE


def variant_world(base_obj, targets_dir, variant):
    """All base.obj vertices (original indexing, incl. helpers/joint cubes) in glb world space."""
    verts, groups = parse_obj(base_obj)
    if variant == "neutral":
        return world_transform(verts, groups), groups
    return world_transform(morph(verts, targets_dir, variant), groups, ref_verts=verts), groups


def build_prims(world, groups):
    prims = []
    for gname, kind in KEEP.items():
        tris = triangulate(groups[gname])
        pos, ltris = compact(world, tris)
        prims.append((gname, 0 if kind == "skin" else 1, pos, vertex_normals(pos, ltris), ltris))
    return prims


def main():
    base_obj, targets_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    neutral, groups = variant_world(base_obj, targets_dir, "neutral")
    ref_prims = build_prims(neutral, groups)
    for variant in ("female", "male"):
        world, _ = variant_world(base_obj, targets_dir, variant)
        prims = build_prims(world, groups)
        for (n, _, p0, _, t0), (_, _, p1, _, t1) in zip(ref_prims, prims):
            assert p0.shape == p1.shape and np.array_equal(t0, t1), n
        path = out_dir / f"body_{variant}.glb"
        write_glb(path, prims)
        skin = prims[0][2]
        d = np.linalg.norm(skin - ref_prims[0][2], axis=1)
        print(f"{variant}: {path.name} {path.stat().st_size} bytes, height {skin[:, 1].max():.4f} m, "
              f"bbox x {skin[:, 0].min():.3f}..{skin[:, 0].max():.3f} z {skin[:, 2].min():.3f}..{skin[:, 2].max():.3f}, "
              f"|delta| mean {d.mean() * 1000:.1f} mm max {d.max() * 1000:.1f} mm")


if __name__ == "__main__":
    main()
