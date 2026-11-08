"""Kidney (R1-R27), liver (F1-F14), governing vessel (VG1-VG28), conception vessel (VC1-VC24).

VG and VC are midline vessels: every ray starts at x = 0 and has no x component.
The scalp part of VG is measured along the midsagittal head profile. VG20 sits on the line
between the ear apices; glabella -> VG20 = 8 cun (3 cun to the anterior hairline + 5 cun) gives
the cun for VG21-VG24. The back of the head is anchored on the occipital protuberance (see below).
"""
import math

import numpy as np

from placement import (
    CUN_LEG, CUN_T, CUN_THIGH, KNEE_Y, MED_MALL_Y, NAVEL_Y, NOTCH_Y, PUBIS_Y, RC, VERT,
    back, face, foot_top, from_outside, front, ics_front, shin, sole, thigh, torso,
)

_VSTEP = VERT["T1"] - VERT["T2"]
_MED_MALL = MED_MALL_Y      # medial malleolus tip
_NAVEL_PIT = NAVEL_Y        # visible navel pit on the mesh (centre of the umbilicus)
_LOW_CUN = (NAVEL_Y - PUBIS_Y) / 5   # navel -> upper border of the pubic symphysis = 5 cun (WHO)


def _low(cun_below_navel):
    """Level `cun_below_navel` cun below the navel on the navel->pubis 5-cun scale."""
    return NAVEL_Y - cun_below_navel * _LOW_CUN


def _below(v):
    """Midline of the back, in the depression just below spinous process `v`."""
    return back(0.0, VERT[v] - _VSTEP / 2)


# ---- midsagittal head profile (for the scalp part of VG) ----
_HO = np.array([0.0, 1.560, -0.055])     # inside the cranium, above the mouth cavity
_EAR_APEX_Z = -0.070
_GLABELLA_Y = 1.572


def _hdir(phi):
    p = math.radians(phi)
    return np.array([0.0, math.sin(p), math.cos(p)])


def _head_profile():
    phis, pts = [], []
    for phi in np.arange(0.0, 262.0, 0.25):
        h = RC.first_hit(_HO, _hdir(phi))
        if h is None:
            continue
        phis.append(phi)
        pts.append(np.asarray(h[0], float))
    phis, pts = np.array(phis), np.array(pts)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    return phis, pts, s


_PHI, _PTS, _S = _head_profile()
_front_half = _PHI < 90
_i_gl = int(np.argmin(np.where(_front_half, np.abs(_PTS[:, 1] - _GLABELLA_Y), 9)))
_top = (_PHI > 45) & (_PHI < 135)
_i_vx = int(np.argmin(np.where(_top, np.abs(_PTS[:, 2] - _EAR_APEX_Z), 9)))
S_VERTEX = float(_S[_i_vx])
CUN_HEAD_FRONT = (S_VERTEX - _S[_i_gl]) / 8


def _s_back(y):
    """Arc position of the back-of-head profile point at height y."""
    m = (_PHI > 100) & (_PHI < 240)
    ys, ss = _PTS[m, 1], _S[m]
    return float(np.interp(y, ys[::-1], ss[::-1]))


# Back of the head is anchored on anatomy (the model's occiput is long relative to its
# forehead, so one cun scale cannot fit both): VG16 in the depression just below the external
# occipital protuberance, level with VB20; VG17 on the upper border of the protuberance,
# level with VB19. VG17 -> VG20 is split into three 1.5-cun steps.
S_VG16 = _s_back(1.500)
S_VG17 = _s_back(1.537)


def scalp_s(s):
    """Midline head ray landing at arc position s of the midsagittal profile."""
    phi = float(np.interp(s, _S, _PHI))
    for dphi in (0.0, 0.05, -0.05, 0.1, -0.1, 0.2, -0.2):
        if RC.first_hit(_HO, _hdir(phi + dphi)) is not None:
            return _HO, _hdir(phi + dphi)
    return _HO, _hdir(phi)


def scalp_front(cun_from_vertex):
    """Midline of the head, `cun_from_vertex` cun in front of VG20."""
    return scalp_s(S_VERTEX - cun_from_vertex * CUN_HEAD_FRONT)


def scalp_back(frac):
    """Back of the head between VG17 (frac 0) and VG20 (frac 1)."""
    return scalp_s(S_VG17 + (S_VERTEX - S_VG17) * frac)


def mid(o, d):
    """Midline ray helper: forces x = 0 in origin and direction."""
    o = np.array(o, float)
    d = np.array(d, float)
    o[0] = 0.0
    d[0] = 0.0
    return o, d


_CHEST_X = 2 * CUN_T
_ABD_X = 0.5 * CUN_T

SPEC = {
    # ---------------- Kidney: foot and ankle ----------------
    "R1": sole(0.222, -0.025),
    "R2": (np.array([0.215, 0.030, -0.055]), np.array([-1.0, -0.05, 0.0])),
    "R3": (np.array([0.220, 0.080, -0.125]), np.array([-1.0, 0.0, -0.4])),
    "R4": (np.array([0.220, 0.068, -0.130]), np.array([-0.8, -0.1, -0.6])),
    "R5": (np.array([0.220, 0.056, -0.132]), np.array([-1.0, -0.2, -0.3])),
    "R6": (np.array([0.220, 0.063, -0.100]), np.array([-1.0, -0.1, 0.0])),
    # ---------------- Kidney: leg ----------------
    "R7": shin(_MED_MALL + 2 * CUN_LEG, -140),
    "R8": shin(_MED_MALL + 2 * CUN_LEG, -108),
    "R9": shin(_MED_MALL + 5 * CUN_LEG, -140),
    "R10": thigh(KNEE_Y + 0.004, -145),
    # ---------------- Kidney: abdomen, 0.5 cun lateral ----------------
    "R11": front(_ABD_X, PUBIS_Y),
    "R12": front(_ABD_X, _low(4)),
    "R13": front(_ABD_X, _low(3)),
    "R14": front(_ABD_X, _low(2)),
    "R15": front(_ABD_X, _low(1)),
    "R16": front(_ABD_X, _NAVEL_PIT),
    "R17": front(_ABD_X, NAVEL_Y + 2 * CUN_T),
    "R18": front(_ABD_X, NAVEL_Y + 3 * CUN_T),
    "R19": front(_ABD_X, NAVEL_Y + 4 * CUN_T),
    "R20": front(_ABD_X, NAVEL_Y + 5 * CUN_T),
    "R21": front(_ABD_X, NAVEL_Y + 6 * CUN_T),
    # ---------------- Kidney: chest, 2 cun lateral ----------------
    "R22": front(_CHEST_X, ics_front(5)),
    "R23": front(_CHEST_X, ics_front(4)),
    "R24": front(_CHEST_X, ics_front(3)),
    "R25": front(_CHEST_X, ics_front(2)),
    "R26": front(_CHEST_X, ics_front(1)),
    "R27": front(_CHEST_X, 1.334),
    # ---------------- Liver ----------------
    "F1": (np.array([0.196, 0.016, 0.074]), np.array([1.0, 0.6, 0.0])),
    "F2": foot_top(0.202, 0.028),     # web margin on the dorsum (z 0.034 slipped into the toe gap)
    "F3": foot_top(0.205, -0.002),
    "F4": (np.array([0.215, 0.076, -0.080]), np.array([-0.8, 0.0, 0.6])),
    "F5": shin(_MED_MALL + 5 * CUN_LEG, -65),
    "F6": shin(_MED_MALL + 7 * CUN_LEG, -65),
    "F7": shin(0.410, -133),
    "F8": thigh(KNEE_Y + 0.004, -118),
    "F9": thigh(0.470 + 4 * CUN_THIGH, -100),
    "F10": front(0.050, PUBIS_Y - 3 * CUN_T),
    "F11": front(0.048, PUBIS_Y - 2 * CUN_T),
    "F12": front(2.5 * CUN_T, PUBIS_Y - 0.022),   # level with the lower border of the symphysis
    "F13": (np.array([0.0, 1.050, -0.060]), np.array([math.sin(math.radians(85)), 0.0, math.cos(math.radians(85))])),
    "F14": front(4 * CUN_T, ics_front(6)),
    # ---------------- Governing vessel ----------------
    # VG1 midway between the coccyx tip (V35 level, ~0.828) and the anus; VG2 in the sacral
    # hiatus, level with the 4th sacral foramina (V30/V34), where the gluteal cleft begins.
    # (a landing higher than ~0.805 falls deep into the gluteal cleft and is hidden from behind)
    "VG1": mid([0, 0.856, -0.100], [0, -0.05, -0.045]),
    "VG2": back(0.0, VERT["S4"]),
    "VG3": _below("L4"),
    "VG4": _below("L2"),
    "VG5": _below("L1"),
    "VG6": _below("T11"),
    "VG7": _below("T10"),
    "VG8": _below("T9"),
    "VG9": _below("T7"),
    "VG10": _below("T6"),
    "VG11": _below("T5"),
    "VG12": _below("T3"),
    "VG13": _below("T1"),
    "VG14": _below("C7"),
    "VG15": scalp_s(S_VG16 + (S_VG16 - S_VG17) / 3),   # 0.5 cun below VG16
    "VG16": scalp_s(S_VG16),
    "VG17": scalp_s(S_VG17),
    # VG18 midway VG16-VG20, VG19 midway VG18-VG20 (4 / 5.5 / 7 cun above the hairline)
    "VG18": scalp_s((S_VG16 + S_VERTEX) / 2),
    "VG19": scalp_s((S_VG16 + 3 * S_VERTEX) / 4),
    "VG20": scalp_s(S_VERTEX),
    "VG21": scalp_front(1.5),
    "VG22": scalp_front(3.0),
    "VG23": scalp_front(4.0),
    "VG24": scalp_front(4.5),
    "VG25": face(0.0, 1.508),
    "VG26": face(0.0, 1.491),
    "VG27": face(0.0, 1.484),
    "VG28": mid([0, 1.479, -0.010], [0, 0.15, 1.0]),
    # ---------------- Conception vessel ----------------
    "VC1": mid([0, 0.850, -0.080], [0, -1.0, 0]),
    "VC2": front(0.0, PUBIS_Y),
    "VC3": front(0.0, _low(4)),
    "VC4": front(0.0, _low(3)),
    "VC5": front(0.0, _low(2)),
    "VC6": front(0.0, _low(1.5)),
    "VC7": front(0.0, _low(1)),
    "VC8": front(0.0, _NAVEL_PIT),
    "VC9": front(0.0, NAVEL_Y + 1 * CUN_T),
    "VC10": front(0.0, NAVEL_Y + 2 * CUN_T),
    "VC11": front(0.0, NAVEL_Y + 3 * CUN_T),
    "VC12": front(0.0, NAVEL_Y + 4 * CUN_T),
    "VC13": front(0.0, NAVEL_Y + 5 * CUN_T),
    "VC14": front(0.0, NAVEL_Y + 6 * CUN_T),
    "VC15": front(0.0, NAVEL_Y + 7 * CUN_T),
    "VC16": front(0.0, ics_front(5)),
    "VC17": front(0.0, ics_front(4)),
    "VC18": front(0.0, ics_front(3)),
    "VC19": front(0.0, ics_front(2)),
    "VC20": front(0.0, ics_front(1)),
    "VC21": front(0.0, NOTCH_Y - CUN_T),
    "VC22": mid([0, 1.340, -0.080], [0, 0.35, 1.0]),
    "VC23": mid([0, 1.400, -0.080], [0, 0.025, 0.045]),
    "VC24": face(0.0, 1.459),
}

VIA = {
    # kidney: up the posteromedial thigh to the pubic area
    "R10>R11": [thigh(0.560, -135), thigh(0.680, -115), thigh(0.790, -60), front(0.030, 0.830)],
    # liver: medial thigh to the groin, groin around the lower abdomen to the 11th rib, rib to chest
    "F9>F10": [thigh(0.630, -88), thigh(0.720, -72)],
    "F12>F13": [front(0.072, 0.925, lat=0.25), torso(0.985, 62, z=-0.060)],
    "F13>F14": [torso(1.095, 58, z=-0.060)],
    # governing vessel: nape, forehead and nose ridge
    "VG1>VG2": [back(0.0, 0.830)],
    "VG14>VG15": [mid([0, 1.435, -0.080], [0, 0.0, -1.0])],
    "VG24>VG25": [face(0.0, 1.605), face(0.0, 1.572), face(0.0, 1.548), face(0.0, 1.527)],
    # conception vessel: perineum round to the pubis, neck under the chin
    "VC1>VC2": [mid([0, 0.830, -0.060], [0, -1.0, 0.7]), mid([0, 0.830, -0.060], [0, -0.5, 1.0])],
    "VC23>VC24": [from_outside(np.array([0.0, 1.437, 0.020]), (0.0, -1.0, 0.25)), face(0.0, 1.447)],
    # yang wei / yang qiao: up the side of the trunk along the posterior axillary line to the back of
    # the shoulder (IG10); without waypoints the long jump from the leg cut through the armpit gap
    # and was drawn in the air between the flank and the arm
    "VB35>IG10": [thigh(0.560, 92), thigh(0.760, 92), torso(0.950, 95), torso(1.080, 100),
                  torso(1.180, 108), torso(1.250, 125)],
    "VB29>IG10": [torso(0.980, 98), torso(1.080, 100), torso(1.180, 108), torso(1.250, 125)],
}
