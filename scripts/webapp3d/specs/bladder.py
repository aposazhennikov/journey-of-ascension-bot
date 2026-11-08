"""Bladder meridian (V1-V67).

Course: inner canthus -> eyebrow -> scalp 1.5 cun from the midline -> occiput and nape.
On the back two lines descend: the inner one 1.5 cun from the posterior midline (V11-V30),
then the sacral foramina (V31-V34), beside the coccyx (V35), the gluteal fold (V36) and down
the middle of the thigh (V37) to the popliteal crease (V40). The outer line separates at the
nape, runs 3 cun from the midline (V41-V54), descends the posterolateral thigh (V38, V39) and
joins the first one at V40. From there: calf (V55-V58), behind the lateral malleolus (V59-V60),
lateral edge of the foot (V61-V66), little toe (V67).
"""
import math

import numpy as np

from placement import (
    CUN_LEG, CUN_THIGH, HEAD_C, KNEE_Y, MALL_Y, RC, VERT, _VERT_STEP,
    back, from_outside, shin, thigh, unit,
)

# ---- scalp: proportional cun along the sagittal arc ----
# Elevations from the head centre on the midline, matched to the VG points of
# kidney_liver_vessels.py: vertex VG20 ~99 deg (line of the ear apices), anterior hairline
# 5 cun in front of it (~54.5 deg, VG24 0.5 cun behind it), posterior hairline 7 cun behind
# it (~207 deg, nape y ~ 1.49). The model's occiput is long, so the cun is measured
# piecewise: ~0.021 m in front of the vertex, larger behind it.
_HAIR_FRONT_EL, _VERTEX_EL, _HAIR_BACK_EL = 54.5, 99.0, 207.0


def _sagittal_profile():
    els, pts = [], []
    for el in np.arange(_HAIR_FRONT_EL, _HAIR_BACK_EL + 0.01, 0.5):
        e = math.radians(el)
        hit = RC.first_hit(HEAD_C, np.array([0.0, math.sin(e), math.cos(e)]))
        if hit is not None:            # a few rays slip through mesh seams
            els.append(el)
            pts.append(hit[0])
    els, pts = np.array(els), np.array(pts)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    return els, arc


_ELS, _ARC = _sagittal_profile()
_ARC_VERTEX = float(np.interp(_VERTEX_EL, _ELS, _ARC))


def _el_at(cun_behind_front_hairline):
    c = cun_behind_front_hairline
    if c <= 5:
        a = c / 5 * _ARC_VERTEX
    else:
        a = _ARC_VERTEX + (c - 5) / 7 * (_ARC[-1] - _ARC_VERTEX)
    return float(np.interp(a, _ARC, _ELS))


# Transverse head cun ~0.0144 m (midline -> E8 arc / 4.5, same as gallbladder_spleen.py).
# Measured along the scalp arc, 1.5 cun = 0.0216 m lands at x 0.0211-0.0215 for V4-V8 and
# 1.3 cun at x ~0.0186, so the bladder line stays medial to the GB line (VB15 x ~0.031).
X_HEAD, X_HEAD_13 = 0.0213, 0.0186


def scalp(x, cun_behind_front_hairline):
    """Scalp point at lateral offset x, `cun` behind the anterior hairline (12 cun to the
    posterior hairline). Ray in the sagittal plane x from the head-centre height."""
    e = math.radians(_el_at(cun_behind_front_hairline))
    return HEAD_C + np.array([x, 0.0, 0.0]), np.array([0.0, math.sin(e), math.cos(e)])


# ---- back ----
X_IN, X_OUT = 0.033, 0.066          # 1.5 and 3 cun from the posterior midline


def below(k):
    """Level of the depression below the spinous process `k`."""
    return VERT[k] - 0.5 * _VERT_STEP


_INNER = {  # V11-V26: inner line, below spinous processes
    "V11": "T1", "V12": "T2", "V13": "T3", "V14": "T4", "V15": "T5", "V16": "T6",
    "V17": "T7", "V18": "T9", "V19": "T10", "V20": "T11", "V21": "T12", "V22": "L1",
    "V23": "L2", "V24": "L3", "V25": "L4", "V26": "L5",
}
_OUTER = {  # V41-V52: outer line
    "V41": "T2", "V42": "T3", "V43": "T4", "V44": "T5", "V45": "T6", "V46": "T7",
    "V47": "T9", "V48": "T10", "V49": "T11", "V50": "T12", "V51": "L1", "V52": "L2",
}

# ---- leg ----
GLUTEAL_FOLD_Y = 0.765
V60_Y = MALL_Y + 0.003
CALF_MID_Y = (KNEE_Y + V60_Y) / 2          # V57: midway V40 - V60
V55_Y = KNEE_Y - 2 * CUN_LEG


def foot_side(y, z, x0=0.225, down=-0.15, back_=0.0):
    """Lateral edge of the foot: inside-out from inside the foot toward +x."""
    return np.array([x0, y, z]), np.array([1.0, down, back_])


SPEC = {
    # face
    "V1": from_outside(np.array([0.0185, 1.547, 0.028]), np.array([-0.6, 0.15, 1.0]), dist=0.12),
    "V2": from_outside(np.array([0.019, 1.566, 0.036]), np.array([-0.15, 0.25, 1.0]), dist=0.12),
    # scalp, 1.5 head cun from the midline (V3 directly above V2, medial to V4)
    "V3": scalp(0.017, 0.5),
    "V4": scalp(X_HEAD, 0.5),
    "V5": scalp(X_HEAD, 1.0),
    "V6": scalp(X_HEAD, 2.5),
    "V7": scalp(X_HEAD, 4.0),
    "V8": scalp(X_HEAD, 5.5),
    # 1.3 head cun lateral to VG17 (upper border of the external occipital protuberance,
    # y ~1.537 in kidney_liver_vessels.py) and to VG15 (y ~1.487, lateral border of the trapezius)
    "V9": (np.array([X_HEAD_13, 1.533, -0.06]), np.array([0.0, 0.05, -1.0])),
    "V10": (np.array([0.019, 1.488, -0.08]), np.array([0.0, 0.0, -1.0])),
}

SPEC.update({code: back(X_IN, below(v)) for code, v in _INNER.items()})
SPEC.update({
    # inner line at the level of the sacral foramina
    "V27": back(X_IN, VERT["S1"]),
    "V28": back(X_IN, VERT["S2"]),
    "V29": back(X_IN, VERT["S3"]),
    "V30": back(X_IN, VERT["S4"]),
    # posterior sacral foramina (close to the midline, narrowing downward)
    "V31": back(0.021, VERT["S1"]),
    "V32": back(0.019, VERT["S2"]),
    "V33": back(0.017, VERT["S3"]),
    "V34": back(0.015, VERT["S4"]),
    # 0.5 cun beside the tip of the coccyx
    "V35": back(0.011, VERT["coccyx"] - 0.007),
    # thigh and popliteal fossa
    "V36": thigh(GLUTEAL_FOLD_Y, 180),
    "V37": thigh(GLUTEAL_FOLD_Y - 6 * CUN_THIGH, 180),
    "V38": thigh(KNEE_Y + CUN_THIGH, 148),
    "V39": thigh(KNEE_Y + 0.002, 142),
    "V40": thigh(KNEE_Y, 180),
})
SPEC.update({code: back(X_OUT, below(v)) for code, v in _OUTER.items()})
SPEC.update({
    "V53": back(X_OUT, VERT["S2"]),
    "V54": back(X_OUT, VERT["S4"]),
    # calf
    "V55": shin(V55_Y, 180),
    "V56": shin((V55_Y + CALF_MID_Y) / 2, 180),
    "V57": shin(CALF_MID_Y, 180),
    "V58": shin(V60_Y + 7 * CUN_LEG, 160),        # ~1 cun lateral/inferior to V57 (az 145 gave ~1.7 cun)
    "V59": shin(V60_Y + 3 * CUN_LEG, 135),
    # ankle and lateral foot
    "V60": (np.array([0.222, V60_Y, -0.115]), unit([0.75, 0.0, -0.66])),
    "V61": (np.array([0.222, 0.026, -0.115]), unit([0.8, -0.1, -0.6])),
    # mesh: lateral malleolus prominence at z ~-0.117; lateral foot edge widest (5th metatarsal
    # head) at z ~-0.005; little toe MTP ~0.010 (toe web 0.017), toe tip 0.043, nail base ~0.035;
    # 5th metatarsal tuberosity by proportion ~-0.058 (no clear bump on the mesh)
    "V62": foot_side(0.048, -0.113),
    "V63": foot_side(0.028, -0.077),
    "V64": foot_side(0.016, -0.045),
    "V65": foot_side(0.013, -0.011, x0=0.235),
    # little toe: the mesh toe lies at x 0.255-0.27, z 0.01-0.043 (the toe-5 landmarks sit
    # on its upper surface, so rays start a little lower, inside the toe)
    "V66": foot_side(0.011, 0.018, x0=0.262),
    "V67": (np.array([0.260, 0.011, 0.035]), np.array([1.0, 0.6, 0.1])),
})

VIA = {
    # along the outer side of the little toe to its nail (the curve hooked round the toe tip)
    "V66>V67": [(np.array([0.36, 0.0125, 0.027]), np.array([-1.0, 0.0, 0.0]))],
    # over the occiput instead of a chord through the skull
    "V8>V9": [scalp(0.0208, 7.0), scalp(0.0197, 8.5)],
    # coccyx -> over the lower buttock -> gluteal fold
    "V35>V36": [back(0.065, 0.800)],
    # outer branch: over the buttock, then down the posterolateral thigh, clearly lateral to
    # the inner line V36-V37 (az 180) so the two branches do not overlap seen from behind
    "V54>V38": [back(0.105, 0.830), thigh(0.78, 145), thigh(0.66, 140), thigh(0.54, 142)],
}

CHAINS = {
    "bladder": [
        ["V%d" % i for i in range(1, 38)] + ["V40"],
        ["V10"] + ["V%d" % i for i in range(41, 55)] + ["V38", "V39", "V40"]
        + ["V%d" % i for i in range(55, 68)],
    ],
}
