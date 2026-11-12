"""Numeric acceptance checks for webapp/assets/poses.json (asanas + mudras) on all body variants.

Usage: python3 -I check_poses.py [--variants neutral female male] [--poses padmasana ...]
                                 [--hands gyan ...] [--no-sheets] [--out DIR] [--poses-file PATH]

For every variant x body pose (with its defaultHand, else 'open') and for every hand pose on
sukhasana the pose is composed exactly like webapp/pose.js composePose, skinned with posekit
Rig.skin (dual quaternions) and measured:

  joint angles in an anatomical frame, per side (deg):
    hip: flexion / abduction / external rotation (knee hinge vs. the hinge of a pure swing),
    knee flexion, ankle twist about the shin, shoulder flexion / abduction / humeral rotation
    (external +), elbow flexion, forearm rotation (supination +, 0 = thumb up, measured against
    the elbow hinge), wrist flexion (+) / extension (-), radial (+) / ulnar deviation, wrist twist;
  contacts on the skin: buttocks to floor, knee height, shin crossing in front of the pubis,
    foot on the opposite thigh (gap / sinking), hand on the legs (gap / sinking), anjali palms
    on the mid plane, mudra fingertip contacts, finger fan;
  skin quality: edge stretch p99 (whole body <= 1.5, each body region <= 2.0), forearm
    cross-section area vs. rest. Note the rest pose bends the elbows ~40 deg, so a straight arm
    already stretches the front of the elbow.

Signed distances use the nearest vertex of the other surface and its normal (plane distance
when the point lies over that vertex, else the distance to the vertex), accurate to ~1-2 mm.

Writes DIR/report.json (all numbers, pass/fail per check) and, unless --no-sheets,
DIR/sheets/<variant>_<pose>_<hand>.png (front/back/left/right/top/below).
Exit code 1 if any check fails.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import posekit as pk  # noqa: E402
from posekit import qconj, qmul, qrot, unit  # noqa: E402

ID = np.array([0, 0, 0, 1.0])
SIDES = {"L": 1.0, "R": -1.0}
OTHER = {"L": "R", "R": "L"}
X = np.array([1.0, 0, 0])
VIEWS6 = ["front", "back", "left", "right", "top", "below"]

SEATED = {"sukhasana", "ardha_padmasana", "padmasana", "vajrasana", "dandasana"}
LOTUS = {"padmasana", "ardha_padmasana"}
SHIN_CROSS_MAX = {"padmasana": 0.12, "ardha_padmasana": 0.20, "sukhasana": 0.20}   # m in front of the pubis
KNEE_FLOOR = {"padmasana": (0.03, 0.015), "ardha_padmasana": (0.03, None)}         # max height, max L/R difference
# half lotus: the lower (right) foot lies under the top leg and lifts its knee; the top knee may stand that
# high but has to rest on the foot (with both knees on the floor the rigid foot sat 2-4 cm inside the shin)
HALF_TOP_KNEE = {"side": "L", "max": 0.10, "gap": 0.010, "sink": 0.010}
MUDRA_TARGETS = {"gyan": [2], "prithvi": [4], "shuni": [3], "vyana": [2, 3], "apana": [3, 4]}

LIM = {
    "hip_flex": 125, "hip_abd": 50, "hip_er": 70, "hip_er_lotus": 80, "hip_ir": -45,
    "knee_flex": 160, "knee_hyper": -5, "ankle_twist": 25,
    "humeral_rot": (-70, 90), "elbow_hyper": -10, "pron_sup": (-85, 90),
    "wrist_ext": 80, "wrist_ext_dandasana": 90, "wrist_flex": 80, "wrist_dev": 25, "wrist_twist": 5,
    "buttock_floor": 0.003, "floor_pen": -0.003, "buttock_heel_gap": 0.010,
    "foot_thigh_gap": 0.005, "foot_thigh_sink": 0.010,
    "hand_leg_sink": 0.005, "hand_leg_gap": 0.010, "hand_floor_gap": 0.010, "palm_leg_gap": 0.012,
    # added after the lotus review: forearms went 5 cm into the belly, the hands into each other and the
    # feet were buried in the thighs, and nothing here measured it
    "arm_trunk_pen": 0.006, "hand_hand_pen": 0.004, "foot_top_visible": 0.30,
    # anjali: a real palm has a hollow, so "90 % of the palm within 3 mm of the mid plane" failed on every
    # body from the start and hid the one real defect (a 1.5 cm slit between the neutral palms, median
    # 9 mm per hand; 6 mm shows no slit from above). Measured instead: the median palm offset, and the
    # finger pads (palmar side of fingers 2-5) lying on the other hand
    # pad limits set from renders: 0.70 (female) and 0.47-0.53 (neutral, male) look closed from above
    "anjali_palm_med": 0.007, "anjali_pad_frac": 0.45, "anjali_pad_band": 0.006, "anjali_pen": 0.002,
    # whole-body p99 of edge length / rest; per region (legs, arms, hands, hips, torso, head) a looser
    # limit that still catches local tearing such as the crotch spike (ratio 2-7 there in the lotus)
    "stretch_p99": 1.5, "stretch_p99_region": 2.0, "forearm_area": 0.8,
    "mudra_gap": 0.005, "mudra_free_flex": 20, "finger_fan": 5,
    "hakini_tip_gap": 0.004, "hakini_cross": 0.003, "hakini_palm": 0.03,
    # dandasana: the teacher's 2 cm is not reachable on this mesh - with straight legs the knee joint
    # sits at hip-joint height (~9 cm) and the back of the knee ~5 cm above the floor; 6 cm = straight
    "danda_knee": 5, "danda_leg_gap": 0.05, "danda_popliteal": 0.06, "danda_foot_up": 20,
    # vrikshasana: getting the heel to the upper third of the standing thigh needs ~80 deg of external
    # rotation and ~55 deg of abduction in this angle convention (grid search in the 2026-11-08 audit)
    # the foot centroid hangs 6-8 cm below the heel; with the heel as high as this leg reaches, the
    # centroid sits around mid-thigh - well clear of the knee, which is what the teacher forbids
    "vriksha_hip_flex": 40, "vriksha_foot_height": 0.55, "vriksha_hip_er": 90, "vriksha_hip_abd": 65,
}


# ---------------------------------------------------------------- small math
def qaxis(axis, deg):
    axis = unit(axis)
    h = np.radians(deg) / 2
    return np.array([*(axis * np.sin(h)), np.cos(h)])


def twist_deg(q, axis):
    """Signed twist (deg) of q about axis in the swing-twist split q = swing * twist."""
    axis = unit(axis)
    a = 2 * np.degrees(np.arctan2(np.dot(q[:3], axis), q[3]))
    return float((a + 180) % 360 - 180)


def swing_vec(q, axis):
    """Rotation vector (axis * deg) of the swing part of q (perpendicular to axis)."""
    s = qmul(q, qconj(qaxis(axis, twist_deg(q, axis))))
    if s[3] < 0:
        s = -s
    v = s[:3]
    n = np.linalg.norm(v)
    if n < 1e-12:
        return np.zeros(3)
    return v / n * 2 * np.degrees(np.arctan2(n, s[3]))


def perp(v, axis):
    axis = unit(axis)
    return np.asarray(v, float) - axis * np.dot(v, axis)


def signed_angle(a, b, axis):
    a, b = perp(a, axis), perp(b, axis)
    return float(np.degrees(np.arctan2(np.dot(np.cross(a, b), unit(axis)), np.dot(a, b))))


def angle(a, b):
    return float(np.degrees(np.arccos(np.clip(np.dot(unit(a), unit(b)), -1, 1))))


def vertex_normals(pos, tris):
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    n = np.zeros_like(pos)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln


def hull_area(p):
    """Area of the 2D convex hull (monotone chain)."""
    p = np.unique(np.round(p, 7), axis=0)
    if len(p) < 3:
        return 0.0
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def half(pts):
        h = []
        for q in pts:
            while len(h) >= 2 and np.cross(h[-1] - h[-2], q - h[-2]) <= 0:
                h.pop()
            h.append(q)
        return h
    hull = np.array(half(p)[:-1] + half(p[::-1])[:-1])
    x, y = hull[:, 0], hull[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def plane_basis(axis):
    axis = unit(axis)
    e1 = unit(np.cross(axis, [0, 0, 1.0] if abs(axis[2]) < 0.9 else [1.0, 0, 0]))
    return e1, np.cross(axis, e1)


def nearest(pa, pb, chunk=1024):
    """Index into pb of the nearest point for each of pa, and the squared distance."""
    bb = np.einsum("ij,ij->i", pb, pb)
    idx = np.empty(len(pa), dtype=np.int64)
    d2 = np.empty(len(pa))
    for i in range(0, len(pa), chunk):
        a = pa[i:i + chunk]
        m = np.einsum("ij,ij->i", a, a)[:, None] + bb[None, :] - 2 * a @ pb.T
        j = m.argmin(1)
        idx[i:i + chunk] = j
        d2[i:i + chunk] = np.maximum(m[np.arange(len(a)), j], 0)
    return idx, d2


# ---------------------------------------------------------------- rest-pose model of one body variant
class Body:
    def __init__(self, rig, variant):
        self.rig, self.v = rig, variant
        prim = pk.load_glb(pk.GLB[variant])[0]
        self.rest, self.tris = prim[0], prim[1]
        self.heads, self.tails = rig.heads[variant], rig.tails[variant]
        self.I = rig.index
        names = np.array(rig.names)
        self.dom = names[rig.joints[np.arange(len(self.rest)), rig.weights.argmax(1)]]
        self.base = np.array([n.split(".")[0] for n in self.dom])
        self.side = np.array([n.split(".")[1] if "." in n else "" for n in self.dom])
        hand_bones = {"wrist"} | {n.split(".")[0] for n in rig.names if n.startswith(("finger", "metacarpal"))}
        self.is_hand = np.isin(self.base, list(hand_bones))
        self.rest_n = vertex_normals(self.rest, self.tris)
        e = np.concatenate([self.tris[:, [0, 1]], self.tris[:, [1, 2]], self.tris[:, [2, 0]]])
        self.edges = np.unique(np.sort(e, axis=1), axis=0)
        self.rest_len = np.linalg.norm(self.rest[self.edges[:, 0]] - self.rest[self.edges[:, 1]], axis=1)
        sp = np.zeros(len(self.rest))
        cnt = np.zeros(len(self.rest))
        for k in (0, 1):
            np.add.at(sp, self.edges[:, k], self.rest_len)
            np.add.at(cnt, self.edges[:, k], 1)
        self.spacing = sp / np.maximum(cnt, 1)
        self.region = np.array([self._region(b, s) for b, s in zip(self.base, self.side)])
        self.edge_region = self.region[self.edges[:, 0]]
        # landmarks and vertex sets
        hipy = self.P("upperleg01.L")[1]
        hipz = self.P("upperleg01.L")[2]
        self.buttock = np.flatnonzero((self.rest[:, 2] < hipz + 0.02) & (np.abs(self.rest[:, 0]) < 0.16)
                                      & (self.rest[:, 1] > hipy - 0.20) & (self.rest[:, 1] < hipy + 0.05) & ~self.is_hand)
        band = (np.abs(self.rest[:, 0]) < 0.01) & (np.abs(self.rest[:, 1] - (hipy - 0.02)) < 0.012) & ~self.is_hand
        cand = np.flatnonzero(band)
        self.pubis = int(cand[np.argmax(self.rest[cand, 2])])
        self.sets = {}
        for s in SIDES:
            self.sets[f"foot{s}"] = self.bones([f"foot.{s}"])
            self.sets[f"thigh{s}"] = self.bones([f"upperleg01.{s}", f"upperleg02.{s}"])
            self.sets[f"shin{s}"] = self.bones([f"lowerleg01.{s}", f"lowerleg02.{s}"])
            self.sets[f"leg{s}"] = self.bones([f"upperleg01.{s}", f"upperleg02.{s}", f"lowerleg01.{s}", f"lowerleg02.{s}", f"foot.{s}"])
            self.sets[f"hand{s}"] = np.flatnonzero(self.is_hand & (self.side == s))
            kn = self.P(f"lowerleg01.{s}")
            self.sets[f"knee{s}"] = np.flatnonzero(np.isin(self.dom, [f"upperleg02.{s}", f"lowerleg01.{s}"])
                                                   & (np.linalg.norm(self.rest - kn, axis=1) < 0.08))
            for k in range(1, 6):
                self.sets[f"tip{k}{s}"] = self.bones([f"finger{k}-3.{s}"])
        self.hand = {s: self._hand_frame(s) for s in SIDES}
        self.forearm = {s: self._forearm_rings(s) for s in SIDES}
        self.palm = {s: self._palm_set(s) for s in SIDES}

    @staticmethod
    def _region(b, s):
        if b.startswith(("upperleg", "lowerleg", "foot")):
            return "leg." + s
        if b.startswith(("upperarm", "lowerarm")):
            return "arm." + s
        if b in ("wrist",) or b.startswith(("finger", "metacarpal")):
            return "hand." + s
        if b.startswith(("pelvis", "root")):
            return "hips"
        if b.startswith(("neck", "head")):
            return "head"
        return "torso"

    def P(self, n):
        return self.heads[self.I[n]]

    def T(self, n):
        return self.tails[self.I[n]]

    def bones(self, names):
        return np.flatnonzero(np.isin(self.dom, names))

    def _hand_frame(self, s):
        """Rest hand frame: d (wrist -> middle knuckle), t (radial, toward the index), n (palmar)."""
        d = unit(self.P(f"finger3-1.{s}") - self.P(f"wrist.{s}"))
        t = unit(perp(self.P(f"finger2-1.{s}") - self.P(f"finger5-1.{s}"), d))
        n = np.cross(d, t)
        # the rest fingers are slightly curled toward the palm: fingertips lie on the palmar side
        curl = sum(perp(self.T(f"finger{k}-3.{s}") - self.P(f"wrist.{s}"), d) for k in range(2, 6))
        if np.dot(curl, n) < 0:
            n = -n
        return d, t, n

    def _forearm_rings(self, s):
        e0, w0 = self.P(f"lowerarm01.{s}"), self.P(f"wrist.{s}")
        ax = w0 - e0
        L = np.linalg.norm(ax)
        m = self.bones([f"lowerarm01.{s}", f"lowerarm02.{s}"])
        t = (self.rest[m] - e0) @ ax / L ** 2
        rings = []
        e1, e2 = plane_basis(ax)
        for st in (0.3, 0.5, 0.7, 0.9):
            idx = m[np.abs(t - st) * L < 0.012]
            if len(idx) < 6:
                continue
            p = self.rest[idx] - e0
            rings.append((st, idx, hull_area(np.stack([p @ e1, p @ e2], axis=1))))
        return rings

    def palm_bones(self, s):
        """The palm itself (wrist and metacarpal skin), without the fingers."""
        return self.bones([f"wrist.{s}"] + [f"metacarpal{k}.{s}" for k in range(1, 5)])

    def _palm_set(self, s):
        d, t, n = self.hand[s]
        wr = self.P(f"wrist.{s}")
        names = [f"wrist.{s}"] + [f"metacarpal{k}.{s}" for k in range(1, 5)] + \
                [f"finger{k}-{j}.{s}" for k in range(2, 6) for j in range(1, 4)]
        m = self.bones(names)
        keep = (self.rest_n[m] @ n > 0.5) & ((self.rest[m] - wr) @ d > 0.0)
        return m[keep]

    def rest_pronation(self, s):
        """Forearm rotation of the rest pose (supination +, 0 = palm parallel to the elbow hinge axis,
        i.e. thumb up with the elbow bent). The reference is the rest elbow hinge, not world x: in the
        rest A-pose the arm is abducted ~40 deg and the elbow bent, so world x is ~30 deg off."""
        sg = SIDES[s]
        u0 = self.P(f"lowerarm01.{s}") - self.P(f"upperarm01.{s}")
        f0 = self.P(f"wrist.{s}") - self.P(f"lowerarm01.{s}")
        ref = sg * unit(perp(np.cross(u0, f0), f0))
        return -sg * signed_angle(ref, self.hand[s][2], f0)


# ---------------------------------------------------------------- pose composition (same as pose.js composePose)
def compose(poses, variant, body_id, hand_id):
    def pick(obj):
        return (obj or {}).get(variant) or (obj or {}).get("neutral") or {}
    body = poses["body"][body_id]
    local = {k: np.array(q, float) for k, q in pick(body.get("rot")).items()}
    hand = poses["hand"].get(hand_id) if hand_id else None
    has_arms = False
    if hand:
        arms = pick(hand.get("arms"))
        has_arms = bool(arms)
        if not arms and hand_id != "open":   # same rule as pose.js: mudra -> the pose's palm-up arms
            local.update({k: np.array(q, float) for k, q in pick(body.get("mudraArms")).items()})
        local.update({k: np.array(q, float) for k, q in arms.items()})
        own = pick(body.get("openRot")) if hand_id == "open" else {}     # same rule as pose.js: lotus dhyana
        fingers = own or pick(hand.get("rot"))
        for k, q in fingers.items():
            local[k] = np.array(q, float)
            if k.endswith(".L") and k[:-2] + ".R" not in fingers:   # explicit right values win (dhyana thumbs)
                local[k[:-2] + ".R"] = np.array([q[0], -q[1], -q[2], q[3]], float)
    root = np.array(pick(body.get("root")) or [0, 0, 0], float)
    return local, root, has_arms


# ---------------------------------------------------------------- measurement
class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, value, op, limit, side=None, unit_=""):
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return
        if op == "<=":
            ok = value <= limit
        elif op == ">=":
            ok = value >= limit
        else:
            ok = limit[0] <= value <= limit[1]
        self.items.append({"name": name, "side": side, "value": round(float(value), 4), "op": op,
                           "limit": list(limit) if isinstance(limit, tuple) else limit, "unit": unit_, "ok": bool(ok)})


def nearest_k(pa, pb, k, chunk=1024):
    """Indices (n, k) of the k nearest pb points for each pa point, nearest first."""
    bb = np.einsum("ij,ij->i", pb, pb)
    out = np.empty((len(pa), k), dtype=np.int64)
    for i in range(0, len(pa), chunk):
        a = pa[i:i + chunk]
        m = np.einsum("ij,ij->i", a, a)[:, None] + bb[None, :] - 2 * a @ pb.T
        j = np.argpartition(m, k, axis=1)[:, :k]
        o = np.argsort(np.take_along_axis(m, j, 1), axis=1)
        out[i:i + chunk] = np.take_along_axis(j, o, 1)
    return out


def surface_sd(b, pos, nrm, A, B, k=5, reach=0.05):
    """Signed distance (m, + outside) of vertices A to the surface of vertex set B.
    Inside only when at least k-1 of the k nearest B vertices see the point behind their normal
    and it is closer than `reach` (a single normal is unreliable at the edge of the set)."""
    PB, NB = pos[B], nrm[B]
    J = nearest_k(pos[A], PB, k)
    rel = pos[A][:, None, :] - PB[J]
    behind = (np.einsum("ijk,ijk->ij", rel, NB[J]) < 0).sum(1)
    j = J[:, 0]
    d2 = np.einsum("ij,ij->i", rel[:, 0], rel[:, 0])
    plane = np.abs(np.einsum("ij,ij->i", rel[:, 0], NB[j]))
    lateral2 = np.maximum(d2 - plane ** 2, 0)
    mag = np.where(lateral2 < b.spacing[B][j] ** 2, plane, np.sqrt(d2))
    inside = (behind >= k - 1) & (d2 < reach ** 2)
    return np.where(inside, -mag, mag)


def min_dist(pos, A, B):
    _, d2 = nearest(pos[A], pos[B])
    return float(np.sqrt(d2.min()))


def hinge_angle(prox, dist, hinge):
    """Angle (deg) between two segments, negative when bent the wrong way about `hinge`."""
    return angle(prox, dist) * (1 if np.dot(np.cross(prox, dist), hinge) >= 0 else -1)


def joint_angles(b, Q, H):
    I = b.I
    out = {}
    for s, sg in SIDES.items():
        h0, k0, a0 = b.P(f"upperleg01.{s}"), b.P(f"lowerleg01.{s}"), b.P(f"foot.{s}")
        hip, knee, ank = H[I[f"upperleg01.{s}"]], H[I[f"lowerleg01.{s}"]], H[I[f"foot.{s}"]]
        Qp, Qt, Qs, Qf = (Q[I[n]] for n in (f"pelvis.{s}", f"upperleg02.{s}", f"lowerleg02.{s}", f"foot.{s}"))
        d = qrot(qconj(Qp), unit(knee - hip))
        h = qrot(qmul(qconj(Qp), Qt), X)
        hw = qrot(Qt, X)                                  # knee hinge axis (rest +x) carried by the thigh

        kf = hinge_angle(knee - hip, ank - knee, hw)      # absolute: 0 = straight, < 0 = hyperextended
        out[s] = {
            "hip_flex": float(np.degrees(np.arctan2(d[2], -d[1]))),
            "hip_abd": float(np.degrees(np.arcsin(np.clip(sg * d[0], -1, 1)))),
            "hip_er": -sg * signed_angle(perp(X, d), h, d),
            "knee_flex": kf,
            "ankle_twist": -sg * twist_deg(qmul(qconj(Qs), Qf), a0 - k0),
            "ankle_swing": float(np.linalg.norm(swing_vec(qmul(qconj(Qs), Qf), a0 - k0))),
        }
        # arm
        s0, e0, w0 = b.P(f"upperarm01.{s}"), b.P(f"lowerarm01.{s}"), b.P(f"wrist.{s}")
        sh, el, wr = H[I[f"upperarm01.{s}"]], H[I[f"lowerarm01.{s}"]], H[I[f"wrist.{s}"]]
        Qth, Qh, Qa, Qw = (Q[I[n]] for n in ("spine01", f"upperarm02.{s}", f"lowerarm02.{s}", f"wrist.{s}"))
        u = qrot(qconj(Qth), unit(el - sh))
        u0, f0 = e0 - s0, w0 - e0
        tau = twist_deg(qmul(qconj(Qh), Qa), f0)
        dh, th_, nh = b.hand[s]
        rel = qmul(qconj(Qa), Qw)
        sv = swing_vec(rel, dh)
        out[s].update({
            "sh_flex": float(np.degrees(np.arctan2(u[2], -u[1]))),
            "sh_abd": float(np.degrees(np.arcsin(np.clip(sg * u[0], -1, 1)))),
            "humeral_rot": -sg * twist_deg(qmul(qconj(Qth), Qh), u0),
            # absolute, signed by the elbow hinge of the rest pose carried by the humerus
            "elbow_flex": hinge_angle(el - sh, wr - el, qrot(Qh, np.cross(u0, f0))),
            "pron_sup": float((b.rest_pronation(s) - sg * tau + 180) % 360 - 180),
            "wrist_flex": float(np.dot(sv, unit(np.cross(dh, nh)))),
            "wrist_dev": float(np.dot(sv, unit(np.cross(dh, th_)))),
            "wrist_twist": -sg * twist_deg(rel, dh),
        })
    return out


def finger_flex(b, Q, s, k):
    """Absolute joint flexion (deg) of finger k (2..5): MCP, PIP, DIP from posed bone directions."""
    I = b.I
    chain = [b.rig.names[b.rig.parent[I[f"finger{k}-1.{s}"]]]] + [f"finger{k}-{j}.{s}" for j in range(1, 4)]
    dirs = [qrot(Q[I[n]], b.T(n) - b.P(n)) for n in chain]
    return [angle(dirs[i], dirs[i + 1]) for i in range(3)]


def finger_fan(b, Q, s):
    I = b.I
    n = qrot(Q[I[f"wrist.{s}"]], b.hand[s][2])
    dirs = [qrot(Q[I[f"finger{k}-1.{s}"]], b.T(f"finger{k}-1.{s}") - b.P(f"finger{k}-1.{s}")) for k in range(2, 6)]
    return max(abs(signed_angle(dirs[i], dirs[i + 1], n)) for i in range(3))


def corrective(poses, variant, body_id):
    """Contact/delta-mush corrective of a body pose (correctives.py) as (vertex ids, n x 3 displacements)."""
    c = (poses["body"][body_id].get("corr") or {}).get(variant)
    if not c or not c.get("i"):
        return None
    return np.asarray(c["i"], dtype=np.int64), np.asarray(c["d"], float).reshape(-1, 3)


def evaluate(b, local, root, body_id, hand_id, has_arms, corr=None):
    rig = b.rig
    Q, H = rig.fk(b.v, local, root)
    pos = rig.skin(b.rest, b.v, Q, H)
    if corr is not None:              # the page adds the pose's corrective after skinning (pose.js)
        pos[corr[0]] += corr[1]
    nrm = vertex_normals(pos, b.tris)
    I = b.I
    C = Checks()
    M = {"angles": joint_angles(b, Q, H)}
    A = M["angles"]
    lotus = body_id in LOTUS
    # ---- joint ranges
    for s in SIDES:
        a = A[s]
        C.add("hip_flex", a["hip_flex"], "<=", LIM["hip_flex"], s, "deg")
        vr = body_id == "vrikshasana"
        C.add("hip_abd", a["hip_abd"], "<=", LIM["vriksha_hip_abd"] if vr else LIM["hip_abd"], s, "deg")
        er_hi = LIM["vriksha_hip_er"] if vr else (LIM["hip_er_lotus"] if lotus else LIM["hip_er"])
        C.add("hip_er", a["hip_er"], "in", (LIM["hip_ir"], er_hi), s, "deg")
        C.add("knee_flex", a["knee_flex"], "in", (LIM["knee_hyper"], LIM["knee_flex"]), s, "deg")
        C.add("ankle_twist", abs(a["ankle_twist"]), "<=", LIM["ankle_twist"], s, "deg")
        C.add("humeral_rot", a["humeral_rot"], "in", LIM["humeral_rot"], s, "deg")
        C.add("elbow_flex", a["elbow_flex"], ">=", LIM["elbow_hyper"], s, "deg")
        C.add("pron_sup", a["pron_sup"], "in", LIM["pron_sup"], s, "deg")
        ext_lim = LIM["wrist_ext_dandasana"] if body_id == "dandasana" and not has_arms else LIM["wrist_ext"]
        C.add("wrist_ext", -a["wrist_flex"], "<=", ext_lim, s, "deg")
        C.add("wrist_flex", a["wrist_flex"], "<=", LIM["wrist_flex"], s, "deg")
        C.add("wrist_dev", abs(a["wrist_dev"]), "<=", LIM["wrist_dev"], s, "deg")
        C.add("wrist_twist", abs(a["wrist_twist"]), "<=", LIM["wrist_twist"], s, "deg")
    # ---- floor and seat
    M["min_y"] = float(pos[:, 1].min())
    C.add("floor_pen", M["min_y"], ">=", LIM["floor_pen"], None, "m")
    if body_id in SEATED:
        M["buttock_y"] = float(pos[b.buttock, 1].min())
        if body_id == "vajrasana":
            feet = np.concatenate([b.sets["footL"], b.sets["footR"]])
            M["buttock_heel_gap"] = float(surface_sd(b, pos, nrm, b.buttock, feet).min())
            C.add("buttock_heel_gap", M["buttock_heel_gap"], "<=", LIM["buttock_heel_gap"], None, "m")
        else:
            C.add("buttock_floor", M["buttock_y"], "<=", LIM["buttock_floor"], None, "m")
        M["knee_skin_y"] = {s: float(pos[b.sets[f"knee{s}"], 1].min()) for s in SIDES}
        if body_id in KNEE_FLOOR:
            hmax, dmax = KNEE_FLOOR[body_id]
            for s in SIDES:
                if body_id == "ardha_padmasana" and s == HALF_TOP_KNEE["side"]:
                    C.add("knee_height", M["knee_skin_y"][s], "<=", HALF_TOP_KNEE["max"], s, "m")
                    legT = np.concatenate([b.sets[f"thigh{s}"], b.sets[f"shin{s}"]])
                    sd = surface_sd(b, pos, nrm, b.sets[f"foot{OTHER[s]}"], legT)
                    C.add("top_leg_on_foot_gap", float(sd.min()), "<=", HALF_TOP_KNEE["gap"], s, "m")
                    C.add("top_leg_on_foot_sink", float(max(0.0, -sd.min())), "<=", HALF_TOP_KNEE["sink"], s, "m")
                    continue
                C.add("knee_height", M["knee_skin_y"][s], "<=", hmax, s, "m")
            if dmax is not None:
                C.add("knee_height_diff", abs(M["knee_skin_y"]["L"] - M["knee_skin_y"]["R"]), "<=", dmax, None, "m")
    # ---- shin crossing in front of the pubis
    if body_id in SHIN_CROSS_MAX:
        a1, b1 = H[I["lowerleg01.L"]], H[I["foot.L"]]
        a2, b2 = H[I["lowerleg01.R"]], H[I["foot.R"]]
        best = None
        for t in np.linspace(0, 1, 201):
            p = a1 + t * (b1 - a1)
            uu = np.clip(np.dot(p - a2, b2 - a2) / np.dot(b2 - a2, b2 - a2), 0, 1)
            q = a2 + uu * (b2 - a2)
            dd = np.linalg.norm(p - q)
            if best is None or dd < best[0]:
                best = (dd, 0.5 * (p + q))
        M["shin_axes_dist"] = float(best[0])
        M["shin_axes_cross_fwd"] = float(best[1][2] - pos[b.pubis, 2])
        # crossing as seen from above: skin of shin+foot of one leg over the other's (2D, within 1.5 cm)
        la = np.concatenate([b.sets["shinL"], b.sets["footL"]])
        ra = np.concatenate([b.sets["shinR"], b.sets["footR"]])
        j, d2 = nearest(pos[la][:, [0, 2]], pos[ra][:, [0, 2]])
        ov = d2 < 0.015 ** 2
        if ov.any():
            z = np.concatenate([pos[la][ov, 2], pos[ra][j[ov], 2]]) - pos[b.pubis, 2]
            M["shin_cross_fwd"] = float(np.median(z))
            M["shin_cross_front"] = float(z.max())
        else:
            M["shin_cross_fwd"] = M["shin_axes_cross_fwd"]
        C.add("shin_cross_fwd", M["shin_cross_fwd"], "<=", SHIN_CROSS_MAX[body_id], None, "m")
    # ---- feet resting on the opposite thigh
    rest_on = []
    if body_id == "padmasana":
        rest_on = ["L", "R"]
    elif body_id == "ardha_padmasana":
        # asanas.solve_lotus always puts the left foot on top; picking the higher ankle chose the right
        # foot (under the left knee) on the neutral body and checked the wrong leg
        rest_on = ["L"]
    elif body_id == "vrikshasana":
        bent = max(SIDES, key=lambda s: A[s]["knee_flex"])
        rest_on = [bent]
        st = OTHER[bent]
        C.add("vriksha_hip_flex", A[bent]["hip_flex"], "<=", LIM["vriksha_hip_flex"], bent, "deg")
        hip_y, knee_y = H[I[f"upperleg01.{st}"]][1], H[I[f"lowerleg01.{st}"]][1]
        rel_h = (pos[b.sets[f"foot{bent}"], 1].mean() - knee_y) / max(1e-6, hip_y - knee_y)
        M["vriksha_foot_height"] = float(rel_h)
        C.add("vriksha_foot_height", rel_h, ">=", LIM["vriksha_foot_height"], bent, "of thigh")
    M["foot_on_thigh"] = {}
    for s in rest_on:
        sd = surface_sd(b, pos, nrm, b.sets[f"foot{s}"], b.sets[f"thigh{OTHER[s]}"])
        # sinking = depth of the 3rd deepest foot vertex: a single heel vertex in the groin fold, where
        # the thigh set meets the pelvis and the normals turn, read 22 mm while the solver on the same
        # pose read 0 (3-4 vertices 38 mm in, as once on the male body, still fail)
        gap, sink = float(sd.min()), float(max(0.0, -np.sort(sd)[min(2, len(sd) - 1)]))
        M["foot_on_thigh"][s] = {"gap": gap, "sink": sink}
        C.add("foot_thigh_gap", gap, "<=", LIM["foot_thigh_gap"], s, "m")
        C.add("foot_thigh_sink", sink, "<=", LIM["foot_thigh_sink"], s, "m")
    # feet that rest on the thighs must be seen from above (a foot is visible where no other skin lies
    # above it within 1 cm sideways)
    if body_id in LOTUS:
        others = np.setdiff1d(np.arange(len(pos)), np.concatenate([b.sets["footL"], b.sets["footR"]]))
        po = pos[others]
        for s in rest_on:
            f = pos[b.sets[f"foot{s}"]][::2]
            vis = 0
            for p in f:
                near = ((po[:, 0] - p[0]) ** 2 + (po[:, 2] - p[2]) ** 2) < 0.01 ** 2
                if not near.any() or po[near, 1].max() < p[1] + 0.002:
                    vis += 1
            M.setdefault("foot_visible", {})[s] = vis / max(1, len(f))
            C.add("foot_top_visible", vis / max(1, len(f)), ">=", LIM["foot_top_visible"], s, "")
    # arms out of the trunk, hands out of each other
    trunk = np.flatnonzero(np.isin(b.region, ["torso", "hips"]))
    for s in SIDES:
        fore = np.flatnonzero((np.isin(b.base, ["lowerarm01", "lowerarm02"]) | b.is_hand) & (b.side == s))
        sd = surface_sd(b, pos, nrm, fore, trunk)
        C.add("arm_trunk_pen", float(max(0.0, -sd.min())), "<=", LIM["arm_trunk_pen"], s, "m")
    if hand_id not in ("anjali", "hakini"):
        hh = min(surface_sd(b, pos, nrm, b.sets["handR"], b.sets["handL"]).min(), surface_sd(b, pos, nrm, b.sets["handL"], b.sets["handR"]).min())
        C.add("hand_hand_pen", float(max(0.0, -hh)), "<=", LIM["hand_hand_pen"], None, "m")
    # ---- hands
    legs = np.concatenate([b.sets["legL"], b.sets["legR"]])
    if body_id in SEATED and body_id != "dandasana" and not has_arms:
        M["hand_leg"] = {}
        for s in SIDES:
            # lotus dhyana: the right hand rests on the left one, which is its support (it read as a
            # 4-10 cm gap over the legs)
            sup = np.concatenate([legs, b.sets["handL"]]) if (body_id in LOTUS and hand_id == "open" and s == "R") else legs
            sd = surface_sd(b, pos, nrm, b.sets[f"hand{s}"], sup)
            M["hand_leg"][s] = {"gap": float(sd.min()), "sink": float(max(0.0, -sd.min()))}
            C.add("hand_leg_gap", float(sd.min()), "<=", LIM["hand_leg_gap"], s, "m")
            C.add("hand_leg_sink", float(max(0.0, -sd.min())), "<=", LIM["hand_leg_sink"], s, "m")
            if hand_id == "open" and body_id not in LOTUS:
                # the palm itself rests on the thigh: curled fingertips touching the knee passed the gap
                # above while the palm hung 1-2 cm over the thigh (sukhasana)
                sdp = surface_sd(b, pos, nrm, b.palm_bones(s), legs)
                C.add("palm_leg_gap", float(sdp.min()), "<=", LIM["palm_leg_gap"], s, "m")
    if body_id == "dandasana" and not has_arms:
        for s in SIDES:
            C.add("hand_floor_gap", float(pos[b.sets[f"hand{s}"], 1].min()), "<=", LIM["hand_floor_gap"], s, "m")
    if hand_id == "anjali":
        M["anjali"] = {}
        mid, lat = H[I["spine01"]], qrot(Q[I["spine01"]], X)   # body mid plane (the root may be shifted)
        for s, sg in SIDES.items():
            x = (pos[b.palm[s]] - mid) @ lat * sg   # distance from the mid plane, + on the own side
            pads = np.isin(b.palm[s], b.bones([f"finger{k}-{j}.{s}" for k in range(2, 6) for j in (2, 3)]))
            pad_frac = float(np.mean(np.abs(x[pads]) <= LIM["anjali_pad_band"]))
            med = float(np.median(x))
            pen = float(max(0.0, -x.min()))
            M["anjali"][s] = {"pad_frac": pad_frac, "penetration": pen, "median_gap": med}
            C.add("anjali_palm_med", med, "<=", LIM["anjali_palm_med"], s, "m")
            C.add("anjali_pad_frac", pad_frac, ">=", LIM["anjali_pad_frac"], s, "")
            C.add("anjali_palm_pen", pen, "<=", LIM["anjali_pen"], s, "m")
    if hand_id == "hakini":
        # nothing measured hakini until 2026-11-12, when the user saw the palms merged and the index
        # fingers lying on the other hand: every fingertip on its twin, no hand past the mid plane,
        # a hollow between the palms
        mid, lat = H[I["spine01"]], qrot(Q[I["spine01"]], X)
        M["hakini"] = {"tip_gap": {}}
        for k in range(1, 6):
            g = min_dist(pos, b.sets[f"tip{k}L"], b.sets[f"tip{k}R"])
            M["hakini"]["tip_gap"][k] = g
            C.add(f"hakini_tip_gap_f{k}", g, "<=", LIM["hakini_tip_gap"], None, "m")
        for s, sg in SIDES.items():
            x = (pos[b.sets[f"hand{s}"]] - mid) @ lat * sg
            C.add("hakini_cross", float(max(0.0, -x.min())), "<=", LIM["hakini_cross"], s, "m")
        pl = (pos[b.bones([f"metacarpal{k}.L" for k in range(1, 5)])] - mid) @ lat
        C.add("hakini_palm_apart", float(np.median(pl)), ">=", LIM["hakini_palm"], "L", "m")
    if hand_id in MUDRA_TARGETS:
        M["mudra"] = {}
        for s in SIDES:
            gaps = {k: min_dist(pos, b.sets[f"tip1{s}"], b.sets[f"tip{k}{s}"]) for k in MUDRA_TARGETS[hand_id]}
            free = {k: max(finger_flex(b, Q, s, k)) for k in range(2, 6) if k not in MUDRA_TARGETS[hand_id]}
            M["mudra"][s] = {"tip_gap": gaps, "free_max_flex": free}
            for k, g in gaps.items():
                C.add(f"mudra_tip_gap_f{k}", g, "<=", LIM["mudra_gap"], s, "m")
            for k, f in free.items():
                C.add(f"mudra_free_flex_f{k}", f, "<=", LIM["mudra_free_flex"], s, "deg")
    if hand_id in ("open", "anjali"):
        for s in SIDES:
            C.add("finger_fan", finger_fan(b, Q, s), "<=", LIM["finger_fan"], s, "deg")
    # ---- pose-specific targets (yoga teacher)
    if body_id == "dandasana":
        for s in SIDES:
            C.add("danda_knee_flex", A[s]["knee_flex"], "<=", LIM["danda_knee"], s, "deg")
            C.add("danda_popliteal", M["knee_skin_y"][s], "<=", LIM["danda_popliteal"], s, "m")
            fd = qrot(Q[I[f"foot.{s}"]], b.T(f"foot.{s}") - b.P(f"foot.{s}"))
            C.add("danda_foot_up", angle(fd, [0, 1, 0]), "<=", LIM["danda_foot_up"], s, "deg")
        C.add("danda_leg_gap", min_dist(pos, b.sets["shinL"], b.sets["shinR"]), "<=", LIM["danda_leg_gap"], None, "m")
    # ---- skin quality
    ln = np.linalg.norm(pos[b.edges[:, 0]] - pos[b.edges[:, 1]], axis=1)
    ratio = ln / np.maximum(b.rest_len, 1e-9)
    M["stretch_p99_all"] = float(np.percentile(ratio, 99))
    M["stretch_max"] = float(ratio.max())
    C.add("stretch_p99", M["stretch_p99_all"], "<=", LIM["stretch_p99"], None, "")
    M["stretch_p99"] = {}
    M["compress_p1"] = {}
    for r in np.unique(b.edge_region):
        m = b.edge_region == r
        M["stretch_p99"][r] = float(np.percentile(ratio[m], 99))
        M["compress_p1"][r] = float(np.percentile(ratio[m], 1))
        C.add("stretch_p99_region", M["stretch_p99"][r], "<=", LIM["stretch_p99_region"], r, "")
    M["forearm_area"] = {}
    for s in SIDES:
        el, wr = H[I[f"lowerarm01.{s}"]], H[I[f"wrist.{s}"]]
        e1, e2 = plane_basis(wr - el)
        ratios = {}
        for st, idx, a0 in b.forearm[s]:
            p = pos[idx] - el
            ratios[st] = hull_area(np.stack([p @ e1, p @ e2], axis=1)) / max(a0, 1e-12)
        M["forearm_area"][s] = ratios
        if ratios:
            C.add("forearm_area", min(ratios.values()), ">=", LIM["forearm_area"], s, "of rest")
    return M, C.items, pos


# ---------------------------------------------------------------- sheets
def sheet(pos, tris, out, title, tmp):
    from PIL import Image
    lo, hi = pos.min(axis=0) - 0.02, pos.max(axis=0) + 0.02
    tiles = []
    for v in VIEWS6:
        f = Path(tmp) / f"_{v}.png"
        pk.render([(pos, tris, (222, 202, 186))], v, str(f), size=360, bbox=(lo, hi), title=f"{title} ({v})")
        tiles.append(Image.open(f).convert("RGB"))
    w = max(t.width for t in tiles)
    h = max(t.height for t in tiles)
    img = Image.new("RGB", (w * 3, h * 2), (246, 243, 238))
    for i, t in enumerate(tiles):
        img.paste(t, ((i % 3) * w, (i // 3) * h))
    img.save(out)


# ---------------------------------------------------------------- main
def fmt_check(c):
    unit_ = c["unit"]
    v = c["value"]
    if unit_ == "m":
        vs = f"{v * 1000:.0f}mm"
        lim = c["limit"]
        ls = (f"[{lim[0] * 1000:.0f},{lim[1] * 1000:.0f}]mm" if isinstance(lim, list) else f"{c['op']}{lim * 1000:.0f}mm")
    else:
        vs = f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}"
        lim = c["limit"]
        ls = f"[{lim[0]},{lim[1]}]" if isinstance(lim, list) else f"{c['op']}{lim:g}"
        vs += {"deg": "deg"}.get(unit_, "")
    side = f".{c['side']}" if c["side"] else ""
    return f"{c['name']}{side}={vs} ({ls})"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variants", nargs="*", default=["neutral", "female", "male"])
    ap.add_argument("--poses", nargs="*", help="body pose ids (default: all in poses.json)")
    ap.add_argument("--hands", nargs="*", help="hand poses checked on sukhasana (default: all; pass none to skip)")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "pose_check"))
    ap.add_argument("--poses-file", default=str(pk.ASSETS / "poses.json"))
    args = ap.parse_args()
    t0 = time.time()
    poses = json.loads(Path(args.poses_file).read_text(encoding="utf-8"))
    rig = pk.Rig()
    out = Path(args.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    body_ids = args.poses or list(poses["body"])
    hand_ids = list(poses["hand"]) if args.hands is None else [h for h in args.hands if h != "none"]
    combos = []
    for pid in body_ids:
        combos.append((pid, poses["body"][pid].get("defaultHand", "open")))
    if "sukhasana" in poses["body"]:
        for hid in hand_ids:
            if ("sukhasana", hid) not in combos:
                combos.append(("sukhasana", hid))
    results = []
    fails = {}
    for variant in args.variants:
        b = Body(rig, variant)
        for pid, hid in combos:
            local, root, has_arms = compose(poses, variant, pid, hid)
            M, checks, pos = evaluate(b, local, root, pid, hid, has_arms, corrective(poses, variant, pid))
            bad = [c for c in checks if not c["ok"]]
            results.append({"variant": variant, "body": pid, "hand": hid, "pass": not bad,
                            "n_checks": len(checks), "n_fail": len(bad), "metrics": M, "checks": checks})
            for c in bad:
                fails.setdefault(c["name"], []).append(f"{variant}/{pid}+{hid}" + (f".{c['side']}" if c["side"] else ""))
            print(f"{'PASS' if not bad else 'FAIL'} {variant:7s} {pid + '+' + hid:28s} {len(checks) - len(bad):3d}/{len(checks):3d}")
            for c in bad:
                print("      " + fmt_check(c))
            if not args.no_sheets:
                sheet(pos, b.tris, out / "sheets" / f"{variant}_{pid}_{hid}.png", f"{variant} {pid}+{hid}", out / "sheets")
    for f in (out / "sheets").glob("_*.png"):
        f.unlink()
    n_bad = sum(not r["pass"] for r in results)
    summary = {"combos": len(results), "failed_combos": n_bad,
               "failed_checks": {k: len(v) for k, v in sorted(fails.items(), key=lambda kv: -len(kv[1]))},
               "seconds": round(time.time() - t0, 1)}
    report = {"poses_file": str(args.poses_file), "limits": LIM, "shin_cross_max": SHIN_CROSS_MAX,
              "knee_floor": KNEE_FLOOR, "summary": summary, "failures": fails, "results": results}
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"{len(results) - n_bad}/{len(results)} pose combos pass; failing checks (count):")
    for k, n in summary["failed_checks"].items():
        print(f"  {k:24s} {n}")
    print("report:", out / "report.json", f"({summary['seconds']} s)")
    sys.exit(1 if n_bad else 0)


if __name__ == "__main__":
    main()
