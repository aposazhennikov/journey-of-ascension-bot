"""Asanas authored as anatomical joint angles (see anatomy.py) plus a small contact solver.

Each seated pose: leg angles are optimised inside anatomical ranges so that the contacts the yoga
teacher asked for hold (feet under the opposite knees in sukhasana, heels in the groin and knees on
the floor in padmasana, buttocks on the floor, shins not passing through each other); then the
arms are solved so the hands rest where they should (palms down on the thighs by default, the back
of the wrist on the knee with the palm up for mudras, dhyana in the lap for the lotus).
Angle targets come from the council (scratchpad audit/council/yoga.md, round 2).
"""
import numpy as np

import posekit as pk
from anatomy import ID, SIDES, X, Y, Z, Anatomy
from posekit import qaxis, qmul, qrot, unit

FOOT_BONES = ("foot",)


def nelder_mead(f, x0, step, iters=600, tol=1e-9):
    n = len(x0)
    pts = [np.array(x0, float)]
    step = np.broadcast_to(np.asarray(step, float), (n,))
    for i in range(n):
        p = np.array(x0, float)
        p[i] += step[i]
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


def bound(v, lo, hi, w=1.0):
    """Quadratic penalty outside [lo, hi] (degrees or metres)."""
    return w * (max(0.0, lo - v) ** 2 + max(0.0, v - hi) ** 2)


class Ctx:
    """One body variant: poser, anatomy, vertex sets, capsules."""

    def __init__(self, Poser, Capsule, rig, variant, rest):
        self.ps = ps = Poser(rig, variant, rest)
        self.an = Anatomy(ps)
        self.rig = rig
        dom = ps.dom.astype(str)
        base = np.array([n.split(".")[0] for n in dom])
        side = np.array([n.split(".")[1] if "." in n else "" for n in dom])
        self.set = {}
        for s in SIDES:
            self.set[f"thigh.{s}"] = np.isin(base, ["upperleg01", "upperleg02"]) & (side == s)
            self.set[f"shin.{s}"] = np.isin(base, ["lowerleg01", "lowerleg02"]) & (side == s)
            self.set[f"foot.{s}"] = (base == "foot") | np.char.startswith(base, "toe")
            self.set[f"foot.{s}"] &= side == s
            self.set[f"hand.{s}"] = ps.hand_mask & (side == s)
            self.set[f"palm.{s}"] = np.isin(base, ["wrist", "metacarpal1", "metacarpal2", "metacarpal3", "metacarpal4"]) & (side == s)
            self.set[f"arm.{s}"] = np.isin(base, ["upperarm01", "upperarm02", "lowerarm01", "lowerarm02"]) & (side == s)
            self.set[f"fore.{s}"] = np.isin(base, ["lowerarm01", "lowerarm02"]) & (side == s)
            self.set[f"nothumb.{s}"] = ps.hand_mask & (side == s) & ~np.isin(base, ["finger1-1", "finger1-2", "finger1-3", "metacarpal1"])
        hip = ps.P("upperleg01.L")
        r = ps.rest
        self.set["butt"] = (r[:, 2] < hip[2] + 0.02) & (np.abs(r[:, 0]) < 0.16) & (r[:, 1] > hip[1] - 0.20) & (r[:, 1] < hip[1] + 0.05) & ~ps.hand_mask
        self.set["body"] = ~ps.hand_mask
        limb = np.array([b.startswith(("upperleg", "lowerleg", "foot", "toe", "upperarm", "lowerarm", "wrist", "finger",
                                       "metacarpal", "neck", "head", "jaw", "eye", "tongue", "clavicle", "shoulder",
                                       "breast")) for b in base])
        self.set["trunk"] = ~limb & ~ps.hand_mask
        self.cap = {}
        for s in SIDES:
            self.cap[f"shin.{s}"] = Capsule(ps, [f"lowerleg01.{s}", f"lowerleg02.{s}"], f"lowerleg01.{s}", f"foot.{s}")
            self.cap[f"thigh.{s}"] = Capsule(ps, [f"upperleg01.{s}", f"upperleg02.{s}"], f"upperleg01.{s}", f"lowerleg01.{s}")
        legs = np.zeros(len(r), bool)
        for s in SIDES:
            for k in ("thigh", "shin", "foot"):
                legs |= self.set[f"{k}.{s}"]
        self.idx_legs = np.flatnonzero(legs | self.set["butt"])
        self.sub = {k: v[self.idx_legs] for k, v in self.set.items()}
        hands = np.zeros(len(r), bool)
        for s in SIDES:
            hands |= self.set[f"hand.{s}"] | self.set[f"arm.{s}"]
        self.idx_hands = np.flatnonzero(hands)
        self.subh = {k: v[self.idx_hands] for k, v in self.set.items()}
        self.fingers = {}       # {'open': left finger locals, 'mudras': [..]} set by build_poses
        self.legs_cache = {}    # pid -> world rotations of the legs/trunk to reuse (build_poses --reuse-legs)

    def skin_idx(self, idx):
        Q, H = self.ps.fk()
        return self.rig.skin(self.ps.rest, self.ps.v, Q, H, idx=idx), Q, H

    def H(self, name, H):
        return H[self.rig.index[name]]


# ---------------------------------------------------------------- legs
LEG_TABLE = {
    # (flex, abd, ext rot), knee, (dorsi, inv); ranges for the optimiser
    "sukhasana": dict(hip=(85, 38, 50), knee=138, ankle=(-15, 15), rng=((70, 108), (25, 50), (30, 67), (120, 152))),
    "padmasana": dict(hip=(90, 42, 60), knee=155, ankle=(-25, 30), rng=((80, 105), (35, 50), (45, 72), (148, 158)), tilt=12),
    "vajrasana": dict(hip=(95, 7, 2), knee=155, ankle=(-48, 0), rng=((72, 118), (3, 10), (0, 6), (148, 162))),
    # legs together (slight adduction), knees straight, slightly more hip flexion so the backs of the
    # knees reach the floor, feet pulled up toward vertical
    "dandasana": dict(hip=(91, -4.5, 2), knee=0, ankle=(20, 0), rng=((88, 95), (-8, 2), (0, 6), (0, 3))),
}


def legs_world(ctx, pid, L, R, tilt=0.0, ankleL=None, ankleR=None, tibL=0.0, tibR=0.0):
    """L/R = (flex, abd, rot, knee). Returns W dict incl. pelvis tilt and an upright spine."""
    tab = LEG_TABLE[pid]
    Qp = qaxis(X, tilt) if tilt else ID
    W = {}
    if tilt:
        W["root"] = Qp
        W["spine05"] = ID
    W.update(ctx.an.leg("L", hip=L[:3], knee=L[3], ankle=ankleL or tab["ankle"], tibia=tibL, Qp=Qp))
    W.update(ctx.an.leg("R", hip=R[:3], knee=R[3], ankle=ankleR or tab["ankle"], tibia=tibR, Qp=Qp))
    return W


def foot_hidden(pos, foot, others, step=3):
    """Fraction of foot vertices covered from above by other skin (within 1 cm sideways, 2 mm up)."""
    f = pos[foot][::step]
    o = pos[others][::2]
    near = ((f[:, None, 0] - o[None, :, 0]) ** 2 + (f[:, None, 2] - o[None, :, 2]) ** 2) < 0.01 ** 2
    above = near & (o[None, :, 1] > f[:, None, 1] + 0.002)
    return float(above.any(axis=1).mean())


def seated_eval(ctx, W):
    """Pose the legs, drop the body so the buttocks touch y = 0; returns (pos_sub, H, shift)."""
    ps = ctx.ps
    ps.W = W
    ps.root = np.zeros(3)
    pos, Q, H = ctx.skin_idx(ctx.idx_legs)
    shift = -pos[ctx.sub["butt"]][:, 1].min()
    pos = pos + [0, shift, 0]
    H = H + [0, shift, 0]
    return pos, H, shift


def overlap(ctx, pos, H, a, cap):
    d = ctx.cap[cap].depth(H, pos[ctx.sub[a]])
    return float(np.max(d)) if np.isfinite(d).any() else -1.0


def solve_sukhasana(ctx):
    tab = LEG_TABLE["sukhasana"]
    rng = tab["rng"]
    k = np.linalg.norm(ctx.ps.P("lowerleg01.L") - ctx.ps.P("upperleg01.L")) / 0.42
    x0 = np.array([*tab["hip"], tab["knee"]] * 2, float)

    def unpack(x):
        return x[:4], x[4:]

    def cost(x):
        L, R = unpack(x)
        pos, H, _ = seated_eval(ctx, legs_world(ctx, "sukhasana", L, R))
        hz = ctx.H("upperleg01.L", H)[2]
        c = 0.0
        # left foot under the right shin near the knee (behind), right foot under the left shin (in front)
        aL, aR = ctx.H("foot.L", H), ctx.H("foot.R", H)
        # ankles ~5.5 cm up: the feet lie on their outer edge
        c += 2e3 * ((aL[0] + 0.13 * k) ** 2 + (aL[2] - (hz + 0.18 * k)) ** 2 + (aL[1] - 0.055) ** 2)
        c += 2e3 * ((aR[0] - 0.13 * k) ** 2 + (aR[2] - (hz + 0.29 * k)) ** 2 + (aR[1] - 0.055) ** 2)
        c += 2e3 * (max(0.0, ctx.H("lowerleg01.L", H)[1] - 0.16) ** 2 + max(0.0, ctx.H("lowerleg01.R", H)[1] - 0.16) ** 2)
        legs_low = min(pos[ctx.sub["shin.L"] | ctx.sub["shin.R"] | ctx.sub["foot.L"] | ctx.sub["foot.R"]][:, 1])
        c += 2e5 * min(0.0, legs_low + 0.002) ** 2           # nothing under the floor
        c += 2e3 * max(0.0, legs_low - 0.01) ** 2            # feet/shins rest on the floor
        c += 3e4 * max(0.0, overlap(ctx, pos, H, "shin.L", "shin.R") - 0.008) ** 2
        c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.L", "shin.R") - 0.010) ** 2
        c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.R", "shin.L") - 0.010) ** 2
        for (lo, hi), v in zip(rng * 2, x):
            c += bound(v, lo, hi, 1.0)
        c += 1e-3 * float(np.sum((x - x0) ** 2))
        return c
    x, f = nelder_mead(cost, x0, 4.0, iters=700)
    x, f = nelder_mead(cost, x, 1.5, iters=400)
    L, R = unpack(x)
    return legs_world(ctx, "sukhasana", L, R), {"cost": round(float(f), 4), "L": np.round(L, 1).tolist(), "R": np.round(R, 1).tolist()}


def solve_lotus(ctx, half=False):
    """padmasana (half=False) or ardha padmasana: left foot on the right groin on top; the right foot
    on the left groin underneath (lotus) or under the left knee (half lotus)."""
    tab = LEG_TABLE["padmasana"]
    rng = tab["rng"]
    tilt = tab["tilt"]
    suk = LEG_TABLE["sukhasana"]
    k = np.linalg.norm(ctx.ps.P("lowerleg01.L") - ctx.ps.P("upperleg01.L")) / 0.42
    if half:
        # the top (left) foot turns like in the full lotus (inversion, tibia rotation): without it the
        # foot sank into the right thigh, 85 % of it covered from above on the neutral and female bodies
        x0 = np.array([*tab["hip"], tab["knee"], *suk["hip"], suk["knee"], 30, 8], float)
        lot = list(rng)
        # external rotation kept under the check's 80 deg (85 here gave 84); the full lotus below still
        # uses 85 until its legs are rebuilt
        lot[0], lot[2] = (80, 112), (45, 79)
        rngs = lot + list(suk["rng"]) + [(15, 50), (-15, 25)]
    else:
        # full lotus also turns the shins and supinates the feet (inversion, tibia rotation): without it
        # the feet stayed buried in the opposite thighs, 95 % of the foot covered from above
        x0 = np.array([*tab["hip"], tab["knee"]] * 2 + [30, 8, 30, 8], float)
        x0[0] += 5                                   # the top leg flexes a little more
        lot = list(rng)
        lot[0], lot[2] = (80, 112), (45, 85)
        rngs = lot * 2 + [(15, 50), (-15, 25)] * 2
    others = {s: ~ctx.sub[f"foot.{s}"] for s in SIDES}

    def world(x):
        L, R = x[:4], x[4:8]
        dorsi = tab["ankle"][0]
        if half:
            W = legs_world(ctx, "padmasana", L, L, tilt=tilt, ankleL=(dorsi, x[8]), tibL=x[9])
            W.update(ctx.an.leg("R", hip=R[:3], knee=R[3], ankle=suk["ankle"], Qp=W["root"]))
            return W
        return legs_world(ctx, "padmasana", L, R, tilt=tilt, ankleL=(dorsi, x[8]), ankleR=(dorsi, x[10]), tibL=x[9], tibR=x[11])

    def cost(x):
        pos, H, _ = seated_eval(ctx, world(x))
        hipL, hipR = ctx.H("upperleg01.L", H), ctx.H("upperleg01.R", H)
        aL, aR = ctx.H("foot.L", H), ctx.H("foot.R", H)
        kL, kR = ctx.H("lowerleg01.L", H), ctx.H("lowerleg01.R", H)
        c = 0.0
        # heel in the opposite groin: ankle a little in front of and above the opposite hip joint
        c += 1.5e3 * float(np.sum((aL - (hipR + np.array([0.015, 0.075, 0.11]) * [1, 1, k])) ** 2))
        knee_top = 0.068
        c += 3e3 * max(0.0, kL[1] - knee_top) ** 2
        if half:
            c += 2e3 * ((aR[0] - 0.12 * k) ** 2 + (aR[2] - (hipR[2] + 0.30 * k)) ** 2)
            c += 3e3 * max(0.0, kR[1] - 0.085) ** 2
        else:
            c += 1.5e3 * float(np.sum((aR - (hipL + np.array([-0.015, 0.045, 0.10]) * [1, 1, k])) ** 2))
            c += 3e3 * max(0.0, kR[1] - knee_top) ** 2
            c += 3e3 * max(0.0, abs(kL[1] - kR[1]) - 0.012) ** 2
            c += 3e3 * max(0.0, abs(kL[0] + kR[0]) - 0.02) ** 2
        low = min(pos[ctx.sub["shin.L"] | ctx.sub["shin.R"] | ctx.sub["foot.L"] | ctx.sub["foot.R"] | ctx.sub["thigh.L"] | ctx.sub["thigh.R"]][:, 1])
        # half lotus 10x: with the top foot's visibility term the solver let the lower foot go 1.5 cm under
        # the floor, and grounding then lifted the whole body (buttocks 12-19 mm in the air)
        c += (2e6 if half else 2e5) * min(0.0, low + 0.002) ** 2
        c += 3e4 * max(0.0, overlap(ctx, pos, H, "shin.L", "shin.R") - 0.010) ** 2
        c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.L", "thigh.R") - 0.012) ** 2
        # the top foot stays ON the thigh (half lotus 30x: made visible, it floated 4.8 cm above it)
        c += (3e4 if half else 1e3) * max(0.0, -0.012 - overlap(ctx, pos, H, "foot.L", "thigh.R")) ** 2
        if not half:
            c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.R", "thigh.L") - 0.012) ** 2
            # both feet lie ON the thighs: seen from above, not covered by the legs
            for s in SIDES:
                c += 300 * foot_hidden(pos, ctx.sub[f"foot.{s}"], others[s]) ** 2
        else:
            c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.R", "thigh.L") - 0.010) ** 2
            c += 3e4 * max(0.0, overlap(ctx, pos, H, "foot.R", "shin.L") - 0.010) ** 2
            c += 300 * foot_hidden(pos, ctx.sub["foot.L"], others["L"]) ** 2
        for (lo, hi), v in zip(rngs, x):
            c += bound(v, lo, hi, 20.0)
        c += 1e-3 * float(np.sum((x - x0) ** 2))
        return c
    best = None
    for dx in (0.0, 6.0):
        s = x0.copy()
        s[2] += dx
        x, f = nelder_mead(cost, s, 4.0, iters=700)
        x, f = nelder_mead(cost, x, 1.5, iters=400)
        if best is None or f < best[1]:
            best = (x, f)
    x, f = best
    info = {"cost": round(float(f), 4), "L": np.round(x[:4], 1).tolist(), "R": np.round(x[4:8], 1).tolist(), "tilt": tilt}
    pos, H, _ = seated_eval(ctx, world(x))
    info["feet"] = np.round(x[8:], 1).tolist()
    info["foot_hidden"] = {s: round(foot_hidden(pos, ctx.sub[f"foot.{s}"], others[s]), 2) for s in (["L"] if half else SIDES)}
    return world(x), info


def solve_vajrasana(ctx):
    tab = LEG_TABLE["vajrasana"]
    x0 = np.array([tab["hip"][0], tab["knee"]], float)

    def world(x):
        L = (x[0], tab["hip"][1], tab["hip"][2], x[1])
        return legs_world(ctx, "vajrasana", L, L)

    def cost(x):
        ps = ctx.ps
        ps.W = world(x)
        ps.root = np.zeros(3)
        pos, Q, H = ctx.skin_idx(ctx.idx_legs)
        low = pos[ctx.sub["shin.L"] | ctx.sub["shin.R"]][:, 1].min()
        pos = pos - [0, low, 0]
        H = H - [0, low, 0]
        sd = unit(ctx.H("foot.L", H) - ctx.H("lowerleg01.L", H))
        c = 400 * sd[1] ** 2                         # shins lie flat on the floor
        heel_top = pos[ctx.sub["foot.L"]][:, 1].max()
        butt = pos[ctx.sub["butt"]][:, 1].min()
        c += 3e3 * (butt - heel_top + 0.005) ** 2     # sitting on the heels
        c += bound(x[0], *tab["rng"][0]) + bound(x[1], *tab["rng"][3])
        c += 1e-3 * float(np.sum((x - x0) ** 2))
        return c
    x, f = nelder_mead(cost, x0, 3.0, iters=300)
    return world(x), {"cost": round(float(f), 4), "flex": round(float(x[0]), 1), "knee": round(float(x[1]), 1)}


def solve_dandasana(ctx):
    tab = LEG_TABLE["dandasana"]
    L = (*tab["hip"], tab["knee"])
    return legs_world(ctx, "dandasana", L, L), {"hip": L}


# ---------------------------------------------------------------- arms
ARM_DEFAULT = {
    # palms down on the thighs: shoulder (flex, abd, rot), elbow, sup, wrist (flex, dev)
    "thigh": dict(sh=(20, 12, 0), elbow=60, sup=-80, wrist=(-10, 0), rng=((0, 40), (5, 30), (-40, 25), (25, 95))),
    # palm up: a little wrist flexion lifts the straight free fingers off the knee
    "knee_up": dict(sh=(22, 14, 0), elbow=55, sup=85, wrist=(18, 0), rng=((0, 45), (5, 30), (-45, 25), (25, 95))),
    # dandasana: these arms are too short for a flat palm beside the hips (hip joint ~16 cm up), so the
    # hand stands on its fingertips beside the hip, as the teacher allows
    "floor": dict(sh=(-4, 10, 0), elbow=4, sup=-60, wrist=(-25, 0), rng=((-25, 15), (3, 30), (-30, 25), (0, 25))),
    # dhyana: the forearm turn and the wrist are free too (x = sh3, elbow, sup, wrist flex, radial dev),
    # so the fingers can point to the other side while the palm faces up
    # ranges kept inside check_poses limits (humeral rot >= -70, pron_sup <= 90, |wrist dev| <= 25): a
    # first try let the wrists bend 40 deg to make the fingers point straight across
    # elbow down to 40: at 60 the neutral and female arms could not reach the heels with the hands close
    "lap": dict(sh=(12, 14, -25), elbow=95, sup=85, wrist=(0, 0), rng=((-10, 45), (5, 35), (-66, 20), (40, 135)),
                xrng=((55, 85), (-30, 35), (-17, 17)), bound_w=8.0),
    "side": dict(sh=(0, 6, 0), elbow=8, sup=0, wrist=(0, 0), rng=None),
}


def arms_eval(ctx, Wlegs, root, s, x, mode):
    tab = ARM_DEFAULT[mode]
    sh = tuple(x[:3])
    el = x[3]
    sup = x[4] if len(x) > 4 else tab["sup"]
    wrist = (x[5], x[6]) if len(x) > 6 else tab["wrist"]
    W = dict(Wlegs)
    W.update(ctx.an.arm(s, shoulder=sh, elbow=el, sup=sup, wrist=wrist, Qp=W.get("spine01", ID)))
    return W


def solve_arm(ctx, Wlegs, root, s, mode, target_fn):
    """Optimise (shoulder flex, abd, rot, elbow[, sup, wrist flex, dev]) so target_fn(ctx, pos, H, Q, s) is low."""
    tab = ARM_DEFAULT[mode]
    free = "xrng" in tab
    x0 = np.array([*tab["sh"], tab["elbow"]] + ([tab["sup"], *tab["wrist"]] if free else []), float)
    rngs = list(tab["rng"]) + (list(tab["xrng"]) if free else [])
    ps = ctx.ps

    def cost(x):
        ps.W = arms_eval(ctx, Wlegs, root, s, x, mode)
        ps.root = root
        pos, Q, H = ctx.skin_idx(ctx.idx_hands)
        c = target_fn(ctx, pos, H, Q, s)
        for (lo, hi), v in zip(rngs, x):
            c += bound(v, lo, hi, tab.get("bound_w", 0.5))
        c += 2e-4 * float(np.sum((x - x0) ** 2))
        return c
    x, f = nelder_mead(cost, x0, 6.0, iters=700 if free else 500)
    x, f = nelder_mead(cost, x, 2.0, iters=400 if free else 300)
    W = arms_eval(ctx, Wlegs, root, s, x, mode)
    return {k: v for k, v in W.items() if k.endswith(f".{s}") and k.split(".")[0] in ("upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist")}, {"x": np.round(x, 1).tolist(), "cost": round(float(f), 5)}


def thigh_surface(ctx, H, legs_pos, s, t, up=True):
    """Top (up) point of the posed thigh at fraction t from hip to knee (legs_pos in idx_legs order)."""
    hip, knee = ctx.H(f"upperleg01.{s}", H), ctx.H(f"lowerleg01.{s}", H)
    pts = legs_pos[ctx.sub[f"thigh.{s}"] | ctx.sub[f"shin.{s}"]]
    ax = knee - hip
    tt = (pts - hip) @ ax / (ax @ ax)
    near = pts[np.abs(tt - t) < 0.06]
    return near[np.argmax(near[:, 1])] if len(near) else hip + ax * t


def make_palm_on(point, ctx_legs, normal_down=True):
    """Palm centre on `point` (palm resting on top, palm facing down) without sinking into the leg."""
    def fn(ctx, pos, H, Q, s):
        palm = pos[ctx.subh[f"palm.{s}"]]
        centre = palm.mean(axis=0)
        n = qrot(Q[ctx.rig.index[f"wrist.{s}"]], ctx.ps.hand_frame0(s)[1])
        c = 3e3 * float(np.sum((centre - (point + np.array([0, 0.012, 0]))) ** 2))
        c += 20 * (n[1] + 1.0) ** 2 if normal_down else 20 * (n[1] - 1.0) ** 2
        hand = pos[ctx.subh[f"hand.{s}"]]
        for cap in ("thigh.L", "thigh.R", "shin.L", "shin.R"):
            d = ctx.cap[cap].depth(H, hand)
            if np.isfinite(d).any():
                c += 3e4 * max(0.0, float(np.max(d)) - 0.004) ** 2
        c += 1e4 * min(0.0, hand[:, 1].min() + 0.002) ** 2
        return c
    return fn


def make_wrist_on(point):
    """Back of the wrist resting on `point`, palm up."""
    def fn(ctx, pos, H, Q, s):
        wr = H[ctx.rig.index[f"wrist.{s}"]]
        n = qrot(Q[ctx.rig.index[f"wrist.{s}"]], ctx.ps.hand_frame0(s)[1])
        back = wr - n * 0.018
        c = 3e3 * float(np.sum((back - (point + np.array([0, 0.004, 0]))) ** 2))
        c += 20 * (n[1] - 1.0) ** 2
        hand = pos[ctx.subh[f"hand.{s}"]]
        for cap in ("thigh.L", "thigh.R", "shin.L", "shin.R"):
            d = ctx.cap[cap].depth(H, hand)
            if np.isfinite(d).any():
                c += 3e4 * max(0.0, float(np.max(d)) - 0.004) ** 2
        return c
    return fn


def make_palm_floor(point):
    def fn(ctx, pos, H, Q, s):
        palm = pos[ctx.subh[f"palm.{s}"]]
        centre = palm.mean(axis=0)
        n = qrot(Q[ctx.rig.index[f"wrist.{s}"]], ctx.ps.hand_frame0(s)[1])
        c = 3e3 * float(np.sum((centre[[0, 2]] - point[[0, 2]]) ** 2))
        hand = pos[ctx.subh[f"hand.{s}"]]
        # fingertips on the floor beside the hip, the hand standing on them (never through the floor)
        c += 3e4 * (hand[:, 1].min() - 0.002) ** 2
        c += 1e6 * min(0.0, hand[:, 1].min()) ** 2
        return c
    return fn


def contact(ctx, s, fingers=None, on_hand=False):
    """Signed distance (m) from the hand to the legs as check_poses measures it: <0 sinking, >0 gap.
    fingers: list of left-hand finger pose dicts that will be shown with this arm (worst case wins).
    on_hand: the other hand counts as support too (dhyana: the right hand rests on the left one)."""
    from check_poses import Body, surface_sd, vertex_normals
    if not hasattr(ctx, "cb"):
        ctx.cb = Body(ctx.rig, ctx.ps.v)
    cb = ctx.cb
    # the whole other hand (leaving its thumb out made the nearest support vertices the back of that hand
    # and the right hand read as 4 cm inside it)
    legs = np.concatenate([cb.sets["legL"], cb.sets["legR"]] + ([cb.sets[f"hand{'R' if s == 'L' else 'L'}"]] if on_hand else []))
    ps = ctx.ps
    worst = None
    for f in (fingers or [{}]):
        loc = ps.local()
        loc.update(f)
        loc.update({k.replace(".L", ".R"): pk.qmirror(np.asarray(q, float)) for k, q in f.items()})
        Q, H = ctx.rig.fk(ps.v, loc, ps.root)
        pos = ctx.rig.skin(ps.rest, ps.v, Q, H)
        nrm = vertex_normals(pos, cb.tris)
        d = float(surface_sd(cb, pos, nrm, cb.sets[f"hand{s}"], legs).min())
        worst = d if worst is None else min(worst, d)
    return worst


def settle_arm(ctx, W, root, s, mode, make_fn, tgt, lo=-0.004, hi=0.006, rounds=6, fingers=None, on_hand=False):
    """Solve the arm for target `tgt`, then move the target up/down until the hand rests on the legs
    (sinking <= 4 mm, gap <= 6 mm, measured on the skin like check_poses, with the shown fingers)."""
    tgt = np.array(tgt, float)
    best = None
    for _ in range(rounds):
        Wa, ai = solve_arm(ctx, W, root, s, mode, make_fn(tgt))
        Wt = dict(W)
        Wt.update(Wa)
        ctx.ps.W, ctx.ps.root = Wt, root
        d = contact(ctx, s, fingers, on_hand)
        ai["contact_mm"] = round(d * 1000, 1)
        miss = max(lo - d, d - hi, 0.0)
        if best is None or miss < best[0]:
            best = (miss, Wa, ai)
        if miss == 0.0:
            break
        # at most 1 cm per round: an unreachable target was pushed 4 cm further each round and the
        # last (worst) round was kept, with the hand 4 cm above the lap
        step = (0.002 - d) if d < lo else -(d - 0.002)
        tgt = tgt + np.array([0, float(np.clip(step, -0.01, 0.01)), 0])
    return best[1], best[2]


def ground(ctx):
    """Lift the body so its lowest non-hand vertex touches y = 0."""
    ps = ctx.ps
    pos = ps.skin()
    ps.root = ps.root + [0, -pos[ctx.set["body"]][:, 1].min(), 0]
    return ps.skin()


ARM_BONES = ("upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist")


def arm_locals(ctx, W):
    ctx.ps.W = W
    loc = ctx.ps.local()
    return {k: v for k, v in loc.items() if k.split(".")[0] in ARM_BONES}


def body_pose(ctx, pid, anjali_world):
    """Returns (W, root, info, mudra_W or None)."""
    ps = ctx.ps
    an = ctx.an
    info = {}
    if pid == "stand":
        ps.W, ps.root = {}, np.zeros(3)
        return {}, np.zeros(3), info, None
    if pid == "tadasana":
        W = {}
        for s in SIDES:
            W.update(an.leg(s, hip=(0, 1, 6), knee=0, ankle=(0, 0)))
            W.update(an.arm(s, shoulder=(0, 6, 0), elbow=8, sup=0, wrist=(0, 0)))
        ps.W, ps.root = W, np.zeros(3)
        ground(ctx)
        return W, ps.root.copy(), info, None
    if pid == "vrikshasana":
        return vrikshasana(ctx, anjali_world)
    # ---- seated
    if pid in ctx.legs_cache:
        Wl, info = dict(ctx.legs_cache[pid]), {"legs": "reused"}
    elif pid == "sukhasana":
        Wl, info = solve_sukhasana(ctx)
    elif pid == "padmasana":
        Wl, info = solve_lotus(ctx, half=False)
    elif pid == "ardha_padmasana":
        Wl, info = solve_lotus(ctx, half=True)
    elif pid == "vajrasana":
        Wl, info = solve_vajrasana(ctx)
    elif pid == "dandasana":
        Wl, info = solve_dandasana(ctx)
    else:
        raise ValueError(pid)
    ctx.legs_cache[pid] = dict(Wl)        # build_poses re-runs the arms with other settings on these legs
    if pid == "vajrasana":
        ps.W, ps.root = Wl, np.zeros(3)
        pos = ps.skin()
        ps.root = np.array([0, -pos[ctx.set["body"]][:, 1].min(), 0])
    else:
        pos, H, shift = seated_eval(ctx, Wl)
        ps.root = np.array([0, shift, 0])
    root = ps.root.copy()
    ps.W = Wl
    legs_pos, Q, H = ctx.skin_idx(ctx.idx_legs)
    W = dict(Wl)
    arm_info = {}
    hipL, hipR = ctx.H("upperleg01.L", H), ctx.H("upperleg01.R", H)
    for s, sg in SIDES.items():
        if pid in ("padmasana", "ardha_padmasana"):
            # dhyana: palms up over the heels, the fingers of each hand pointing to the other side, the
            # right hand lying on the left one; forearms clear of the belly and the waist
            fl = ctx.fingers.get("dhyana") or ctx.fingers.get("open", {})
            if s == "L":
                ps.W, ps.root = dict(W), root
                torso = TorsoModel(ps.skin(), ctx.set["trunk"])
                # the solver sees the dhyana fingers (it used the rest fingers, and the curled ring and
                # little fingers of the right hand then went 1-1.6 cm into the left hand)
                ps.hold = dict(fl)
                ps.hold.update({k.replace(".L", ".R"): pk.qmirror(np.asarray(q, float)) for k, q in fl.items()})
            heels = 0.5 * (ctx.H("foot.L", H) + ctx.H("foot.R", H))
            # palms stacked over the heels, the right one on the left one: the palm centres only
            # LAP_DX apart, so the thumb bases come close enough for the thumb tips to meet (with the
            # centres 7 cm apart the wrists ended 20 cm apart and the thumbs 2-4 cm short)
            tgt = np.array([LAP_DX * sg, heels[1] + 0.035 + (0.014 if s == "R" else 0.0), heels[2] + 0.045])
            # fingers across, or ~30 deg forward (a shallow V, dz 0.55): straight across needs more inner
            # shoulder rotation than the limit on short arms, and the lower hand hung 2-4 cm above the heels
            d_t = unit(np.array([-sg, 0.0, LAP_CFG["dz"]]))
            Wa, ai = settle_arm(ctx, W, root, s, "lap", lambda p, d_t=d_t, s=s: make_lap(p, d_t, torso, s == "R"), tgt,
                                lo=-0.002 if s == "R" else -0.004, hi=0.008, fingers=[fl], on_hand=s == "R")
        elif pid == "dandasana":
            hip = hipL if s == "L" else hipR
            tgt = hip + np.array([sg * 0.13, 0, 0.04])
            Wa, ai = solve_arm(ctx, W, root, s, "floor", make_palm_floor(tgt))
        else:
            t = 0.72 if pid == "sukhasana" else 0.65    # 5-15 cm closer to the body than the kneecap
            tgt = thigh_surface(ctx, H, legs_pos, s, t)
            Wa, ai = settle_arm(ctx, W, root, s, "thigh", lambda p: make_palm_on(p, None), tgt, fingers=[ctx.fingers.get("open", {})])
        W.update(Wa)
        arm_info[s] = ai
    ps.hold = {}
    info["arms"] = arm_info
    # mudra arms: palm up, back of the wrist on the knee (all seated poses except dandasana)
    mudra_W = None
    if pid != "dandasana":
        Wm = dict(W)
        for s in SIDES:
            t = 0.78 if pid != "vajrasana" else 0.70
            tgt = thigh_surface(ctx, H, legs_pos, s, t)
            Wa, ai = settle_arm(ctx, Wm, root, s, "knee_up", make_wrist_on, tgt, fingers=ctx.fingers.get("mudras") or [{}])
            Wm.update(Wa)
            info[f"mudra_{s}"] = ai
        mudra_W = Wm
    ps.W, ps.root = W, root
    pos = ps.skin()
    low = pos[ctx.set["body"]][:, 1].min()
    if low < 0:
        root = root + [0, -low, 0]
        ps.root = root
    info["buttock_y"] = round(float(ps.skin()[ctx.set["butt"]][:, 1].min()), 4)
    return W, root, info, mudra_W


def vrikshasana(ctx, anjali_world):
    """Tree pose; the sole is moved off the standing thigh until it rests on its skin (<= 6 mm in)."""
    from check_poses import Body, surface_sd, vertex_normals
    if not hasattr(ctx, "cb"):
        ctx.cb = Body(ctx.rig, ctx.ps.v)
    dx = 0.0
    for _ in range(4):
        W, root, info, _m = vrikshasana_once(ctx, anjali_world, dx)
        pos = ctx.ps.skin()
        nrm = vertex_normals(pos, ctx.cb.tris)
        sd = float(surface_sd(ctx.cb, pos, nrm, ctx.cb.sets["footL"], ctx.cb.sets["thighR"]).min())
        info["foot_sd_mm"] = round(sd * 1000, 1)
        if sd >= -0.006:
            break
        dx += -sd - 0.003
    return W, root, info, None


def vrikshasana_once(ctx, anjali_world, dx=0.0):
    ps, an = ctx.ps, ctx.an
    W0 = dict(anjali_world)
    W0.update(an.leg("R", hip=(0, 1, 4), knee=0, ankle=(0, 0)))
    # grid search: flex ~35, abd ~40, ER ~75-80, knee ~158 puts the ankle at ~0.3 of the thigh below the
    # hip, on the inner side of the standing thigh
    x0 = np.array([33, 42, 76, 156], float)
    rng = ((15, 40), (35, 63), (40, 88), (140, 160))

    def world(x):
        W = dict(W0)
        W.update(an.leg("L", hip=tuple(x[:3]), knee=x[3], ankle=(-15, 20)))
        return W

    def cost(x):
        ps.W, ps.root = world(x), np.zeros(3)
        pos, Q, H = ctx.skin_idx(ctx.idx_legs)
        hipR, kneeR = ctx.H("upperleg01.R", H), ctx.H("lowerleg01.R", H)
        foot = pos[ctx.sub["foot.L"]]
        # heel (ankle) high on the inner right thigh: ~0.28 of the thigh below the hip, at its inner side
        ank = ctx.H("foot.L", H)
        tgt = hipR + (kneeR - hipR) * 0.28 + np.array([0.095 + dx, 0, 0.03])   # sole against, not into, the thigh
        c = 2e3 * float(np.sum((ank - tgt) ** 2))
        rel_h = (foot[:, 1].mean() - kneeR[1]) / max(1e-6, hipR[1] - kneeR[1])   # as check_poses measures
        c += 300 * max(0.0, 0.60 - rel_h) ** 2
        d = ctx.cap["thigh.R"].depth(H, foot)
        if np.isfinite(d).any():
            dm = float(np.max(d))
            c += 3e5 * max(0.0, dm - 0.006) ** 2 + 2e3 * max(0.0, -0.004 - dm) ** 2
        for (lo, hi), v in zip(rng, x):
            c += bound(v, lo, hi, 5.0)
        c += 1e-3 * float(np.sum((x - x0) ** 2))
        return c
    best = None
    for s0 in (x0, x0 + [-8, 5, 4, 0], x0 + [4, 8, -10, -4]):
        x, f = nelder_mead(cost, s0, 5.0, iters=600)
        if best is None or f < best[1]:
            best = (x, f)
    x, f = best
    W = world(x)
    ps.W, ps.root = W, np.array([-0.045, 0, 0])
    ground(ctx)
    return W, ps.root.copy(), {"cost": round(float(f), 4), "L": np.round(x, 1).tolist()}, None


class TorsoModel:
    """Posed trunk as elliptic cross-sections every 1.5 cm of height (centre, half-width, half-depth);
    depth() tells how far points are inside it (> 0 inside). The trunk does not move with the arms."""

    def __init__(self, pos, mask, step=0.015):
        p = pos[mask]
        self.y0, self.step = float(p[:, 1].min()), step
        n = int((p[:, 1].max() - self.y0) / step) + 1
        self.cx, self.w, self.cz, self.d = (np.full(n, np.nan) for _ in range(4))
        for i in range(n):
            q = p[np.abs(p[:, 1] - (self.y0 + i * step)) < 0.75 * step]
            if len(q) < 20:
                continue
            self.cx[i], self.w[i] = 0.5 * (q[:, 0].max() + q[:, 0].min()), 0.5 * (q[:, 0].max() - q[:, 0].min())
            self.cz[i], self.d[i] = 0.5 * (q[:, 2].max() + q[:, 2].min()), 0.5 * (q[:, 2].max() - q[:, 2].min())

    def depth(self, pts):
        i = np.round((pts[:, 1] - self.y0) / self.step).astype(int)
        ok = (i >= 0) & (i < len(self.w))
        i = np.clip(i, 0, len(self.w) - 1)
        ok &= np.isfinite(self.w[i])
        w, d = np.nan_to_num(self.w[i], nan=1.0), np.nan_to_num(self.d[i], nan=1.0)
        # superellipse (p = 3): a trunk section is fuller than an ellipse at the diagonals, where the
        # ellipse let the hands sink into the lower belly unnoticed
        u = np.abs((pts[:, 0] - np.nan_to_num(self.cx[i])) / w)
        v = np.abs((pts[:, 2] - np.nan_to_num(self.cz[i])) / d)
        r = (u ** 3 + v ** 3) ** (1 / 3)
        return np.where(ok, (1.0 - r) * np.minimum(w, d), -1.0)


LAP_DX = 0.012     # dhyana: palm centre this far to its own side of the mid plane
# dhyana arm settings tried by build_poses (it keeps the best by thumb gap / hands / contact):
# xw = weight of the sideways palm target, dz = forward part of the finger direction
LAP_CFG = {"xw": 1000.0, "dz": 0.55}
LAP_CFGS = [{"xw": xw, "dz": dz} for xw in (300.0, 1000.0, 3000.0) for dz in (0.15, 0.55)]


def make_lap(point, d_t=None, torso=None, on_left=False):
    """Dhyana: palms up in the lap over the heels. d_t: wanted direction wrist -> middle knuckle;
    torso: forearm and hand stay out of the trunk; on_left: this (right) hand lies above the left one."""
    def fn(ctx, pos, H, Q, s):
        palm = pos[ctx.subh[f"palm.{s}"]]
        centre = palm.mean(axis=0)
        n = qrot(Q[ctx.rig.index[f"wrist.{s}"]], ctx.ps.hand_frame0(s)[1])
        # height and depth firm; sideways soft: the hands go as close to the middle as the arms reach
        # (a firm x left short arms at all their limits with the hand hanging 2-4 cm above the lap)
        c = 3e3 * float((centre[1] - point[1]) ** 2 + (centre[2] - point[2]) ** 2) + LAP_CFG["xw"] * float((centre[0] - point[0]) ** 2)
        c += 30 * (n[1] - 1.0) ** 2
        hand = pos[ctx.subh[f"hand.{s}"]]
        for cap in ("thigh.L", "thigh.R", "shin.L", "shin.R"):
            d = ctx.cap[cap].depth(H, hand)
            if np.isfinite(d).any():
                c += 3e4 * max(0.0, float(np.max(d)) - 0.004) ** 2
        if d_t is not None:
            dh = unit(H[ctx.rig.index[f"finger3-1.{s}"]] - H[ctx.rig.index[f"wrist.{s}"]])
            c += 150 * float(np.sum((dh - d_t) ** 2))
        if torso is not None:
            pts = pos[ctx.subh[f"fore.{s}"] | ctx.subh[f"hand.{s}"]]
            # keep 6 mm off the model trunk: the skin check still found the hands 1-1.5 cm in the belly
            c += 3e4 * max(0.0, float(torso.depth(pts).max()) + 0.006) ** 2
        if on_left:
            # the right hand lies ON the left one: never below its skin, and no gap either (the left
            # thumb is left out, it stands up to meet the right thumb and pushed the hand 2 cm up)
            other = pos[ctx.subh["nothumb.L"]][::2]
            mine = pos[ctx.subh["nothumb.R"]][::3]
            dxz = ((mine[:, None, 0] - other[None, :, 0]) ** 2 + (mine[:, None, 2] - other[None, :, 2]) ** 2) < 0.015 ** 2
            if dxz.any():
                under = np.where(dxz, other[None, :, 1], -np.inf).max(axis=1)
                gap = mine[:, 1] - under
                ok = np.isfinite(gap)
                if ok.any():
                    c += 2e5 * max(0.0, float(np.max(0.003 - gap[ok]))) ** 2       # through the left hand
                    c += 2e3 * max(0.0, float(np.min(gap[ok])) - 0.006) ** 2        # floating above it
        return c
    return fn
