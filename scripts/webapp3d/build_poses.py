"""Author webapp/assets/poses.json (asanas + mudras) with small IK helpers, per body variant.

Usage: python3 -I build_poses.py [--only body|hand] [--variants neutral female male]

Reads webapp/assets/rig.json and body*.glb. Every pose is solved separately for each body
variant (limb lengths differ), stored as LOCAL bone rotations relative to the rest pose,
quaternions [x, y, z, w] in the rest-pose world axes (+x body's left, +y up, +z front),
see posekit.py for the exact FK formula.  Hand poses store the LEFT hand; the right hand
uses the mirrored quaternion (x, -y, -z, w).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import posekit as pk  # noqa: E402
from posekit import qaxis, qconj, qmul, qrot, unit  # noqa: E402

ID = np.array([0, 0, 0, 1.0])
SIDES = {"L": 1.0, "R": -1.0}
FINGER_BONES = [f"finger{k}-{j}" for k in range(1, 6) for j in range(1, 4)] + [f"metacarpal{k}" for k in range(1, 5)]
ARM_BONES = ["clavicle", "shoulder01", "upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist"]
HAND_SET = {"wrist"} | set(FINGER_BONES)


def angle_of(q):
    return 2 * np.degrees(np.arccos(min(1.0, abs(q[3]))))


def nelder_mead(f, x0, step, iters=1500, tol=1e-10):
    n = len(x0)
    pts = [np.array(x0, float)]
    for i in range(n):
        p = np.array(x0, float)
        p[i] += step[i] if hasattr(step, "__len__") else step
        pts.append(p)
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol:
            break
        c = np.mean(pts[:-1], axis=0)
        xr = c + (c - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, len(pts)):
                    pts[i] = pts[0] + 0.5 * (pts[i] - pts[0])
                    vals[i] = f(pts[i])
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def two_bone(root, target, l1, l2, pole):
    d = target - root
    dist = np.linalg.norm(d)
    a = d / dist
    dist = min(dist, (l1 + l2) * 0.9995)
    dist = max(dist, abs(l1 - l2) + 1e-4)
    cosa = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    sina = np.sqrt(max(0.0, 1 - cosa * cosa))
    pp = np.asarray(pole, float) - a * np.dot(pole, a)
    pp = unit(pp)
    mid = root + a * l1 * cosa + pp * l1 * sina
    end = root + a * dist
    return mid, end


class Poser:
    def __init__(self, rig, variant, rest):
        self.rig, self.v, self.rest = rig, variant, rest
        self.h, self.t = rig.heads[variant], rig.tails[variant]
        self.W = {}
        self.root = np.zeros(3)
        # local rotations laid over W in fk()/skin() only (not in local()): the fingers that will be shown,
        # so an arm solver sees the real hand shape instead of the rest fingers
        self.hold = {}
        dom =rig.joints[np.arange(len(rest)), rig.weights.argmax(1)]
        self.dom = np.array(rig.names)[dom]
        base = np.array([n.split(".")[0] for n in self.dom])
        self.hand_mask = np.isin(base, list(HAND_SET))
        self._hand_cache = {}

    def P(self, n):
        return self.h[self.rig.index[n]]

    def T(self, n):
        return self.t[self.rig.index[n]]

    # ---- world rotations -> local
    def local(self, W=None):
        W = self.W if W is None else W
        rig = self.rig
        Qw = []
        loc = {}
        for i, n in enumerate(rig.names):
            p = rig.parent[i]
            Qp = Qw[p] if p >= 0 else ID
            Qb = W.get(n, Qp)
            q = qmul(qconj(Qp), Qb)
            q = q / np.linalg.norm(q)
            if q[3] < 0:
                q = -q
            Qw.append(Qb)
            if angle_of(q) > 1e-4:
                loc[n] = q
        return loc

    def fk(self):
        loc = self.local()
        loc.update(self.hold)
        return self.rig.fk(self.v, loc, self.root)

    def skin(self):
        Q, H = self.fk()
        return self.rig.skin(self.rest, self.v, Q, H)

    # ---- legs
    def set_leg(self, s, ankle, pole, foot_dir, sole_normal, kneecap=None):
        """Place the ankle (world) with the knee bending toward `pole`; foot frame by toe direction
        and sole normal (pointing out of the sole). kneecap: explicit kneecap direction (straight legs)."""
        hip0, knee0, ank0 = self.P(f"upperleg01.{s}"), self.P(f"lowerleg01.{s}"), self.P(f"foot.{s}")
        hip = hip0 + self.root
        l1, l2 = np.linalg.norm(knee0 - hip0), np.linalg.norm(ank0 - knee0)
        knee, ank = two_bone(hip, np.asarray(ankle, float), l1, l2, pole)
        a, sd = unit(knee - hip), unit(ank - knee)
        c = np.cross(a, sd)
        if kneecap is not None or np.linalg.norm(c) < 0.05:
            kc = np.asarray(kneecap if kneecap is not None else pole, float)
            hng = unit(np.cross(kc, a))
        else:
            hng = unit(c)
        a0, s0 = unit(knee0 - hip0), unit(ank0 - knee0)
        x = np.array([1.0, 0, 0])
        Rt = pk.frame_rot(a0, x, a, hng)
        Rs = pk.frame_rot(s0, x, sd, hng)
        for b in ("upperleg01", "upperleg02"):
            self.W[f"{b}.{s}"] = Rt
        for b in ("lowerleg01", "lowerleg02"):
            self.W[f"{b}.{s}"] = Rs
        # anatomical foot frame at rest: heel->toe axis horizontal forward (slightly out), sole facing down
        sg = SIDES[s]
        self.W[f"foot.{s}"] = pk.frame_rot(unit([sg * 0.12, 0, 1]), [0, -1, 0], foot_dir, sole_normal)
        return knee, ank

    # ---- arms
    def hand_frame0(self, s):
        sg = SIDES[s]
        d0 = unit(self.P(f"finger3-1.{s}") - self.P(f"wrist.{s}"))
        n0 = unit(np.cross(d0, self.P(f"finger2-1.{s}") - self.P(f"finger5-1.{s}"))) * sg
        return d0, n0

    def set_arm(self, s, wrist, pole, hand_dir, palm_normal, twist_share=0.35):
        sh0, el0, wr0 = self.P(f"upperarm01.{s}"), self.P(f"lowerarm01.{s}"), self.P(f"wrist.{s}")
        Q, H = self.fk()
        sh = H[self.rig.index[f"upperarm01.{s}"]]
        l1, l2 = np.linalg.norm(el0 - sh0), np.linalg.norm(wr0 - el0)
        el, wr = two_bone(sh, np.asarray(wrist, float), l1, l2, pole)
        u, f = unit(el - sh), unit(wr - el)
        u0, f0 = unit(el0 - sh0), unit(wr0 - el0)
        h0 = unit(np.cross(u0, f0))
        c = np.cross(u, f)
        hng = unit(c) if np.linalg.norm(c) > 0.08 else unit(np.cross(u, np.asarray(pole, float)) * -1)
        # keep the elbow hinge sense of the rest pose (u x f)
        Ru = pk.frame_rot(u0, h0, u, hng)
        Rf = pk.frame_rot(f0, h0, f, hng)
        d0, n0 = self.hand_frame0(s)
        Rh = pk.frame_rot(d0, n0, hand_dir, palm_normal)
        # forearm twist that leaves the least rotation for the wrist
        best = None
        for tau in np.arange(-150, 151, 2.0):
            Rt = qmul(qaxis(f, tau), Rf)
            res = angle_of(qmul(qconj(Rt), Rh))
            if best is None or res < best[1]:
                best = (tau, res)
        tau = best[0]
        self.W[f"upperarm01.{s}"] = Ru
        self.W[f"upperarm02.{s}"] = Ru
        self.W[f"lowerarm01.{s}"] = qmul(qaxis(f, tau * twist_share), Rf)
        self.W[f"lowerarm02.{s}"] = qmul(qaxis(f, tau), Rf)
        self.W[f"wrist.{s}"] = Rh
        return el, wr, tau, best[1]

    def ground(self):
        pos = self.skin()
        body = pos[~self.hand_mask]
        return pos, -body[:, 1].min()


# ------------------------------------------------------------------ body poses
def legs_seated(ps, kind):
    """Set both legs for a seated pose; positions relative to the posed hip joints."""
    L = {s: np.linalg.norm(ps.P(f"lowerleg01.{s}") - ps.P(f"upperleg01.{s}")) for s in SIDES}
    S = {s: np.linalg.norm(ps.P(f"foot.{s}") - ps.P(f"lowerleg01.{s}")) for s in SIDES}
    hip = {s: ps.P(f"upperleg01.{s}") + ps.root for s in SIDES}
    hz = hip["L"][2]
    l1, l2 = L["L"], S["L"]
    if kind == "dandasana":
        for s, sg in SIDES.items():
            ank = np.array([sg * 0.085, 0.075, hz + 0.98 * (l1 + l2)])
            ps.set_leg(s, ank, [0, 1, 0], foot_dir=unit([sg * 0.1, 1, 0.3]), sole_normal=[0, -0.3, 1], kneecap=[sg * 0.1, 1, 0])
        return
    if kind == "vajrasana":
        for s, sg in SIDES.items():
            knee_z = hz + np.sqrt(max(l1 ** 2 - (hip[s][1] - 0.075) ** 2 - 0.0, 0.01))
            ank = np.array([sg * 0.085, 0.075, knee_z - l2 * 0.995])
            ps.set_leg(s, ank, [sg * 0.05, -0.2, 1], foot_dir=unit([-sg * 0.1, -0.3, -1]), sole_normal=[sg * 0.2, 1, -0.3])
        return
    if kind == "sukhasana":
        # left foot tucked under the right thigh, right shin in front, right foot under the left knee
        ps.set_leg("L", [-0.115 * l1 / 0.42, 0.06, hz + 0.20 * l1 / 0.42], [1, 0.35, 0.35],
                   foot_dir=unit([-1, -0.05, 0.25]), sole_normal=unit([-0.2, 0.55, -0.8]))
        ps.set_leg("R", [0.135 * l1 / 0.42, 0.06, hz + 0.40 * l1 / 0.42], [-1, 0.35, 0.35],
                   foot_dir=unit([1, -0.05, 0.25]), sole_normal=unit([0.2, 0.55, -0.8]))
        return
    if kind in ("ardha_padmasana", "padmasana"):
        knee_y = 0.075 + getattr(ps, "knee_lift", 0.0)
        k = l1 / 0.42
        hy = hip["L"][1]
        # left foot on the right thigh (on top); padmasana: right foot on the left thigh (below),
        # ardha: right foot tucked under the left knee
        Lt = getattr(ps, "lotus", LOTUS)
        ankL = np.array([-Lt["top_x"] * k, hy + Lt["top_lift"], hz + Lt["top_fwd"] * k])
        ps.set_leg("L", ankL, _knee_pole(hip["L"], ankL, l1, l2, knee_y + 0.015, 1), foot_dir=unit(Lt["foot_dir"]),
                   sole_normal=unit(Lt["sole"]))
        if kind == "padmasana":
            ankR = np.array([Lt["low_x"] * k, hy + Lt["low_lift"], hz + Lt["low_fwd"] * k])
            ps.set_leg("R", ankR, _knee_pole(hip["R"], ankR, l1, l2, knee_y, -1), foot_dir=unit(np.multiply(Lt["foot_dir"], [-1, 1, 1])),
                       sole_normal=unit(np.multiply(Lt["sole"], [-1, 1, 1])))
        else:
            ankR = np.array([Lt["ard_x"] * k, 0.06, hz + Lt["ard_fwd"] * k])
            ps.set_leg("R", ankR, [-1, 0.35, 0.35], foot_dir=unit([1, -0.05, 0.3]), sole_normal=unit([0.2, 0.55, -0.8]))
        return
    raise ValueError(kind)


def _knee_pole(hip, ank, l1, l2, knee_y, side):
    best = None
    a = unit(ank - hip)
    e1 = unit(np.cross(a, [0, 1, 0]))
    e2 = np.cross(e1, a)
    for phi in np.radians(np.arange(0, 360, 2)):
        pole = np.cos(phi) * e1 + np.sin(phi) * e2
        k, _ = two_bone(hip, ank, l1, l2, pole)
        cost = (k[1] - knee_y) ** 2 + 0.05 * max(0, hip[2] - k[2]) ** 2 + 4 * max(0, 0.12 - (k[0] - hip[0]) * side) ** 2
        if best is None or cost < best[0]:
            best = (cost, pole)
    return best[1]


LOTUS = {"top_x": 0.075, "top_lift": 0.115, "top_fwd": 0.15, "low_x": 0.075, "low_lift": 0.07, "low_fwd": 0.11,
         "ard_x": 0.15, "ard_fwd": 0.27, "foot_dir": [-1, -0.12, 0.2], "sole": [0.1, 1, -0.35]}
# feet stay near the opposite hip crease (lotus) / under the opposite knee (ardha), cun-scaled metres
LOTUS_RANGE = {"top_x": (0.06, 0.16), "top_lift": (0.08, 0.20), "top_fwd": (0.09, 0.21),
               "low_x": (0.01, 0.12), "low_lift": (0.05, 0.15), "low_fwd": (0.07, 0.17),
               "ard_x": (0.11, 0.19), "ard_fwd": (0.22, 0.33)}
LOTUS_KEYS = {"padmasana": ["top_x", "top_lift", "top_fwd", "low_x", "low_lift", "low_fwd"],
              "ardha_padmasana": ["top_x", "top_lift", "top_fwd", "ard_x", "ard_fwd"]}


class Capsule:
    """Radius profile of a limb segment (bones `names`, axis head(a) -> head(b)) measured on the rest
    mesh; used to tell how deep posed vertices of another limb sink into it."""

    def __init__(self, ps, names, a, b, bins=12):
        self.ps, self.names, self.a, self.b = ps, names, a, b
        pa, pb = ps.P(a), ps.P(b)
        ax = pb - pa
        ln = np.linalg.norm(ax)
        m = np.isin(ps.dom, names)
        rel = ps.rest[m] - pa
        t = rel @ ax / ln ** 2
        r = np.linalg.norm(rel - np.outer(t, ax), axis=1)
        self.edges = np.linspace(0, 1, bins + 1)
        self.r = np.array([np.median(r[(t >= lo) & (t < hi)]) if np.any((t >= lo) & (t < hi)) else r.mean()
                           for lo, hi in zip(self.edges[:-1], self.edges[1:])])

    def depth(self, H, pts):
        """Penetration depth (m, >0 inside) of each point into the posed capsule; -inf off the segment."""
        pa, pb = H[self.ps.rig.index[self.a]], H[self.ps.rig.index[self.b]]
        ax = pb - pa
        t = (pts - pa) @ ax / (ax @ ax)
        d = np.linalg.norm(pts - pa - np.outer(t, ax), axis=1)
        k = np.clip((t * (len(self.r))).astype(int), 0, len(self.r) - 1)
        out = self.r[k] - d
        out[(t < 0.02) | (t > 0.98)] = -np.inf
        return out


class LotusProbe:
    """How the crossed legs touch each other: worst sinking (m, >0 = inside, <0 = gap) of a limb's
    vertices into another limb's capsule. Only leg vertices are skinned, so it is cheap."""

    def __init__(self, ps):
        self.ps = ps
        self.cap = {}
        for s in SIDES:
            self.cap[f"shin{s}"] = Capsule(ps, [f"lowerleg01.{s}", f"lowerleg02.{s}"], f"lowerleg01.{s}", f"foot.{s}")
            self.cap[f"thigh{s}"] = Capsule(ps, [f"upperleg01.{s}", f"upperleg02.{s}"], f"upperleg01.{s}", f"lowerleg01.{s}")
        sets = {}
        for s in SIDES:
            sets[f"shin{s}"] = np.isin(ps.dom, [f"lowerleg01.{s}", f"lowerleg02.{s}"])
            sets[f"foot{s}"] = np.char.startswith(ps.dom.astype(str), "foot.") & np.char.endswith(ps.dom.astype(str), "." + s)
        self.idx = np.flatnonzero(np.any(np.stack(list(sets.values())), axis=0))
        self.sets = {k: v[self.idx] for k, v in sets.items()}

    def __call__(self):
        ps = self.ps
        Q, H = ps.fk()
        pos = ps.rig.skin(ps.rest, ps.v, Q, H, idx=self.idx)

        def sink(part, cap):
            d = self.cap[cap].depth(H, pos[self.sets[part]])
            return float(np.max(d)) if np.isfinite(d).any() else -1.0
        r = {}
        for s, o in (("L", "R"), ("R", "L")):
            r[f"shin{s}_in_shin{o}"] = sink(f"shin{s}", f"shin{o}")
            r[f"foot{s}_in_thigh{o}"] = sink(f"foot{s}", f"thigh{o}")
            r[f"foot{s}_in_shin{o}"] = sink(f"foot{s}", f"shin{o}")
            r[f"shin{s}_in_thigh{o}"] = sink(f"shin{s}", f"thigh{o}")
        r["shins"] = max(r["shinL_in_shinR"], r["shinR_in_shinL"])
        r["kneeL_y"] = float(H[ps.rig.index["lowerleg01.L"]][1])
        r["kneeR_y"] = float(H[ps.rig.index["lowerleg01.R"]][1])
        return r


def lotus_overlap(ps, pos=None):
    return LotusProbe(ps)()


SINK_OK, GAP_OK, SHIN_OK = 0.010, 0.012, 0.004   # allowed overlap / air under a resting foot / shin-on-shin overlap


def tune_lotus(ps, pid):
    """Place the ankles so that the feet rest on the opposite thighs (no gap, no sinking), the top
    shin lies over the bottom one and the knees stay low. Pelvis height fixed; the caller re-seats
    the body afterwards."""
    probe = LotusProbe(ps)
    keys = LOTUS_KEYS[pid]
    x0 = np.array([LOTUS[k] for k in keys])

    def over(v, lim=SINK_OK):
        return max(0.0, v - lim) ** 2

    def gap(v):
        return max(0.0, -GAP_OK - v) ** 2

    def run(x):
        ps.lotus = dict(LOTUS)
        ps.lotus.update(dict(zip(keys, x)))
        ps.W = {}
        legs_seated(ps, pid)
        return probe()

    def cost(x):
        r = run(x)
        c = 1e5 * (over(r["shinL_in_shinR"], SHIN_OK) + over(r["shinR_in_shinL"], SHIN_OK))
        c += 1e4 * (over(r["footL_in_thighR"]) + gap(r["footL_in_thighR"]))
        c += 1e4 * (over(r["shinL_in_thighR"], 0.015) + over(r["shinR_in_thighL"], 0.015) + over(r["footL_in_shinR"]))
        if pid == "padmasana":
            c += 1e4 * (over(r["footR_in_thighL"]) + gap(r["footR_in_thighL"]) + over(r["footR_in_shinL"]))
        else:   # bottom foot on the floor under the top leg: just keep it out of the thigh and shin
            c += 1e4 * (over(r["footR_in_thighL"]) + over(r["footR_in_shinL"]))
        c += 200 * (max(0, r["kneeL_y"] - 0.09) ** 2 + max(0, r["kneeR_y"] - 0.09) ** 2)
        for k, v, v0 in zip(keys, x, x0):
            lo, hi = LOTUS_RANGE[k]
            c += 1e4 * (max(0, lo - v) ** 2 + max(0, v - hi) ** 2)
            c += (40 if k.startswith("ard") else 2) * (v - v0) ** 2
        return c
    best = None
    seeds = [x0]
    for dl in (0.04, 0.08):
        s = x0.copy()
        s[keys.index("top_lift")] += dl
        s[keys.index("top_x")] += dl * 0.5
        seeds.append(s)
    for s in seeds:
        x, f = nelder_mead(cost, s, 0.02, iters=400, tol=1e-10)
        x, f = nelder_mead(cost, x, 0.006, iters=200, tol=1e-11)
        if best is None or f < best[1]:
            best = (x, f)
    x = best[0]
    r = run(x)
    print("    tune", pid, "cost %.4f" % best[1], {k: round(v * 1000) for k, v in r.items()})
    return {k: round(v * 1000) for k, v in r.items()}, {k: round(float(ps.lotus[k]), 3) for k in keys}


def knee_top(ps, pos, s):
    """Top surface point of the posed knee/distal thigh, and the thigh direction."""
    Q, H = ps.fk()
    hip = H[ps.rig.index[f"upperleg01.{s}"]]
    knee = H[ps.rig.index[f"lowerleg01.{s}"]]
    near = np.linalg.norm(pos - knee, axis=1) < 0.07
    near &= np.isin(ps.dom, [f"upperleg02.{s}", f"lowerleg01.{s}", f"upperleg01.{s}"])
    top = pos[near][np.argmax(pos[near][:, 1])]
    return top, unit(knee - hip), knee, hip


def arms_on_knees(ps):
    """Palm up, back of the hand resting on the knee (or as close as the arm reaches)."""
    pos = ps.skin()
    for s, sg in SIDES.items():
        top, tdir, knee, hip = knee_top(ps, pos, s)
        Q, H = ps.fk()
        sh = H[ps.rig.index[f"upperarm01.{s}"]]
        reach = 0.985 * (np.linalg.norm(ps.P(f"lowerarm01.{s}") - ps.P(f"upperarm01.{s}"))
                         + np.linalg.norm(ps.P(f"wrist.{s}") - ps.P(f"lowerarm01.{s}")))
        horiz = unit(tdir * [1, 0, 1])
        fdir = unit(horiz + np.array([sg * 0.25, 0, 0.0]))
        wr = None
        for back in np.arange(0.06, 0.30, 0.005):
            cand = top + np.array([0, 0.022, 0]) - horiz * back
            # follow the thigh surface: drop with the thigh slope
            cand[1] = top[1] + 0.022 + max(0.0, -tdir[1]) * back * 0.0 + (hip[1] - knee[1]) * back / max(1e-6, np.linalg.norm((knee - hip) * [1, 0, 1])) * 0.85
            if np.linalg.norm(cand - sh) <= reach:
                wr = cand
                break
        if wr is None:
            wr = sh + unit(cand - sh) * reach
        ps.set_arm(s, wr, [sg * 1.0, -0.3, -0.6], hand_dir=unit(fdir + [0, -0.12, 0]), palm_normal=[sg * 0.25, 1, 0.0])


def arms_tadasana(ps):
    for s, sg in SIDES.items():
        sh = ps.P(f"upperarm01.{s}") + ps.root
        wr = sh + np.array([sg * 0.05, -0.43, 0.025])
        ps.set_arm(s, wr, [sg * 0.2, 0, -1], hand_dir=unit([sg * -0.05, -1, 0.06]), palm_normal=[-sg, 0, 0.1])


def arms_dandasana(ps):
    for s, sg in SIDES.items():
        Q, H = ps.fk()
        sh = H[ps.rig.index[f"upperarm01.{s}"]]
        hip = H[ps.rig.index[f"upperleg01.{s}"]]
        l = np.linalg.norm(ps.P(f"lowerarm01.{s}") - ps.P(f"upperarm01.{s}")) + np.linalg.norm(ps.P(f"wrist.{s}") - ps.P(f"lowerarm01.{s}"))
        x = hip[0] + sg * 0.13
        z = hip[2] + 0.02
        dxz = np.hypot(x - sh[0], z - sh[2])
        y = sh[1] - np.sqrt(max(0.0, (0.995 * l) ** 2 - dxz ** 2))
        wr = np.array([x, max(y, 0.07), z])
        # fingertips on the floor: pitch the hand forward-down just enough to reach y ~ 0.01
        lh = np.linalg.norm(ps.T(f"finger3-3.{s}") - ps.P(f"wrist.{s}")) + 0.012
        sn = np.clip((wr[1] - 0.012) / lh, 0, 1)
        d = unit([sg * 0.12 * np.sqrt(1 - sn ** 2), -sn, np.sqrt(1 - sn ** 2)])
        side = np.array([n.endswith("." + s) for n in ps.dom]) & ps.hand_mask
        for _ in range(8):  # flatten the hand until no part of it is below the floor
            d = unit([sg * 0.12 * np.sqrt(1 - sn ** 2), -sn, np.sqrt(1 - sn ** 2)])
            nrm = np.array([-sg * 0.2, -1.0, 0])
            nrm = unit(nrm - d * np.dot(nrm, d))
            ps.set_arm(s, wr, [sg * 0.3, 0, -1], hand_dir=d, palm_normal=nrm)
            low = ps.skin()[side][:, 1].min() + ps.root[1] * 0
            if low >= -0.004:
                break
            sn = max(0.0, sn - (-low + 0.004) / lh)


def chest_front(ps, y, xr=0.12):
    band = (np.abs(ps.rest[:, 1] - y) < 0.03) & (np.abs(ps.rest[:, 0]) < xr) & ~ps.hand_mask
    return ps.rest[band][:, 2].max()


def body_pose(rig, variant, rest, pid, hands):
    ps = Poser(rig, variant, rest)
    seated = pid in ("sukhasana", "ardha_padmasana", "padmasana", "vajrasana", "dandasana")
    hipy = ps.P("upperleg01.L")[1]
    if pid == "stand":
        return ps, {}
    if pid in ("tadasana", "vrikshasana"):
        if pid == "vrikshasana":
            ps.root = np.array([-0.045, 0, 0])
            ankR = ps.P("foot.R") * [0, 1, 1] + [-0.075 + ps.root[0] * 0.3, 0.0, 0.0]
            ps.set_leg("R", ankR, [0, 0, 1], foot_dir=unit([-0.1, 0, 1]), sole_normal=[0, -1, 0], kneecap=[0, 0, 1])
            Q, H = ps.fk()
            # left sole against the inner right thigh, heel high, knee out to the side
            thigh_x = H[rig.index["upperleg01.R"]][0] * 0.7 + ankR[0] * 0.3
            ankL = np.array([thigh_x + 0.12, ps.P("upperleg01.L")[1] - 0.205, ps.P("upperleg01.L")[2] + 0.025])
            ps.set_leg("L", ankL, [1, 0.05, 0.12], foot_dir=unit([0.05, -1, 0.3]), sole_normal=unit([-1, 0.0, 0.1]))
            ps.W.update({k: v for k, v in hands["anjali"].items()})
        else:
            for s, sg in SIDES.items():
                ank = ps.P(f"foot.{s}") * [0, 1, 1] + [sg * 0.075, 0, 0]
                ps.set_leg(s, ank, [0, 0, 1], foot_dir=unit([sg * 0.1, 0, 1]), sole_normal=[0, -1, 0], kneecap=[0, 0, 1])
            arms_tadasana(ps)
        pos, g = ps.ground()
        ps.root = ps.root + [0, g, 0]
        return ps, {}
    # seated: iterate root height so the buttocks touch the floor
    hip_h = 0.105 if pid != "vajrasana" else 0.235
    ps.knee_lift = 0.0
    butt = (rest[:, 2] < ps.P("upperleg01.L")[2] + 0.02) & (np.abs(rest[:, 0]) < 0.16) & \
           (rest[:, 1] > hipy - 0.20) & (rest[:, 1] < hipy + 0.05) & ~ps.hand_mask
    lotus = pid in ("padmasana", "ardha_padmasana")
    for rnd_ in range(2 if lotus else 1):
        if rnd_ == 1:
            ps.tune = tune_lotus(ps, pid)
        for it in range(7):
            ps.root = np.array([0, hip_h - hipy, 0])
            ps.W = {}
            legs_seated(ps, pid)
            pos = ps.skin()
            bmin = pos[butt][:, 1].min()
            if pid == "vajrasana":
                break
            low = pos[~ps.hand_mask & ~butt][:, 1].min()
            if lotus and rnd_ == 0 and low < bmin - 0.003:
                ps.knee_lift = min(0.05, ps.knee_lift + bmin - low)   # knees lower than the buttocks: lift them
            hip_h -= bmin
    if pid == "dandasana":
        arms_dandasana(ps)
    else:
        arms_on_knees(ps)
    pos, g = ps.ground()
    ps.root = ps.root + [0, g, 0]
    pos = ps.skin()
    body = pos[~ps.hand_mask]
    butt = (rest[:, 2] < ps.P("upperleg01.L")[2] + 0.02) & (np.abs(rest[:, 0]) < 0.16) & \
           (rest[:, 1] > hipy - 0.20) & (rest[:, 1] < hipy + 0.05) & ~ps.hand_mask
    info = {"buttock_y": float(pos[butt][:, 1].min()), "body_min": float(body[:, 1].min()),
            "hand_min": float(pos[ps.hand_mask][:, 1].min())}
    if lotus:
        ov = lotus_overlap(ps, pos)
        print("   ", pid, "overlap mm", {k: round(v * 1000) for k, v in ov.items()}, "lifts", ps.tune[1])
    return ps, info


# ------------------------------------------------------------------ hands
class Hand:
    """Left-hand finger model in the rest frame (wrist fixed)."""

    def __init__(self, ps):
        self.ps = ps
        rig = ps.rig
        self.d0, self.n0 = ps.hand_frame0("L")
        P, T = ps.P, ps.T
        self.lit = unit(P("finger5-1.L") - P("finger2-1.L"))
        self.axes = {}
        for k in range(2, 6):
            for j in range(1, 4):
                b = f"finger{k}-{j}.L"
                d = unit(T(b) - P(b))
                self.axes[b] = unit(np.cross(d, self.n0))
        # thumb pad direction: toward the palm and the index finger
        for j in range(1, 4):
            b = f"finger1-{j}.L"
            d = unit(T(b) - P(b))
            toward = P("finger2-1.L") - P(b)
            toward = unit(toward - d * np.dot(toward, d))
            pad = unit(0.55 * toward + 0.45 * (self.n0 - d * np.dot(self.n0, d)))
            self.axes[b] = unit(np.cross(d, pad))
        self.thumb_basis = (self.axes["finger1-1.L"], self.n0, unit(T("finger1-1.L") - P("finger1-1.L")))
        # fingertip centres and radii from the skin (distal 6 mm of each finger)
        self.tip, self.rad = {}, {}
        for k in range(1, 6):
            b = f"finger{k}-3.L"
            d = unit(T(b) - P(b))
            m = ps.dom == b
            pts = ps.rest[m]
            proj = (pts - P(b)) @ d
            cap = pts[proj > proj.max() - 0.006]
            c = cap.mean(axis=0)
            axis_pt = P(b) + d * np.dot(c - P(b), d)
            self.tip[k] = c
            self.rad[k] = float(np.mean(np.linalg.norm(cap - axis_pt - d * ((cap - axis_pt) @ d)[:, None], axis=1)))
        self.chain = {k: ([f"metacarpal{k - 1}.L"] if k > 1 else []) + [f"finger{k}-{j}.L" for j in range(1, 4)] for k in range(1, 6)}

    def tips(self, loc):
        """Fingertip centres for local finger rotations (wrist at rest)."""
        P = self.ps.P
        out = {}
        for k, chain in self.chain.items():
            Q = ID
            H = P(chain[0])
            prev = None
            for b in chain:
                if prev is not None:
                    H = H + qrot(Q, P(b) - P(prev))
                Q = qmul(Q, loc.get(b, ID))
                prev = b
            out[k] = H + qrot(Q, self.tip[k] - P(chain[-1]))
        return out

    def finger(self, k, mcp, pip, dip=None, spread=0.0):
        dip = 0.7 * pip if dip is None else dip
        b1, b2, b3 = (f"finger{k}-{j}.L" for j in range(1, 4))
        sgn = np.sign(np.dot(np.cross(self.n0, self.d0), self.lit))
        return {b1: qmul(qaxis(self.axes[b1], mcp), qaxis(self.n0, sgn * spread)),
                b2: qaxis(self.axes[b2], pip), b3: qaxis(self.axes[b3], dip)}

    def thumb(self, r, ip1, ip2):
        e1, e2, e3 = self.thumb_basis
        rv = r[0] * e1 + r[1] * e2 + r[2] * e3
        ang = np.linalg.norm(rv)
        q1 = qaxis(rv, ang) if ang > 1e-6 else ID
        return {"finger1-1.L": q1, "finger1-2.L": qaxis(self.axes["finger1-2.L"], ip1),
                "finger1-3.L": qaxis(self.axes["finger1-3.L"], ip2)}


RELAX = {2: (6, 8), 3: (7, 9), 4: (8, 10), 5: (9, 11)}
# relaxed hand (council): MCP 10-25, PIP 15-35, DIP 10-20, more curl toward the little finger
RELAXED_CURL = {2: (12, 18, 10), 3: (15, 22, 12), 4: (18, 26, 14), 5: (22, 30, 16)}
# fingers almost parallel: fan angle from the middle finger in the palm plane (deg, sign kept)
FAN = {2: 3.0, 3: 0.0, 4: 3.0, 5: 7.0}


def fan_spread(hand):
    """Spread (deg, for Hand.finger) that turns each finger from the MakeHuman rest fan to FAN."""
    ps, n0 = hand.ps, hand.n0
    sgn = np.sign(np.dot(np.cross(n0, hand.d0), hand.lit))
    def dirp(k):
        d = unit(ps.T(f"finger{k}-1.L") - ps.P(f"finger{k}-1.L"))
        return unit(d - n0 * np.dot(d, n0))
    dm = dirp(3)
    out = {}
    for k in range(2, 6):
        dk = dirp(k)
        a = np.degrees(np.arctan2(np.dot(np.cross(dm, dk), n0), np.dot(dm, dk)))
        want = np.sign(a) * FAN[k] if abs(a) > 0.5 else 0.0
        out[k] = (want - a) * sgn
    return out


def rest_flex(ps, k):
    """Absolute flexion (deg) of MCP, PIP, DIP of finger k in the MakeHuman rest pose (already curled)."""
    first = f"finger{k}-1.L"
    chain = [ps.rig.names[ps.rig.parent[ps.rig.index[first]]], first, f"finger{k}-2.L", f"finger{k}-3.L"]
    dirs = [unit(ps.T(n) - ps.P(n)) for n in chain]
    return np.array([np.degrees(np.arccos(np.clip(np.dot(dirs[i], dirs[i + 1]), -1, 1))) for i in range(3)])


def absolute_curl(hand, k, target):
    """Hand.finger() angles are relative to the rest pose; turn absolute joint angles into them."""
    return tuple(np.asarray(target, float) - rest_flex(hand.ps, k))


def relaxed_hand(hand, curl=RELAXED_CURL, skip=()):
    sp = fan_spread(hand)
    loc = {}
    for k in range(2, 6):
        if k in skip:
            continue
        loc.update(hand.finger(k, *absolute_curl(hand, k, curl[k]), spread=sp[k]))
    loc.update(hand.thumb(np.array([8.0, 0.0, 0.0]), 8.0, 6.0))
    return loc


# soft, slightly cupped fingers (straight ones looked like boards)
DHYANA_CURL = {2: (12, 16, 8), 3: (13, 17, 9), 4: (15, 19, 10), 5: (17, 22, 12)}
# a palm lying on the thigh (sukhasana, vajrasana): the fingers follow the thigh, nearly flat; with the
# relaxed hanging curl the fingertips went 9-14 mm into the knee once the palm itself lay on the thigh
THIGH_CURL = {2: (5, 7, 4), 3: (6, 8, 4), 4: (7, 9, 5), 5: (8, 11, 6)}


def thigh_fingers(hand):
    """Hand lying palm down on the thigh: nearly flat fingers, the thumb in the palm plane tilted a little
    toward the back (the relaxed thumb hung below the palm and went 8-12 mm into the thigh in vajrasana)."""
    loc = relaxed_hand(hand, THIGH_CURL)
    loc.update({k: v for k, v in flat_hand(hand, thumb=35, thumb_tilt=10).items() if k.startswith("finger1-")})
    return loc


def dhyana_fingers(hand, thumb=(20.0, -10.0, 0.0), ip=(5.0, 3.0)):
    """Dhyana hands: fingers almost straight and together, the thumb lifted off the index side."""
    sp = fan_spread(hand)
    loc = {}
    for k in range(2, 6):
        # the full fan spread: half of it fanned the fingers 10 deg apart (check_poses allows 5)
        loc.update(hand.finger(k, *absolute_curl(hand, k, DHYANA_CURL[k]), spread=sp[k]))
    loc.update(hand.thumb(np.asarray(thumb, float), *ip))
    return loc


def dhyana_thumbs(ps, hand, W, root):
    """Thumb poses that make the two thumb tips touch above the palms once the arms of the pose are set
    (W world rotations, root). Each thumb has its own angles: the right hand lies 1.5 cm higher, and
    one mirrored thumb pose left the tips 2 cm apart. Returns (finger locals of both hands, info);
    the .R keys are explicit, compose() only mirrors .L keys that have no .R twin."""
    rig = ps.rig
    ps.W, ps.root = W, root
    base = ps.local()
    tipL = hand.tip[1]
    b = "finger1-3"
    PL, PR = ps.P(f"{b}.L"), ps.P(f"{b}.R")
    tipR = tipL * np.array([-1, 1, 1])
    rad = hand.rad[1]
    iL, iR = rig.index[f"{b}.L"], rig.index[f"{b}.R"]
    mL, mR = rig.index["finger1-1.L"], rig.index["finger1-1.R"]

    def build(x):
        fL = dhyana_fingers(hand, x[0:3], x[3:5])
        fR = dhyana_fingers(hand, x[5:8], x[8:10])
        loc = dict(fL)
        loc.update({k.replace(".L", ".R"): pk.qmirror(np.asarray(q, float)) for k, q in fR.items()})
        return loc

    def tips(x):
        loc = dict(base)
        f = build(x)
        loc.update(f)
        Q, H = rig.fk(ps.v, loc, root)
        return H[iL] + qrot(Q[iL], tipL - PL), H[iR] + qrot(Q[iR], tipR - PR), H, f, Q

    def lim(ip1, ip2):
        return 1e-2 * (max(0, -ip1 - 10) ** 2 + max(0, ip1 - 50) ** 2 + max(0, -ip2 - 15) ** 2 + max(0, ip2 - 60) ** 2)

    # skin of each hand without its thumb (fixed while the thumbs move): a lifted thumb must not go into
    # the other hand (the left one went 6 mm into the right palm)
    from check_poses import vertex_normals
    loc0 = dict(base)
    loc0.update(build(np.array([20, -10, 0, 5, 3] * 2, float)))
    pos0 = rig.skin(ps.rest, ps.v, *rig.fk(ps.v, loc0, root))
    nrm0 = vertex_normals(pos0, pk.load_glb(pk.GLB[ps.v])[0][1])
    thumb_b = np.isin(np.array([n.split(".")[0] for n in ps.dom]), ["finger1-1", "finger1-2", "finger1-3", "metacarpal1"])
    rest_hand = {s: np.flatnonzero(ps.hand_mask & ~thumb_b & np.char.endswith(ps.dom.astype(str), f".{s}"))[::2] for s in SIDES}
    seg = [(f"finger1-{j}", t) for j in (2, 3) for t in (0.0, 0.35, 0.7, 1.0)]

    def thumb_pen(H, Q, s):
        o = "R" if s == "L" else "L"
        pts = []
        for bn, t in seg:
            i = rig.index[f"{bn}.{s}"]
            tail = H[i] + qrot(Q[i], ps.T(f"{bn}.{s}") - ps.P(f"{bn}.{s}"))
            pts.append(H[i] + (tail - H[i]) * t)
        pts = np.array(pts)
        V, N = pos0[rest_hand[o]], nrm0[rest_hand[o]]
        j = ((pts[:, None] - V[None]) ** 2).sum(-1).argmin(1)
        sd = ((pts - V[j]) * N[j]).sum(-1)
        return float(np.sum(np.maximum(0.0, 0.8 * rad - sd) ** 2))

    def cost(x):
        a, c, H, _, Q = tips(x)
        v = 4e4 * (thumb_pen(H, Q, "L") + thumb_pen(H, Q, "R"))
        # just touching (the old target pressed them 1.5 mm into each other)
        gap = np.linalg.norm(a - c) - (2 * rad + 0.0005)
        v += 4e4 * gap ** 2
        # the tips meet in front of the thumb bases and above them, never bent back toward the belly
        # (they went 1 cm into the lower belly)
        mid = 0.5 * (a + c)
        zb = 0.5 * (H[mL][2] + H[mR][2])
        # halfway between the thumb bases: above the higher (right) one the left thumb stood up almost
        # vertically to reach the right one, which lies ~1.5 cm higher on the left hand
        yb = 0.5 * (H[mL][1] + H[mR][1])
        v += 4e4 * max(0.0, zb - 0.005 - mid[2]) ** 2 + 4e4 * max(0.0, yb - mid[1]) ** 2
        for o in (0, 5):
            v += 2e-5 * float(np.sum(x[o:o + 3] ** 2)) + 2e-4 * float(np.sum(x[o + 3:o + 5] ** 2)) + lim(x[o + 3], x[o + 4])
        v += 1e-4 * float(np.sum((x[0:5] - x[5:10]) ** 2))
        return v
    best = None
    for seed in ([20, -10, 0, 5, 3], [35, 10, 0, 10, 5], [10, -30, 10, 0, 0], [40, -25, -10, 15, 10],
                 [55, -40, 0, -5, -5], [60, 0, 20, 10, 10], [30, -50, -20, 20, 15]):
        s = np.array(seed * 2, float)
        x, f = nelder_mead(cost, s, 10.0, iters=900)
        x, f = nelder_mead(cost, x, 3.0, iters=600)
        if best is None or f < best[1]:
            best = (x, f)
    x, f = best
    a, c, H, loc, Q = tips(x)
    return loc, {"thumb_pen_mm": round(1000 * max(np.sqrt(thumb_pen(H, Q, "L")), np.sqrt(thumb_pen(H, Q, "R"))), 1),"thumb_gap_mm": round(float(np.linalg.norm(a - c) - 2 * rad) * 1000, 1), "x": np.round(x, 1).tolist(),
                 "tips_fwd_mm": round(float(0.5 * (a + c)[2] - 0.5 * (H[mL][2] + H[mR][2])) * 1000, 1)}


def dhyana_score(ctx, W, root, floc, info, finfo):
    """How far a lotus dhyana is from right, in mm-like units measured as check_poses does: thumb tip gap,
    hand in hand beyond 3 mm, forearm/hand in the trunk beyond 4 mm, hands off their support."""
    from check_poses import Body, surface_sd, vertex_normals
    if not hasattr(ctx, "cb"):
        ctx.cb = Body(ctx.rig, ctx.ps.v)
    cb, ps, rig = ctx.cb, ctx.ps, ctx.rig
    ps.W, ps.root = W, root
    loc = ps.local()
    loc.update(floc)
    Q, H = rig.fk(ps.v, loc, root)
    pos = rig.skin(ps.rest, ps.v, Q, H)
    nrm = vertex_normals(pos, cb.tris)
    hh = -min(surface_sd(cb, pos, nrm, cb.sets["handR"], cb.sets["handL"]).min(),
              surface_sd(cb, pos, nrm, cb.sets["handL"], cb.sets["handR"]).min()) * 1000
    trunk = np.flatnonzero(np.isin(cb.region, ["torso", "hips"]))
    tr = 0.0
    for s in SIDES:
        fore = np.flatnonzero((np.isin(cb.base, ["lowerarm01", "lowerarm02"]) | cb.is_hand) & (cb.side == s))
        tr = max(tr, -float(surface_sd(cb, pos, nrm, fore, trunk).min()) * 1000)
    cL, cR = info["arms"]["L"]["contact_mm"], info["arms"]["R"]["contact_mm"]
    miss = max(-4 - cL, cL - 8, 0) + max(-2 - cR, cR - 8, 0)
    tg = max(0.0, finfo["thumb_gap_mm"])
    # the right palm lies over the left one, not in front of it (one setting put it 9 cm forward with
    # only the thumb tips touching)
    pc = {s: pos[cb.palm[s]].mean(axis=0) for s in SIDES}
    dz = abs(pc["R"][2] - pc["L"][2]) * 1000
    score = tg + 2 * max(0.0, hh - 3) + 2 * max(0.0, tr - 4) + miss + 0.5 * max(0.0, dz - 25)
    return score, {"thumb": round(tg, 1), "hands": round(max(0.0, hh), 1), "trunk": round(max(0.0, tr), 1), "cL": cL, "cR": cR,
                   "dz": round(dz, 1)}


def mudra_touch(hand, targets):
    """Thumb tip touches the tips of `targets`; other fingers relaxed straight."""
    rad = hand.rad

    sp = fan_spread(hand)
    # free fingers almost straight (absolute flexion <= 20 deg per joint) and together
    straight = {k: absolute_curl(hand, k, v) for k, v in {2: (6, 9, 6), 3: (7, 10, 6), 4: (9, 12, 7), 5: (11, 14, 8)}.items()}

    def build(x):
        loc = {}
        for k in range(2, 6):
            if k in targets:
                i = 3 + 2 * targets.index(k)
                loc.update(hand.finger(k, x[i], x[i + 1], spread=sp[k] * 0.5))
            else:
                loc.update(hand.finger(k, *straight[k], spread=sp[k] * 0.5))
        loc.update(hand.thumb(x[0:3] * 0 + x[0:3], x[3 + 2 * len(targets)], x[4 + 2 * len(targets)]))
        return loc

    def cost(x):
        tp = hand.tips(build(x))
        c = 0.0
        for k in targets:
            dist = np.linalg.norm(tp[1] - tp[k])
            c += 4e4 * (dist - (rad[1] + rad[k] - 0.0015)) ** 2
        if len(targets) == 2:
            a, b = targets
            dist = np.linalg.norm(tp[a] - tp[b])
            c += 4e4 * max(0.0, dist - (rad[a] + rad[b] + 0.002)) ** 2
        # natural ranges and gentle preference for smooth curls
        for i in range(len(targets)):
            mcp, pip = x[3 + 2 * i], x[4 + 2 * i]
            c += 1e-4 * ((mcp - 35) ** 2 + (pip - 45) ** 2)
            c += 1e-2 * (max(0, -mcp) ** 2 + max(0, mcp - 85) ** 2 + max(0, -pip) ** 2 + max(0, pip - 100) ** 2)
        ip1, ip2 = x[3 + 2 * len(targets)], x[4 + 2 * len(targets)]
        c += 1e-4 * (ip1 ** 2 + ip2 ** 2 + np.sum(x[0:3] ** 2) * 0.5)
        c += 1e-2 * (max(0, -ip1 - 10) ** 2 + max(0, ip1 - 60) ** 2 + max(0, -ip2 - 15) ** 2 + max(0, ip2 - 70) ** 2)
        return c

    n = 5 + 2 * len(targets)
    best = None
    for seed in ([30, 10, 0], [45, -15, 10], [55, 15, -10], [20, -30, 20]):
        x0 = np.zeros(n)
        x0[0:3] = seed
        for i in range(len(targets)):
            x0[3 + 2 * i], x0[4 + 2 * i] = 35, 45
        x0[3 + 2 * len(targets)], x0[4 + 2 * len(targets)] = 15, 15
        x, f = nelder_mead(cost, x0, 12.0, iters=2500)
        x, f = nelder_mead(cost, x, 3.0, iters=1500)
        if best is None or f < best[1]:
            best = (x, f)
    x = best[0]
    loc = build(x)
    tp = hand.tips(loc)
    gaps = {k: round(float(np.linalg.norm(tp[1] - tp[k]) - rad[1] - rad[k]) * 1000, 1) for k in targets}
    return loc, {"cost": round(float(best[1]), 5), "gap_mm": gaps, "x": np.round(x, 1).tolist()}


# metacarpal flexion (deg) toward the palm: middle, ring, little (6/8/13 left the little-finger side of
# the palm 10-15 mm off the other hand while the heels of the hands met)
# metacarpal flexion (deg) toward the palm: middle, ring, little. A light cup: flat (0) left the little-finger
# side off the other hand, 6/11/19 fanned the fingers out as seen from the side (council 2026-11-09)
ANJALI_CUP = {2: 3.0, 3: 5.0, 4: 9.0}


def flat_hand(hand, spread=None, thumb=None, thumb_tilt=0.0):
    """Fingers straightened into the palm plane (undo the rest curl), optional spread (deg); the thumb
    `thumb` deg from the middle finger, tilted `thumb_tilt` deg out of the palm plane toward the back."""
    loc = {}
    ps = hand.ps
    n0 = hand.n0
    sgn = np.sign(np.dot(np.cross(n0, hand.d0), hand.lit))
    dm = unit(ps.T("finger3-1.L") - ps.P("finger3-1.L"))
    dm = unit(dm - n0 * np.dot(dm, n0))
    for k in range(2, 6):
        parent_world = ID
        # straight finger in the palm plane, fanned by spread[k] degrees from the middle finger
        target = qrot(qaxis(n0, sgn * (spread or {}).get(k, 0.0)), dm)
        for j in range(1, 4):
            b = f"finger{k}-{j}.L"
            d = unit(ps.T(b) - ps.P(b))
            world = pk.swing(d, target)
            loc[b] = qmul(qconj(parent_world), world)
            parent_world = world
    if thumb is None:
        return loc
    # thumb laid into the palm plane, `thumb` degrees from the middle finger toward the radial side
    target = qrot(qaxis(n0, -sgn * thumb), dm)
    tl = np.radians(thumb_tilt)
    target = unit(target * np.cos(tl) - n0 * np.sin(tl))
    parent_world = ID
    for j in range(1, 4):
        b = f"finger1-{j}.L"
        d = unit(ps.T(b) - ps.P(b))
        world = pk.swing(d, target)
        loc[b] = qmul(qconj(parent_world), world)
        parent_world = world
    return loc


def anjali_fingers(ps, hand, sp, thumb_tilt=0.0):
    loc = flat_hand(hand, spread=sp, thumb=32, thumb_tilt=thumb_tilt)
    # the ulnar side of a real palm curves toward the palm (4th/5th carpometacarpal flexion); the flat
    # MakeHuman palm kept the ring and little fingers 1-2 cm off the other hand
    for k, ang in ANJALI_CUP.items():
        b = f"metacarpal{k}.L"
        dmc = unit(ps.T(b) - ps.P(b))
        loc[b] = qaxis(unit(np.cross(dmc, hand.n0)), ang)
    return loc


def anjali_thumb_tilt(ps, hand, sp, arms):
    """Smallest tilt of the thumbs toward the back of the hand that keeps the left thumb on its own side
    of the mid plane: in the palm plane the two thumbs went up to 1.8 cm into each other (neutral body)."""
    rig = ps.rig
    # the two distal phalanges: the base (finger1-1) sits on the palm edge and barely moves with the tilt
    thumb = np.flatnonzero(np.isin(ps.dom, ["finger1-2.L", "finger1-3.L"]))

    def min_x(tilt):
        loc = dict(arms)
        loc.update(anjali_fingers(ps, hand, sp, tilt))
        Q, H = rig.fk(ps.v, loc)
        return float(rig.skin(ps.rest, ps.v, Q, H, idx=thumb)[:, 0].min())
    for tilt in range(0, 31, 2):
        if min_x(tilt) >= 0.0:
            return tilt
    return 30


def palm_offset(ps, loc_fingers):
    """Max palmar extent (along n0) of the hand skin for the given finger pose, wrist at rest."""
    W = {}
    sub = Poser(ps.rig, ps.v, ps.rest)
    pos = sub.rig.skin(ps.rest, ps.v, *ps.rig.fk(ps.v, loc_fingers))
    d0, n0 = ps.hand_frame0("L")
    # palm + fingers 2-5 (the thumb lies alongside and must not decide the contact plane)
    side = np.array([n.endswith(".L") and not n.startswith("finger1") for n in ps.dom]) & ps.hand_mask
    rel = (pos[side] - ps.P("wrist.L")) @ n0
    return rel.max(), pos, side


def world_hand_rot(ps, s, hand_dir, palm_normal):
    d0, n0 = ps.hand_frame0(s)
    return pk.frame_rot(d0, n0, hand_dir, palm_normal)


def arms_for_hands(ps, hand, loc_fingers, hand_dir, palm_normal, center_y, center_z, contact_x, pole, ref="tips"):
    """Both arms placed so the (left) hand with loc_fingers has its palm (ref='palm') or its
    fingertips (ref='tips') at x = contact_x, mirrored for the right hand."""
    Rh = world_hand_rot(ps, "L", hand_dir, palm_normal)
    wr0 = ps.P("wrist.L")
    if ref == "palm":
        _, pos, side = palm_offset(ps, loc_fingers)
        rel = (pos[side] - wr0) @ pk.qmat(Rh).T
        xs = rel[:, 0].min()
    else:
        tp = hand.tips(loc_fingers)
        xs = np.mean([qrot(Rh, tp[k] - wr0)[0] for k in tp])
    mid = qrot(Rh, ps.P("finger3-1.L") - wr0)
    wrist = np.array([contact_x - xs, center_y - mid[1], center_z - mid[2]])
    out = {}
    for s, sg in SIDES.items():
        w = wrist * [sg, 1, 1]
        hd = np.asarray(hand_dir) * [sg, 1, 1]
        pn = np.asarray(palm_normal) * [sg, 1, 1]
        el, wr, tau, res = ps.set_arm(s, w, np.asarray(pole) * [sg, 1, 1], hd, pn)
        out[s] = (round(float(tau), 1), round(float(res), 1))
    loc = ps.local()
    arms = {}
    for s in SIDES:
        for b in ARM_BONES:
            n = f"{b}.{s}"
            if n in loc:
                arms[n] = loc[n]
    return arms, out


def arms_anatomy(ps, hand, loc_fingers, hand_dir, palm_normal, center_y, center_z, contact_x, ref, slope_deg=20.0):
    """Both arms from anatomical angles (shoulder flex/abd/rot, elbow, supination, wrist flexion), solved
    so the left hand has the requested frame, its palm (ref='palm') or fingertips (ref='tips') reach
    x = contact_x, the middle-finger base sits at (center_y, center_z) and the forearm drops ~slope_deg
    from the wrist to the elbow. The right arm uses the same angles (mirror). Returns (arm locals, info)."""
    from anatomy import Anatomy
    an = Anatomy(ps)
    rig = ps.rig
    hand_dir, palm_normal = unit(hand_dir), unit(palm_normal)
    d0, n0 = ps.hand_frame0("L")
    left = np.array([n.endswith(".L") for n in ps.dom]) & ps.hand_mask
    palm_side = left & np.array([not n.startswith("finger1") for n in ps.dom])
    if ref == "palm":
        # the palmar surface (as check_poses measures it): palm-side vertices facing the palm direction
        from check_poses import vertex_normals
        tris = pk.load_glb(pk.GLB[ps.v])[0][1]
        rn = vertex_normals(ps.rest, tris)
        wr0 = ps.P("wrist.L")
        dn = unit(ps.P("finger3-1.L") - wr0)
        palm_side &= (rn @ n0 > 0.5) & ((ps.rest - wr0) @ dn > 0.0)
    idx = np.flatnonzero(palm_side)
    # wrist extension measured exactly as check_poses does (relative to the rest hand): the anatomy
    # angle x[5] is ~14 deg off it on the neutral body, which passed -74 here and failed with 88 there
    from check_poses import Body, swing_vec
    cb = Body(rig, ps.v)
    if ref == "palm":
        # the palm vertices exactly as check_poses picks them: the set above (other normals, other hand
        # axis) missed heel-of-hand vertices that went 2-3 mm past the mid plane
        idx = cb.palm["L"]
    dh, _th, nh = cb.hand["L"]
    ext_axis = unit(np.cross(dh, nh))
    iA, iW = rig.index["lowerarm02.L"], rig.index["wrist.L"]
    # forearm out of the trunk (the elbow end went 7-9 mm into the flank once the elbows dropped)
    from asanas import TorsoModel
    base_n = np.array([n.split(".")[0] for n in ps.dom.astype(str)])
    limb = np.array([bn.startswith(("upperleg", "lowerleg", "foot", "toe", "upperarm", "lowerarm", "wrist", "finger", "metacarpal",
                                    "neck", "head", "jaw", "eye", "tongue", "clavicle", "shoulder", "breast")) for bn in base_n])
    torso = TorsoModel(ps.rest, ~limb & ~ps.hand_mask)
    fore_idx = np.flatnonzero(np.isin(ps.dom.astype(str), ["lowerarm01.L", "lowerarm02.L"]))[::2]
    fingers = dict(loc_fingers)
    fingers.update({k.replace(".L", ".R"): pk.qmirror(v) for k, v in loc_fingers.items()})
    # shoulder flex/abd/rot, elbow, supination, wrist flexion (extension >= -78: the check allows 80)
    # pronation down to -75 (check_poses allows -85): at -40 the neutral body could not turn the palms
    # flat onto each other and they stood 1.5 cm apart in the middle
    rng = ((-10, 85), (0, 70), (-68, 40), (40, 150), (-75, 110), (-78, 40))

    def world(x):
        W = {}
        for s in SIDES:
            W.update(an.arm(s, shoulder=tuple(x[:3]), elbow=x[3], sup=x[4], wrist=(x[5], 0.0)))
        return W

    def pose(x):
        ps.W = world(x)
        loc = ps.local()
        loc.update(fingers)
        Q, H = rig.fk(ps.v, loc, ps.root)
        return Q, H

    def terms(x):
        Q, H = pose(x)
        Wh = Q[rig.index["wrist.L"]]
        t = {}
        # the bone-based palm normal n0 is ~10 deg off the palm skin: weighted as much as the direction it
        # rolled the hands so only the index fingers touched and the little fingers stood 1-1.5 cm apart
        # (seen from the front the fingers made an X); with ref='palm' the skin decides the roll
        # (weight 6 still held the neutral hands rolled: index on the other hand, little finger 1.4 cm off)
        wn = 60 if ref != "palm" else 1
        t["dir"] = (60 if ref != "palm" else 30) * float(np.sum((qrot(Wh, d0) - hand_dir) ** 2))
        t["normal"] = wn * float(np.sum((qrot(Wh, n0) - palm_normal) ** 2))
        pos = rig.skin(ps.rest, ps.v, Q, H, idx=idx)
        if ref == "palm":
            # the whole palmar surface lies in the mid plane, nothing crosses it
            t["flat"] = 8e4 * float(np.mean((pos[:, 0] - contact_x) ** 2))
            # the heels of the hands (wrist skin) went 2-4 mm past the mid plane at 2e5 here
            t["cross"] = 2e6 * float(np.mean(np.minimum(pos[:, 0], 0.0) ** 2)) + 3e6 * max(0.0, -0.0012 - float(pos[:, 0].min())) ** 2
        else:
            tp = np.mean([H[rig.index[f"finger{k}-3.L"]] for k in range(2, 6)], axis=0)
            t["flat"] = 4e4 * (tp[0] - contact_x) ** 2
        mid = H[rig.index["finger3-1.L"]]
        t["centre"] = 3e3 * ((mid[1] - center_y) ** 2 + (mid[2] - center_z) ** 2)
        el, wr = H[rig.index["lowerarm01.L"]], H[rig.index["wrist.L"]]
        sl = (wr[1] - el[1]) / max(1e-6, np.linalg.norm(wr - el))
        t["slope"] = 40 * (sl - np.sin(np.radians(slope_deg))) ** 2
        ext = -float(np.dot(swing_vec(qmul(qconj(Q[iA]), Q[iW]), dh), ext_axis))
        t["wrist"] = 20.0 * max(0.0, ext - 77.0) ** 2
        fp = rig.skin(ps.rest, ps.v, Q, H, idx=fore_idx)
        t["trunk"] = 3e4 * max(0.0, float(torso.depth(fp).max()) + 0.004) ** 2
        t["bounds"] = sum(20.0 * (max(0, lo - v) ** 2 + max(0, v - hi) ** 2) for (lo, hi), v in zip(rng, x))
        return t

    def cost(x):
        return sum(terms(x).values())
    best = None
    for x0 in ([40, 35, -50, 110, 30, -60], [30, 25, -60, 120, 50, -45], [50, 45, -30, 95, 10, -70]):
        x, f = nelder_mead(cost, np.array(x0, float), 10.0, iters=1500)
        x, f = nelder_mead(cost, x, 2.0, iters=800)
        if best is None or f < best[1]:
            best = (x, f)
    x, f = best
    Q, H = pose(x)
    pos = rig.skin(ps.rest, ps.v, Q, H, idx=idx)
    ps.W = world(x)
    loc = ps.local()
    arms = {k: v for k, v in loc.items() if k.split(".")[0] in ARM_BONES}
    flat = float(np.mean(np.abs(pos[:, 0]) < 0.003)) if ref == "palm" else None
    ext = -float(np.dot(swing_vec(qmul(qconj(Q[iA]), Q[iW]), dh), ext_axis))
    return arms, {"x": np.round(x, 1).tolist(), "cost": round(float(f), 5), "palm_within_3mm": None if flat is None else round(flat, 2),
                  "wrist_ext": round(ext, 1), "terms": {k: round(v, 3) for k, v in terms(x).items()}}


def hand_poses(rig, variant, rest, which=None):
    ps = Poser(rig, variant, rest)
    hand = Hand(ps)
    res = {"open": (relaxed_hand(hand), None, {"relaxed": True})}
    for pid, targets in (("gyan", [2]), ("prithvi", [4]), ("shuni", [3]), ("vyana", [2, 3]), ("apana", [3, 4])):
        if which and pid not in which:
            continue
        loc, info = mudra_touch(hand, targets)
        res[pid] = (loc, None, info)
    if which and "anjali" not in which and "hakini" not in which:
        return res
    # anjali: flat hands, fingers together, palms pressed at the chest
    # converging: the MH fingers are thinner than the knuckle spacing (2/0/-2/-3.5 still showed gaps, a fan
    # from the side, council 2026-11-09)
    sp = {2: -3.0, 3: 0, 4: 3.0, 5: 5.5}   # this sign converges (4.5/0/-4/-7.5 fanned them out more)
    loc = anjali_fingers(ps, hand, sp)
    yc = ps.P("spine01")[1] - 0.005
    # 7.5 cm left the wrists 2 cm inside the chest (arm_trunk_pen); 11.5 held the palms 8-10 cm in front of
    # the sternum (council); the solver now keeps the forearms out of the trunk itself (TorsoModel term)
    zc = chest_front(ps, yc) + 0.09
    # forearms dropping 30 deg to the elbows: at 20 deg the neutral and male wrists hit the extension
    # limit and the palms stood 1.5 cm apart in the middle
    # fingers tilted 19 deg forward (12 before): less wrist extension for the same flat palms
    tilt = 0
    for _ in range(3):
        # the thumb tilt moves the heel-of-hand skin too (it went 2-3 mm past the mid plane after the arms
        # were solved with the untilted thumb), so the arms are solved again with the tilted thumb
        arms, tw = arms_anatomy(ps, hand, loc, unit([0, 1, 0.35]), [-1, 0, 0], yc, zc, 0.0015, "palm", slope_deg=30)
        new =anjali_thumb_tilt(ps, hand, sp, arms)
        loc = anjali_fingers(ps, hand, sp, new)
        if new <= tilt:      # the arms were solved with this tilt and the thumbs stay apart
            break
        tilt = new
    loc = anjali_fingers(ps, hand, sp, tilt)
    tw["thumb_tilt"] = tilt
    res["anjali"] = (loc, arms, tw)
    # hakini: spread fingers, tips touching their mirror twins, palms apart
    ps2 = Poser(rig, variant, rest)
    spread = {2: -9, 3: 0, 4: 7, 5: 14}
    off = 0.034
    d_world, n_world = unit([0, 0.8, 0.6]), np.array([-1.0, 0, 0])
    Rh = world_hand_rot(ps2, "L", d_world, n_world)

    def build(x):
        loc = {}
        for i, k in enumerate(range(2, 6)):
            loc.update(hand.finger(k, x[i], 0.55 * x[i], 0.35 * x[i], spread=spread[k]))
        loc.update(hand.thumb(x[4:7], x[7], 0.0))
        return loc

    def cost(x):
        tp = hand.tips(build(x))
        c = 0.0
        for k in range(1, 6):
            c += 4e4 * (np.dot(tp[k] - ps2.P("wrist.L"), hand.n0) - off) ** 2
        c += 4e4 * max(0, 0.045 - np.linalg.norm(tp[1] - tp[2])) ** 2
        c += 1e-4 * np.sum(np.asarray(x) ** 2) * 0.2
        return c
    x, f = nelder_mead(cost, np.array([20, 20, 20, 20, 10, -20, 0, 5.0]), 10.0, iters=3000)
    x, f = nelder_mead(cost, x, 3.0, iters=2000)
    loc = build(x)
    yc = 0.5 * (ps2.P("spine01")[1] + ps2.P("spine02")[1]) + 0.02
    zc = chest_front(ps2, yc) + 0.17
    arms, tw = arms_anatomy(ps2, hand, loc, d_world, n_world, yc, zc, hand.rad[3] - 0.0005, "tips", slope_deg=10)
    res["hakini"] = (loc, arms, {"cost": round(float(f), 5), "x": np.round(x, 1).tolist(), "arms": tw})
    return res


def rnd(q):
    return [round(float(v), 5) for v in q]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="*", default=["neutral", "female", "male"])
    ap.add_argument("--out", default=str(pk.ASSETS / "poses.json"))
    ap.add_argument("--only", choices=["body", "hand"], help="rebuild only this part (the rest is kept from --out)")
    ap.add_argument("--hands", nargs="*", help="rebuild only these hand poses (anjali/hakini are built together)")
    ap.add_argument("--poses", nargs="*", help="rebuild only these body poses (others are kept)")
    ap.add_argument("--reuse-legs", action="store_true",
                    help="seated poses: keep the legs already in --out and solve only the arms (the lotus legs take ~15 min)")
    args = ap.parse_args()
    rig = pk.Rig()
    labels = {
        "stand": "Rest (A-pose)", "tadasana": "Tadasana", "vrikshasana": "Vrikshasana", "sukhasana": "Sukhasana",
        "ardha_padmasana": "Ardha padmasana", "padmasana": "Padmasana", "vajrasana": "Vajrasana", "dandasana": "Dandasana",
        "open": "Open hand", "gyan": "Gyan mudra", "prithvi": "Prithvi mudra", "shuni": "Shuni mudra", "vyana": "Vyana mudra",
        "apana": "Apana mudra", "hakini": "Hakini mudra", "anjali": "Anjali mudra",
    }
    body_ids = ["stand", "tadasana", "vrikshasana", "sukhasana", "ardha_padmasana", "padmasana", "vajrasana", "dandasana"]
    hand_ids = ["open", "gyan", "prithvi", "shuni", "vyana", "apana", "hakini", "anjali"]
    out = {
        "version": 1,
        "rotation": "Local bone rotations relative to the rest pose as unit quaternions [x, y, z, w], expressed in the "
                    "rest-pose world axes (+x body's left, +y up, +z front); Q_bone = Q_parent * q_local, applied about the "
                    "bone head. Missing bones = identity. Values differ per body variant (neutral/female/male).",
        "root": "Translation [x, y, z] in metres added to the root bone (and so to the whole body) per variant; "
                "seated poses lower the pelvis so the body rests on y = 0.",
        "handMirror": "hand.*.rot holds LEFT-hand bones (*.L); apply the mirrored quaternion [x, -y, -z, w] to the "
                      "matching *.R bone. hand.*.arms (if present) overrides arm bones of both sides explicitly.",
        "compose": "local = body.rot[variant]; if hand.arms: local.update(hand.arms[variant]); local.update(fingers of "
                   "hand.rot[variant] for both sides; with the open hand body.openRot[variant] replaces hand.rot when "
                   "present: the lotus dhyana fingers); root = body.root[variant].",
        "body": {pid: {"label": labels[pid], "rot": {}, "root": {}} for pid in body_ids},
        "hand": {pid: {"label": labels[pid], "rot": {}} for pid in hand_ids},
    }
    out["body"]["vrikshasana"]["defaultHand"] = "anjali"
    old = json.loads(Path(args.out).read_text(encoding="utf-8")) if Path(args.out).exists() else None
    if old:  # keep variants / parts that are not rebuilt in this run
        for part in ("body", "hand"):
            for pid, e in old.get(part, {}).items():
                if pid in out[part]:
                    for key in ("rot", "root", "arms", "mudraArms", "openRot"):
                        if key in e:
                            out[part][pid].setdefault(key, {}).update(e[key])
    for variant in args.variants:
        rest = pk.load_glb(pk.GLB[variant])[0][0]
        if args.only != "body":
            hp = hand_poses(rig, variant, rest, args.hands)
            for pid in hand_ids:
                if pid not in hp:
                    continue
                loc, arms, info = hp[pid]
                out["hand"][pid]["rot"][variant] = {k: rnd(v) for k, v in loc.items() if k.split(".")[0] in FINGER_BONES}
                if arms:
                    out["hand"][pid].setdefault("arms", {})[variant] = {k: rnd(v) for k, v in arms.items()}
                print(variant, "hand", pid, info)
        if args.only == "hand":
            continue
        anjali_world = {}
        # anjali arm override as world rotations (spine is identity in every pose)
        Ql = {k: np.array(v) for k, v in out["hand"]["anjali"]["arms"][variant].items()}
        Q, H = rig.fk(variant, Ql)
        for s in SIDES:
            for b in ARM_BONES:
                anjali_world[f"{b}.{s}"] = Q[rig.index[f"{b}.{s}"]]
        import asanas  # noqa: E402  (anatomical-angle poses, see asanas.py)
        ctx = asanas.Ctx(Poser, Capsule, rig, variant, rest)
        fing = lambda pid: {k: np.array(v) for k, v in out["hand"][pid]["rot"].get(variant, {}).items()}  # noqa: E731
        dh_hand = Hand(ctx.ps)
        ctx.fingers = {"open": fing("open"), "mudras": [fing(m) for m in ("gyan", "prithvi", "shuni", "vyana", "apana")],
                       "dhyana": dhyana_fingers(dh_hand), "thigh": thigh_fingers(dh_hand)}
        for pid in body_ids:
            if args.poses and pid not in args.poses:
                continue
            if args.reuse_legs and variant in out["body"][pid].get("rot", {}):
                # world rotations of everything but the arms and hands, from the pose already built
                Q, _H = rig.fk(variant, {k: np.array(v) for k, v in out["body"][pid]["rot"][variant].items()})
                skip = set(ARM_BONES) | HAND_SET
                ctx.legs_cache[pid] = {n: Q[i] for i, n in enumerate(rig.names) if n.split(".")[0] not in skip}
            if pid in ("padmasana", "ardha_padmasana"):
                # the open hand of the lotus is dhyana: its own fingers with the thumb tips touching. No single
                # arm setting suits all three bodies (short arms reach the heels only with the hands apart,
                # then the thumbs cannot meet), so every setting is tried on the same legs and the best kept
                best = None
                for cfg in asanas.LAP_CFGS + asanas.LAP_CFGS_NEAR:
                    if cfg in asanas.LAP_CFGS_NEAR and best[0] < 5.0:
                        break          # the near-belly settings only when the usual ones do not fit
                    asanas.LAP_CFG = cfg
                    Wc, rootc, infoc, mudrac = asanas.body_pose(ctx, pid, anjali_world)
                    floc, finfo = dhyana_thumbs(ctx.ps, dh_hand, Wc, rootc)
                    score, parts = dhyana_score(ctx, Wc, rootc, floc, infoc, finfo)
                    print(variant, pid, "dhyana setting", cfg, "score", round(score, 1), parts, flush=True)
                    if best is None or score < best[0]:
                        best = (score, Wc, rootc, infoc, mudrac, floc, finfo, cfg, parts)
                    if best[0] < 1.0:
                        break
                _, W, root, info, mudra_W, floc, finfo, cfg, parts = best
                ctx.legs_cache.pop(pid, None)
                out["body"][pid].setdefault("openRot", {})[variant] = {k: rnd(v) for k, v in floc.items() if k.split(".")[0] in FINGER_BONES}
                info["dhyana"] = dict(finfo, setting=cfg, score=parts)
            else:
                W, root, info, mudra_W = asanas.body_pose(ctx, pid, anjali_world)
                if pid in asanas.THIGH_POSES:
                    # the open hand of these poses lies on the thigh with its own flatter fingers
                    out["body"][pid].setdefault("openRot", {})[variant] = {
                        k: rnd(v) for k, v in ctx.fingers["thigh"].items() if k.split(".")[0] in FINGER_BONES}
            ctx.ps.W, ctx.ps.root = W, root
            loc = ctx.ps.local()
            out["body"][pid]["rot"][variant] = {k: rnd(v) for k, v in loc.items()}
            out["body"][pid]["root"][variant] = [round(float(v), 5) for v in root]
            if mudra_W:
                out["body"][pid].setdefault("mudraArms", {})[variant] = {k: rnd(v) for k, v in asanas.arm_locals(ctx, mudra_W).items()}
            else:
                out["body"][pid].pop("mudraArms", None)
            print(variant, "body", pid, "root", np.round(root, 4).tolist(), info)
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("wrote", args.out, Path(args.out).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
