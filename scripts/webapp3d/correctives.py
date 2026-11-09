"""Contact correctives: soft tissue giving way where rigid skinned parts press into each other.

Dual-quaternion skinning moves every part rigidly, so where a calf folds onto the thigh or a lotus foot
rests on the opposite thigh the skins pass through each other (dark notches at the knees, a foot that
can only lie where the thigh is thin). For every body pose we precompute, on the posed mesh, how far each
skin vertex has to move so it no longer lies inside the part pressing on it, spread that over the
neighbourhood (a dent, not a spike), and store the displacements per pose and body:

    poses.json  body[pid].corr[variant] = {"i": [vertex ids], "d": [dx, dy, dz, ...]}  (metres, world axes)

pose.js adds them after skinning (blended with the pose transition), check_poses.py measures the
corrected mesh. Pairs are leg-on-leg contacts only, so the hand pose does not matter.

    python3 correctives.py [--poses-file poses.json] [--variants ...] [--poses ...]
"""
import argparse
import json
from pathlib import Path

import numpy as np

import posekit as pk
from check_poses import Body, compose, surface_sd, vertex_normals

SIDES = ("L", "R")
OTHER = {"L": "R", "R": "L"}

# (pressing part, soft part, share of the overlap the soft part takes): a foot is bony and stays, the
# thigh under it gives way; calf and thigh at the knee fold share it
PAIRS = []
for s in SIDES:
    o = OTHER[s]
    # ... and the toes flatten onto the thigh where a thin toe went into it (no thigh skin inside the toe
    # to dent: five male toe vertices stayed 4 cm in)
    PAIRS += [(f"foot{s}", f"thigh{o}", 1.0), (f"foot{s}", f"shin{o}", 1.0), (f"thigh{o}", f"foot{s}", 1.0),
              (f"shin{s}", f"thigh{s}", 0.5), (f"thigh{s}", f"shin{s}", 0.5)]
PAIRS += [("shinL", "shinR", 0.5), ("shinR", "shinL", 0.5), (f"footL", "footR", 0.5), ("footR", "footL", 0.5)]

CORR_DOC = ("body[pid].corr[variant]: correctives added after skinning (delta mush on the legs and hips, soft "
            "tissue giving way at leg-on-leg contacts), vertex ids 'i' and world displacements 'd' (x, y, z per "
            "vertex, metres); blended with the pose transition")
MAX_PUSH = 0.03      # deeper than this is not soft tissue, leave it (and the check reports it)
SPREAD = 6            # smoothing passes the dent fades over
EPS = 0.0015          # end a little outside the pressing surface
FACING = -0.3         # contact only where the two skins face each other (normals opposed): along the
                      # knee, where thigh and calf skin are one continuous surface, the inside test fired
                      # and the first try pushed the knees into lumps


def adjacency(tris, n):
    nb = [set() for _ in range(n)]
    for a, b, c in tris:
        nb[a].update((b, c))
        nb[b].update((a, c))
        nb[c].update((a, b))
    return [np.fromiter(s, dtype=np.int64) for s in nb]


def part_normals_at(b, pos, nrm, A, pts, k=4):
    """Mean normal of the k nearest vertices of part A to each point."""
    PA = pos[A]
    d2 = ((pts[:, None, :] - PA[None, :, :]) ** 2).sum(-1)
    j = np.argpartition(d2, k, axis=1)[:, :k]
    n = nrm[A][j].mean(1)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def contact_deltas(b, pos, adj):
    """Displacements (n x 3) that take soft skin out of the parts pressing on it."""
    n = len(pos)
    delta = np.zeros((n, 3))
    nrm = vertex_normals(pos, b.tris)
    for A_name, B_name, share in PAIRS:
        A, B = b.sets[A_name], b.sets[B_name]
        sd = surface_sd(b, pos, nrm, B, A)             # soft vertices inside the pressing part: < 0
        inside = (sd < -0.0005) & (sd > -MAX_PUSH - 0.01)
        if not inside.any():
            continue
        idx = B[inside]
        na = part_normals_at(b, pos, nrm, A, pos[idx])
        facing = (nrm[idx] * na).sum(1) < FACING
        idx, na, depth = idx[facing], na[facing], -sd[inside][facing]
        push = na * (np.minimum(depth, MAX_PUSH) + EPS)[:, None] * share
        # several pairs on one vertex: keep the largest push per axis direction, not the sum
        for v, p in zip(idx, push):
            if np.linalg.norm(p) > np.linalg.norm(delta[v]):
                delta[v] = p
    fixed = np.linalg.norm(delta, axis=1) > 0
    # spread: smooth the displacement field over the soft parts so the skin dents instead of spiking;
    # the vertices that were inside keep at least their own push
    soft = np.zeros(n, bool)
    for _A, B_name, _s in PAIRS:
        soft[b.sets[B_name]] = True
    region = np.flatnonzero(soft)
    cur = delta.copy()
    for _ in range(SPREAD):
        nxt = cur.copy()
        for v in region:
            nb = adj[v]
            m = 0.5 * cur[v] + 0.5 * cur[nb].mean(0)
            nxt[v] = cur[v] if (fixed[v] and np.linalg.norm(cur[v]) >= np.linalg.norm(m)) else m
        cur = nxt
    return cur


class DeltaMush:
    """Delta mush on the legs and hips: the posed mesh is smoothed and the rest-pose skin detail, stored in
    local frames of the smoothed rest mesh, is added back. It removes what rigid skinning does at a deep
    fold (the side of the knee pinched into a slit, thin spikes along the knee edge, the crumpled shin)
    while keeping the shape. Only the leg/hip region moves, faded out over a few rings at its border."""

    def __init__(self, b, adj, iters=14, lam=0.5):
        n = len(b.rest)
        self.b = b
        self.adj, self.iters, self.lam = adj, iters, lam
        e = set()
        for a, c, d in b.tris:
            e.update(((a, c), (c, a), (c, d), (d, c), (a, d), (d, a)))
        e = np.array(sorted(e))
        self.src, self.dst = e[:, 0], e[:, 1]
        self.deg = np.bincount(self.src, minlength=n).astype(float)
        self.first = np.array([nb[0] if len(nb) else i for i, nb in enumerate(adj)])
        self.tris = b.tris
        legs = np.zeros(n, bool)
        for s in SIDES:
            legs[b.sets[f"thigh{s}"]] = legs[b.sets[f"shin{s}"]] = True
        legs[b.buttock] = True
        # the pelvis and the lower trunk too: the skin over the hip crease and the lower belly stretched
        # 2.2-2.8 x in the seated poses on the male body
        hipy = b.P("upperleg01.L")[1]
        low_trunk = np.isin(b.region, ["hips", "torso"]) & (b.rest[:, 1] < hipy + 0.16)
        legs |= low_trunk
        # weight 1 inside the region, fading to 0 over 4 rings outside it (no seam at the border)
        w = legs.astype(float)
        ring = legs.copy()
        for r in range(4):
            nxt = ring.copy()
            for v in np.flatnonzero(ring):
                nxt[adj[v]] = True
            new = nxt & ~ring
            w[new] = 1.0 - (r + 1) / 5.0
            ring = nxt
        self.w = w
        S = self.smooth(b.rest)
        self.dl = self.to_local(S, b.rest - S)

    def smooth(self, X):
        X = X.copy()
        for _ in range(self.iters):
            acc = np.zeros_like(X)
            np.add.at(acc, self.src, X[self.dst])
            X = X + self.lam * (acc / self.deg[:, None] - X)
        return X

    def frames(self, S):
        nrm = vertex_normals(S, self.tris)
        t = S[self.first] - S
        t = t - nrm * (t * nrm).sum(1, keepdims=True)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
        return t, np.cross(nrm, t), nrm

    def to_local(self, S, d):
        t, bt, n = self.frames(S)
        return np.stack([(d * t).sum(1), (d * bt).sum(1), (d * n).sum(1)], 1)

    def apply(self, P, keep=None):
        """keep: extra points (n x 3) the skin near which must not move (the hands resting on the legs)."""
        S = self.smooth(P)
        t, bt, n = self.frames(S)
        M = S + self.dl[:, :1] * t + self.dl[:, 1:2] * bt + self.dl[:, 2:] * n
        # skin that carries the body stays where the pose put it: smoothing rounded the buttocks off the
        # floor (the body hung 16-27 mm up) and off the heels in vajrasana. Pinned within 1 cm of the
        # floor or of the feet, faded in over the next 4 cm.
        b = self.b
        feet = np.concatenate([b.sets["footL"], b.sets["footR"]])
        # floor pin for the seat only: pinning every vertex near the floor left the lotus knees (2-3 cm up)
        # unsmoothed, cut off and striped
        floor = np.full(len(P), 1.0)
        floor[b.buttock] = P[b.buttock, 1] - P[:, 1].min()
        near_feet = np.full(len(P), 1.0)
        cand = np.flatnonzero(self.w > 0)
        cand = cand[~np.isin(cand, feet)]

        def dist_to(idx, pts):
            out = np.empty(len(idx))
            for s in range(0, len(idx), 2000):
                c = idx[s:s + 2000]
                out[s:s + 2000] = np.sqrt(((P[c][:, None, :] - pts[None, :, :]) ** 2).sum(-1).min(1))
            return out
        # the seat on the heels (vajrasana); not every vertex near a foot: the lotus feet lie by the knees
        # and pinned them unsmoothed
        seat = cand[np.isin(cand, b.buttock)]
        near_feet[seat] = dist_to(seat, P[feet][::3])
        if keep is not None and len(keep):
            # the skin under the hands too: rounding the knee lowered it 18 mm under the male palm
            near_feet[cand] = np.minimum(near_feet[cand], dist_to(cand, keep))
        dist = np.minimum(floor, near_feet)
        pin = np.clip((dist - 0.01) / 0.04, 0.0, 1.0)
        return P + (M - P) * (self.w * pin)[:, None]


def pose_corrective(rig, b, adj, poses, variant, pid, mush=None):
    local, root, _ = compose(poses, variant, pid, "open")
    Q, H = rig.fk(variant, local, root)
    pos = rig.skin(b.rest, variant, Q, H)
    # hands that rest on the legs in this pose: the open hand and, where the pose has them, the mudra arms
    hands = np.concatenate([b.sets["handL"], b.sets["handR"]])
    keep = [pos[hands][::4]]
    if poses["body"][pid].get("mudraArms"):
        lm, rm, _ = compose(poses, variant, pid, "gyan")
        Qm, Hm = rig.fk(variant, lm, rm)
        keep.append(rig.skin(b.rest, variant, Qm, Hm)[hands][::4])
    P = mush.apply(pos, np.concatenate(keep)) if mush is not None else pos
    d = (P - pos) + contact_deltas(b, P, adj)
    idx = np.flatnonzero(np.linalg.norm(d, axis=1) > 3e-4)
    return {"i": idx.tolist(), "d": [round(float(v), 4) for v in d[idx].ravel()]}, float(np.linalg.norm(d, axis=1).max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses-file", default=str(pk.ASSETS / "poses.json"))
    ap.add_argument("--variants", nargs="*", default=["neutral", "female", "male"])
    ap.add_argument("--poses", nargs="*", default=["vrikshasana", "sukhasana", "ardha_padmasana", "padmasana", "vajrasana", "dandasana"])
    args = ap.parse_args()
    path = Path(args.poses_file)
    poses = json.loads(path.read_text(encoding="utf-8"))
    rig = pk.Rig()
    for variant in args.variants:
        b = Body(rig, variant)
        adj = adjacency(b.tris, len(b.rest))
        mush = DeltaMush(b, adj)
        for pid in args.poses:
            corr, mx = pose_corrective(rig, b, adj, poses, variant, pid, mush)
            poses["body"][pid].setdefault("corr", {})[variant] = corr
            print(variant, pid, "vertices", len(corr["i"]), "max push %.1f mm" % (mx * 1000), flush=True)
    poses["corr"] = CORR_DOC
    path.write_text(json.dumps(poses, separators=(",", ":")), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
