"""Stomach (E1-E45)."""
import numpy as np

from placement import (
    CUN_T, CUN_THIGH, J, MALL_Y, NAVEL_Y, PATELLA_TOP_Y, PUBIS_Y,
    face, foot_top, front, ics_front, shin, sph, thigh,
)

_PUPIL_X = 0.031

_E35_Y = 0.438                              # just below the patella, lateral to its ligament
# Shin scale for E36-E40: E35 level (knee joint line) -> lateral malleolus = 16 cun, so E38/E40
# sit exactly midway (Deadman) and E39 comes out level with VB35/VB36 (7 cun above the malleolus).
_SHIN_CUN = (_E35_Y - MALL_Y) / 16
_LOW_CUN = (NAVEL_Y - PUBIS_Y) / 5          # navel -> pubic symphysis = 5 cun (WHO)


def _abd(cun_from_navel):
    """2 cun lateral to the midline; above the navel trunk cun, below it navel->pubis = 5 cun."""
    step = CUN_T if cun_from_navel >= 0 else _LOW_CUN
    return front(2 * CUN_T, NAVEL_Y + cun_from_navel * step)


SPEC = {
    # Face: straight below the pupil, then mouth corner, jaw, in front of the ear
    "E1": face(_PUPIL_X, 1.532),
    "E2": face(_PUPIL_X, 1.519),
    "E3": face(_PUPIL_X, 1.501),
    "E4": face(0.030, 1.479),
    # E5 on the lower border of the mandible ~1.3 cun in front of the angle (angle ~ y 1.474, z -0.050)
    "E5": face(0.043, 1.461, -0.024, toward=(1.0, -0.35, 0.15)),
    "E6": face(0.050, 1.482, -0.045, toward=(1.0, 0.0, 0.1)),
    "E7": face(0.070, 1.525, -0.031, toward=(1.0, 0.0, 0.2)),
    "E8": sph(45, 45),
    # Neck: anterior border of the sternocleidomastoid, 1.5 cun lateral
    "E9": (np.array([0.033, 1.415, -0.075]), np.array([0.25, 0.0, 1.0])),
    "E10": (np.array([0.033, 1.385, -0.075]), np.array([0.2, 0.0, 1.0])),
    "E11": (np.array([0.033, 1.356, -0.075]), np.array([0.0, 0.1, 1.0])),
    "E12": (np.array([4 * CUN_T, 1.40, -0.050]), np.array([0.0, -1.0, 0.25])),
    # Chest: nipple line, 4 cun lateral
    "E13": front(4 * CUN_T, 1.336),
    "E14": front(4 * CUN_T, ics_front(1)),
    "E15": front(4 * CUN_T, ics_front(2)),
    "E16": front(4 * CUN_T, ics_front(3)),
    "E17": front(4 * CUN_T, ics_front(4)),
    "E18": front(4 * CUN_T, ics_front(5)),
    # Abdomen: 2 cun lateral
    "E19": _abd(6),
    "E20": _abd(5),
    "E21": _abd(4),
    "E22": _abd(3),
    "E23": _abd(2),
    "E24": _abd(1),
    "E25": _abd(0),
    "E26": _abd(-1),
    "E27": _abd(-2),
    "E28": _abd(-3),
    "E29": _abd(-4),
    "E30": _abd(-5),
    # Thigh
    "E31": thigh(0.770, 20),
    "E32": thigh(PATELLA_TOP_Y + 6 * CUN_THIGH, 23),
    "E33": thigh(PATELLA_TOP_Y + 3 * CUN_THIGH, 28),
    "E34": thigh(PATELLA_TOP_Y + 2 * CUN_THIGH, 30),
    # Knee and shin: one finger lateral to the tibial crest (the crest drifts from az ~15 to ~30)
    "E35": shin(_E35_Y, 30),
    "E36": shin(_E35_Y - 3 * _SHIN_CUN, 45),
    "E37": shin(_E35_Y - 6 * _SHIN_CUN, 48),
    "E38": shin(_E35_Y - 8 * _SHIN_CUN, 48),
    "E39": shin(_E35_Y - 9 * _SHIN_CUN, 50),
    # E40 level with E38, in front of the fibula (VB36 sits on its anterior border at az 72, lower)
    "E40": shin(_E35_Y - 8 * _SHIN_CUN, 72),
    # Ankle and foot
    "E41": (np.array([0.216, 0.104, 0.03]), np.array([0.0, 0.0, -1.0])),
    "E42": foot_top(0.214, -0.035),        # over the 2nd/3rd cuneiforms, highest part of the dorsum
    "E43": foot_top(0.222, 0.008),
    "E44": foot_top(0.222, 0.031),
    "E45": ((J["l-toe-2-3"] + J["l-toe-2-4"]) / 2, np.array([1.0, 0.6, 0.3])),
}

VIA = {
    # keep the face lines on the skin: over the cheek, along the masseter, up the temple
    "E4>E5": [face(0.047, 1.466, 0.000, toward=(0.75, -0.2, 0.65))],
    "E6>E7": [face(0.070, 1.503, -0.038, toward=(1.0, 0.0, 0.1))],
    "E7>E8": [sph(66, 14), sph(58, 30)],
    "E5>E9": [face(0.060, 1.437, -0.045, toward=(1.0, -0.2, 0.2))],
}

CHAINS = {
    "stomach": [
        ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"],
        ["E5"] + [f"E{i}" for i in range(9, 46)],
    ],
}
