"""Gallbladder (VB1-VB44) and spleen (RP1-RP21)."""
import numpy as np

from placement import (
    CUN_LEG, CUN_T, CUN_THIGH, J, KNEE_Y, MALL_Y, NAVEL_Y, PUBIS_Y, RC,
    aim, az_dir, core_z, face, foot_top, front, head, ics_front, shin, sph, thigh, torso,
)

_ST8 = (45, 45)
_GB7 = (88, 18)
_LOW_CUN = (NAVEL_Y - PUBIS_Y) / 5          # navel -> pubic symphysis = 5 cun (WHO)
_VC4_Y = NAVEL_Y - 3 * _LOW_CUN             # 3 cun below the navel


def _temple(frac):
    return sph(_ST8[0] + (_GB7[0] - _ST8[0]) * frac, _ST8[1] + (_GB7[1] - _ST8[1]) * frac)


def _chest_arc(y, cun):
    """Trunk ray at height y that lands `cun` trunk cun from the anterior midline, measured
    along the skin of the horizontal section (the chest wraps round beyond the nipple line,
    so an x offset of 6 cun would fall on the midaxillary line or off the body)."""
    zc = core_z(round(y, 4))
    o = np.array([0.0, y, zc])
    prev, s = None, 0.0
    for az in np.arange(0.0, 120.0, 0.25):
        h = RC.first_hit(o, az_dir(az))
        if h is None:
            continue
        p = np.asarray(h[0], float)
        if prev is not None:
            s += float(np.linalg.norm(p - prev))
        prev = p
        if s >= cun * CUN_T:
            return torso(y, float(az))
    return torso(y, 60.0)


_L = J["l-ankle"]

SPEC = {
    # Gallbladder: head
    # VB1 outside-in on the lateral orbital rim, 0.5 cun lateral to the outer canthus (x ~0.044)
    "VB1": face(0.051, 1.545, 0.018, toward=(0.4, 0.0, 0.9)),
    "VB2": sph(86, -9),
    "VB3": sph(74, 4),
    "VB4": _temple(0.25),
    "VB5": _temple(0.50),
    "VB6": _temple(0.75),
    "VB7": sph(88, 18),
    "VB8": sph(102, 36),
    "VB9": sph(113, 33),
    "VB10": sph(122, 18),
    "VB11": sph(127, 3),
    "VB12": sph(126, -13),
    # forehead: VG24 (midline) -> VB15 (2.25 cun, above the pupil) -> VB13 (3 cun) -> E8 (4.5 cun);
    # transverse head cun on this model ~0.0144 m (midline -> E8 arc / 4.5)
    "VB13": aim(0.040, 1.621, 0.014),
    "VB14": sph(21, 34),
    "VB15": aim(0.031, 1.630, 0.016),
    # VB15 -> VB20 line, 2.25 cun lateral; VB16/17/18 at 1, 2 and 3.5 cun behind VB15
    # (midline levels 4.5, 5.5 and 7 cun above the glabella, head cun 0.0208 m)
    "VB16": aim(0.033, 1.647, -0.001),
    "VB17": aim(0.034, 1.656, -0.019),
    "VB18": aim(0.034, 1.661, -0.049),
    "VB19": head(0.38, 0.05, -1.0),
    "VB20": head(0.42, -0.45, -1.0),
    # Gallbladder: shoulder, trunk, hip
    # VB21 on the shoulder summit, midway between VG14 (0, 1.387, -0.144) and the acromion (0.21, 1.36, -0.095)
    "VB21": (np.array([0.105, 1.320, -0.115]), np.array([0.0, 1.0, 0.0])),
    "VB22": torso(ics_front(4), 92, z=-0.060),
    "VB23": torso(ics_front(4), 85),                 # 1 cun in front of VB22 along the 4th ICS
    "VB24": front(4 * CUN_T, ics_front(7) - 0.005),
    "VB25": torso(1.030, 102, z=-0.060),             # below the 12th rib tip, behind and below F13
    "VB26": torso(NAVEL_Y, 85, z=-0.060),            # straight below F13 (z -0.049)
    "VB27": front(0.122, _VC4_Y),                    # just medial/anterior to the ASIS (~x 0.13)
    "VB28": front(0.115, _VC4_Y - 0.5 * _LOW_CUN),
    "VB29": torso(0.872, 62, x=0.10, z=-0.07),
    # 1/3 of the way from the greater trochanter (0.178, 0.82) to the sacral hiatus (VG2)
    "VB30": torso(0.833, 172, x=0.118, z=-0.09),
    # Gallbladder: leg and foot
    "VB31": thigh(KNEE_Y + 7 * CUN_THIGH, 90),
    "VB32": thigh(KNEE_Y + 5 * CUN_THIGH, 90),
    "VB33": thigh(0.405 + 3 * CUN_LEG, 92),
    "VB34": shin(0.405, 62),
    # fibula: posterior border ~az 115, anterior border ~az 82 (E40 lies in front, at az 72)
    "VB35": shin(MALL_Y + 7 * CUN_LEG, 115),
    "VB36": shin(MALL_Y + 7 * CUN_LEG, 82),
    "VB37": shin(MALL_Y + 5 * CUN_LEG, 82),
    "VB38": shin(MALL_Y + 4 * CUN_LEG, 84),
    "VB39": shin(MALL_Y + 3 * CUN_LEG, 86),
    # lateral malleolus bulge at (0.259, 0.07, -0.11); VB40 in the depression in front of and below it
    "VB40": (np.array([0.215, 0.054, -0.095]), np.array([1.0, -0.1, 0.3])),
    # distal to the junction of the 4th/5th metatarsal bases (5th tuberosity ~z -0.058), not at the MTP heads
    "VB41": foot_top(0.244, -0.038),                 # x 0.248 already slid onto the lateral edge
    "VB42": foot_top(0.252, 0.002),
    "VB43": foot_top(0.2535, 0.017),                 # web margin between toes 4 and 5
    "VB44": (J["l-toe-4-3"], np.array([1.0, 0.6, 0.3])),
    # Spleen: foot and leg
    "RP1": (np.array([0.193, 0.017, 0.066]), np.array([-1.0, 0.3, 0.0])),
    "RP2": (np.array([0.195, 0.018, 0.040]), np.array([-1.0, -0.1, 0.0])),
    "RP3": (np.array([0.198, 0.018, 0.012]), np.array([-1.0, -0.2, 0.0])),
    "RP4": (np.array([0.202, 0.024, -0.025]), np.array([-1.0, -0.1, 0.0])),
    # midway between the medial malleolus tip (~0.19, 0.08, -0.095) and the navicular tuberosity (R2 above)
    "RP5": (np.array([0.215, 0.062, -0.085]), np.array([-0.9, -0.05, 0.4])),
    "RP6": shin(0.080 + 3 * CUN_LEG, -100),
    "RP7": shin(0.080 + 6 * CUN_LEG, -100),
    "RP8": shin(0.410 - 3 * CUN_LEG, -100),
    "RP9": shin(0.410, -108),
    "RP10": thigh(0.490 + 2 * CUN_THIGH, -70),
    "RP11": thigh(0.490 + 8 * CUN_THIGH, -60),
    # Spleen: abdomen and chest
    "RP12": front(3.5 * CUN_T, PUBIS_Y),
    "RP13": front(4 * CUN_T, PUBIS_Y + 0.7 * _LOW_CUN),
    "RP14": front(4 * CUN_T, NAVEL_Y - 1.3 * _LOW_CUN),
    "RP15": front(4 * CUN_T, NAVEL_Y),
    "RP16": front(4 * CUN_T, NAVEL_Y + 3 * CUN_T),
    "RP17": _chest_arc(ics_front(5), 6),
    "RP18": _chest_arc(ics_front(4), 6),
    "RP19": _chest_arc(ics_front(3), 6),
    "RP20": _chest_arc(ics_front(2), 6),
    "RP21": torso(ics_front(6), 92, z=-0.060),
}

VIA = {
    "VB12>VB13": [sph(120, 42), sph(100, 55), sph(65, 58)],
    # shoulder -> supraclavicular fossa (ST12, outside-in from above like E12) -> down in front of the
    # armpit to VB22; before, the line ran out onto the deltoid and jumped through the armpit gap
    "VB21>VB22": [(np.array([4 * CUN_T, 1.40, -0.050]), np.array([0.0, -1.0, 0.25])),
                  torso(1.300, 60), torso(1.250, 78)],
    # spleen -> heart transition: up the side of the chest into the armpit hollow to C1 (it jumped
    # 3 cm through the air from the chest wall onto the arm)
    "RP21>C1": [torso(1.200, 95), torso(1.240, 97)],
}
