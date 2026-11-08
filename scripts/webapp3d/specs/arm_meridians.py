"""Arm meridians: lung (P1-P11), large intestine (GI1-GI20), heart (C1-C9),
small intestine (IG1-IG19), pericardium (MC1-MC9), triple burner (TR1-TR23).

Arm angles here are ANATOMICAL (arm in supination): 0 = anterior/palmar midline,
+90 = radial/lateral, -90 = ulnar/medial, 180 = posterior/dorsal.

The model's hand is pronated (palm down/back, thumb forward) and placement.py builds the
arm frame from the hand, so on the upper arm its theta 0 is not the biceps side. `_ua`
and `_fa` convert: the upper-arm anterior is the elbow flexion direction (the forearm
bends forward), and on the forearm the pronation twist goes linearly from 0 at the
wrist crease to the full offset at the elbow crease.
"""
import math

import numpy as np

from placement import (
    CUN_T, ELBOW, J, SHOULDER, WRIST,
    _arm_frame, aim, back, face, forearm, front, hand, ics_front, lerp, unit, upper_arm,
)


def _frame_theta(seg_a, seg_b, direction):
    _, palmar, radial = _arm_frame(seg_a, seg_b)
    return math.degrees(math.atan2(direction @ radial, direction @ palmar))


_AX_U = unit(ELBOW - SHOULDER)
_AX_F = unit(WRIST - ELBOW)
# anterior of the upper arm = direction the forearm is bent toward
_UOFF = _frame_theta(SHOULDER, ELBOW, unit(_AX_F - _AX_U * (_AX_F @ _AX_U)))
# anterior of the forearm at the elbow = toward the upper arm
_FOFF = _frame_theta(ELBOW, WRIST, unit(-_AX_U + _AX_F * (_AX_U @ _AX_F)))


def _ua(cun_above_elbow, theta):
    """Upper arm, anatomical theta, cun above the elbow crease."""
    return upper_arm(cun_above_elbow, theta + _UOFF)


def _fa(cun_above_wrist, theta):
    """Forearm, anatomical theta, cun above the wrist crease."""
    return forearm(cun_above_wrist, theta + _FOFF * cun_above_wrist / 12.0)


def _crease(theta, psi=-20.0):
    """Front of the elbow crease. The elbow is flexed ~47 deg, so the skin fold lies in the
    bisector plane, ~20 deg proximal of the upper-arm perpendicular; a perpendicular ray lands
    ~1 cun distal of the fold, on the forearm."""
    origin, d0 = _ua(0, theta)
    d0 = unit(d0)
    p = math.radians(psi)
    return origin, d0 * math.cos(p) + _AX_U * math.sin(p)


def _f(n, k):
    return J[f"l-finger-{n}-{k}"]


def _hd(theta, along=0.0):
    """Hand-frame direction (same frame as placement.hand)."""
    return hand(WRIST, theta, along)[1]


def _neck(y, az, z=-0.085):
    """Neck: origin on the neck axis, direction by azimuth (0 front, 90 lateral, 180 back)."""
    a = math.radians(az)
    return np.array([0.0, y, z]), np.array([math.sin(a), 0.0, math.cos(a)])


def _nail(n, theta, t=0.35):
    """Side of the nail corner of finger n: origin in the distal phalanx near the nail base."""
    return hand(lerp(_f(n, 3), _f(n, 4), t), theta, 0.0)


_MCP45 = lerp(_f(4, 1), _f(5, 1), 0.5)
_MCP23 = lerp(_f(2, 1), _f(3, 1), 0.6)
_S = J["l-shoulder"]

SPEC = {
    # ---- Lung ----
    "P1": front(6 * CUN_T, ics_front(1), lat=0.1),
    "P2": front(6 * CUN_T - 0.002, ics_front(1) + 1 * CUN_T, lat=0.1),
    "P3": _ua(6, 35),
    "P4": _ua(5, 35),
    "P5": _crease(22),
    "P6": _fa(7, 38),
    "P7": _fa(1.5, 80),
    "P8": _fa(1, 60),
    "P9": _fa(0, 55),
    "P10": hand(lerp(_f(1, 1), _f(1, 2), 0.5), 60),
    # thumb is pronated: in the hand frame its nail faces ~110, its radial edge is at ~25,
    # so the radial nail corner is at ~38 (120 was the middle of the nail)
    "P11": hand(lerp(_f(1, 3), _f(1, 4), 0.4), 38),
    # ---- Large intestine ----
    "GI1": _nail(2, 130),
    "GI2": hand(lerp(_f(2, 1), _f(2, 2), 0.25), 95),
    "GI3": hand(lerp(WRIST, _f(2, 1), 0.85), 95),
    "GI4": hand(lerp(WRIST, _f(2, 1), 0.55), 135),
    "GI5": _fa(0, 118),
    "GI6": _fa(3, 112),
    "GI7": _fa(5, 107),
    "GI8": _fa(8, 98),
    "GI9": _fa(9, 94),
    "GI10": _fa(10, 90),
    "GI11": _ua(0, 75),
    "GI12": _ua(1, 115),
    "GI13": _ua(3, 98),
    "GI14": _ua(7, 90),
    "GI15": (_S, np.array([0.65, 0.65, 0.3])),
    "GI16": (np.array([0.152, 1.33, -0.10]), np.array([0.0, 1.0, -0.15])),
    "GI17": _neck(1.387, 80),
    "GI18": _neck(1.405, 72),
    "GI19": face(0.012, 1.490, z_hint=0.045, toward=(0.15, 0.0, 1.0)),
    "GI20": face(0.025, 1.505, z_hint=0.033, toward=(0.35, 0.0, 1.0)),
    # ---- Heart ----
    "C1": (np.array([0.175, 1.15, -0.09]), np.array([0.0, 1.0, 0.0])),
    "C2": _ua(3, -70),
    "C3": _ua(0, -78),
    "C4": _fa(1.5, -62),
    "C5": _fa(1, -62),
    "C6": _fa(0.5, -62),
    "C7": _fa(0, -62),
    "C8": hand(lerp(WRIST, _MCP45, 0.62), 0),
    "C9": _nail(5, 130),
    # ---- Small intestine ----
    "IG1": _nail(5, -130),
    "IG2": hand(lerp(_f(5, 1), _f(5, 2), 0.25), -95),
    "IG3": hand(lerp(WRIST, _f(5, 1), 0.82), -95),
    "IG4": hand(lerp(WRIST, _f(5, 1), 0.25), -85),
    "IG5": _fa(0, -100),
    "IG6": _fa(1, -140),
    "IG7": _fa(5, -130),
    "IG8": _ua(0, -145),
    "IG9": back(0.165, 1.295),
    "IG10": back(0.165, 1.345),
    "IG11": back(0.100, 1.290),
    "IG12": back(0.102, 1.350),
    "IG13": back(0.076, 1.345),
    "IG14": back(0.066, 1.362),
    "IG15": back(0.044, 1.390),
    "IG16": _neck(1.410, 92),
    "IG17": _neck(1.458, 70, z=-0.075),
    "IG18": face(0.045, 1.510, z_hint=0.022, toward=(0.35, 0.0, 1.0)),
    "IG19": aim(0.072, 1.530, -0.042),
    # ---- Pericardium ----
    "MC1": front(5 * CUN_T - 0.002, ics_front(4)),
    "MC2": _ua(7, 0),
    "MC3": _crease(-10),
    "MC4": _fa(5, 0),
    "MC5": _fa(3, 0),
    "MC6": _fa(2, 0),
    "MC7": _fa(0, 0),
    "MC8": hand(lerp(WRIST, _MCP23, 0.62), 0),
    "MC9": (lerp(_f(3, 3), _f(3, 4), 0.3), _f(3, 4) - _f(3, 3)),
    # ---- Triple burner ----
    "TR1": _nail(4, -130),
    # web margin between the 4th and 5th fingers (0.1 sat on the knuckles; the mesh web is
    # shallow - MCP->PIP is ~25 mm and from 0.3 on the origin is in the finger gap and misses)
    "TR2": hand(lerp(_MCP45, lerp(_f(4, 2), _f(5, 2), 0.5), 0.25), 180),
    "TR3": hand(lerp(WRIST, _MCP45, 0.8), 180),
    "TR4": _fa(0, -170),
    "TR5": _fa(2, 180),
    "TR6": _fa(3, 180),
    "TR7": _fa(3, -160),
    "TR8": _fa(4, 180),
    "TR9": _fa(7, 180),
    "TR10": _ua(1, 180),
    "TR11": _ua(2, 180),
    "TR12": _ua(5, 180),
    # WHO: 3 cun below the acromial angle (8 cun put it ~5 cun below TR14)
    "TR13": _ua(9.5, 170),
    # posterolateral shoulder below the acromial angle, ~2 cun behind GI15 (the old ray
    # (0.65, 0.65, -0.25) landed on top of the shoulder, 25 mm from GI15)
    "TR14": (_S, np.array([0.6, 0.55, -0.55])),
    "TR15": (np.array([0.09, 1.33, -0.09]), np.array([0.0, 0.6, -1.0])),
    "TR16": _neck(1.457, 112),
    "TR17": aim(0.060, 1.503, -0.078),
    "TR18": aim(0.064, 1.518, -0.086),
    "TR19": aim(0.068, 1.540, -0.086),
    "TR20": aim(0.074, 1.558, -0.066),
    "TR21": aim(0.072, 1.541, -0.042),
    "TR22": aim(0.070, 1.552, -0.030),
    "TR23": face(0.050, 1.560, z_hint=0.020, toward=(0.5, 0.0, 0.85)),
}

VIA = {
    # over the top of the anterior axillary fold (solid skin from y ~1.29 up); the old
    # second waypoint went up into the armpit vault and the line jumped across the gap
    "MC1>MC2": [(np.array([0.10, 1.25, -0.07]), np.array([0.5, 0.0, 0.866])),
                (np.array([0.165, 1.295, -0.09]), np.array([0.0, 0.0, 1.0]))],
    "C7>C8": [hand(lerp(WRIST, _MCP45, 0.3), -15)],
    "IG8>IG9": [_ua(3, -160), _ua(6, -170)],
    "IG15>IG16": [_neck(1.405, 120)],
    "IG18>IG19": [aim(0.064, 1.520, -0.010)],
    "TR9>TR10": [_fa(11, 180), _ua(0, 180)],
    "GI14>GI15": [_ua(10, 80)],
    "TR14>TR15": [back(0.14, 1.368)],
    "GI18>GI19": [_neck(1.432, 55, z=-0.07), face(0.040, 1.462, z_hint=0.02, toward=(0.6, 0.0, 0.8)),
                  face(0.026, 1.478, z_hint=0.04, toward=(0.3, 0.0, 1.0))],
    "IG17>IG18": [face(0.055, 1.480, z_hint=0.0, toward=(0.8, 0.0, 0.6))],
    "TR15>TR16": [_neck(1.410, 130)],
    "TR20>TR21": [aim(0.072, 1.553, -0.048)],
}
