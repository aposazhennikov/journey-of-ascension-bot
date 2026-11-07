"""Shared landmarks, cun scales and ray helpers for placing points on the body.

Coordinates: meters, y up, +x = body's LEFT side, +z = front. Points are placed on the
left side only; the page mirrors x for the right side. Midline points use x = 0.

Every helper returns a ray (origin, direction). place_points.py casts it against the
skin and takes the first hit. Two kinds of rays:
  * inside-out: origin inside the right body part (bone axis, torso core, head centre),
    direction outward. Good for limbs and the trunk; never hits a neighbouring limb.
  * outside-in: origin a few cm outside the skin, direction inward. Use it for the face
    (rays from the head centre catch the mouth cavity) and for the top of the foot.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from meshlib import RayCaster, load_glb_body

ASSETS = Path(__file__).resolve().parents[2] / "webapp" / "assets"
POS, TRIS = load_glb_body(ASSETS / "body.glb")
J = {k: np.array(v) for k, v in json.loads((ASSETS / "landmarks.json").read_text())["joints"].items()}
RC = RayCaster(POS, TRIS)

# ---- proportional cun ----
NOTCH_Y, PUBIS_Y = 1.350, 0.868            # suprasternal notch, upper border of pubic symphysis
CUN_T = (NOTCH_Y - PUBIS_Y) / 22           # trunk: notch->pubis = 22 cun (~0.022 m)
NAVEL_Y = 0.998                            # the visible navel pit on the mesh
XIPHOID_Y = NAVEL_Y + 8 * CUN_T            # xiphisternal junction, 8 cun above the navel
PERINEUM = np.array([0.0, 0.775, -0.080])
TROCH_Y, KNEE_Y, MALL_Y = 0.820, 0.450, 0.065   # greater trochanter, popliteal crease, lateral malleolus tip
MED_MALL_Y = 0.080                               # medial malleolus tip
PATELLA_TOP_Y = 0.490
CUN_THIGH = (TROCH_Y - KNEE_Y) / 19        # trochanter->popliteal crease = 19 cun
CUN_LEG = (KNEE_Y - MALL_Y) / 16           # popliteal crease->lateral malleolus = 16 cun
TORSO_Z = -0.060
HEAD_C = np.array([0.0, 1.530, -0.050])

# Arm: axillary fold -> elbow crease = 9 cun, elbow crease -> wrist crease = 12 cun.
SHOULDER, ELBOW, WRIST = J["l-shoulder"], J["l-elbow"], J["l-hand"]
AXILLA_T = 0.25                            # anterior axillary fold, as a fraction shoulder->elbow
CUN_UPPER_ARM = np.linalg.norm(ELBOW - SHOULDER) * (1 - AXILLA_T) / 9
CUN_FOREARM = np.linalg.norm(WRIST - ELBOW) / 12

# Spinous process levels (y) on the back. C7 at the base of the neck, L4 at the iliac crests.
_VERT_STEP = 0.0266
VERT = {"C7": 1.400}
for _k in range(1, 13):
    VERT[f"T{_k}"] = 1.400 - _VERT_STEP * _k
for _k in range(1, 6):
    VERT[f"L{_k}"] = VERT["T12"] - _VERT_STEP * _k
for _k in range(1, 5):
    VERT[f"S{_k}"] = VERT["L5"] - 0.030 - 0.022 * (_k - 1)   # sacral foramina levels; S1 sits a full step below L5
VERT["coccyx"] = 0.835


def ics_front(k):
    """Anterior level (y) of the k-th intercostal space; the nipple sits in the 4th."""
    return NOTCH_Y - 0.0365 * k + 0.005


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def az_dir(az_deg, up=0.0):
    """Horizontal direction by azimuth: 0 = front (+z), 90 = left/lateral (+x), 180 = back, -90 = medial."""
    a = math.radians(az_deg)
    return np.array([math.sin(a), up, math.cos(a)])


def on_segment(a, b, y):
    """Point on segment a-b at height y."""
    t = (y - a[1]) / (b[1] - a[1])
    return a + (b - a) * t


# ---- rays ----

def limb(a, b, y, az, up=0.0):
    """Leg: origin on the bone axis between joints a and b at height y; direction by azimuth
    (0 front, 90 lateral, -90 medial, 180 back) made perpendicular to the bone."""
    origin = on_segment(J[a], J[b], y)
    axis = unit(J[b] - J[a])
    d = az_dir(az, up)
    if up == 0:
        d = d - axis * (d @ axis)
    return origin, d


def thigh(y, az, up=0.0):
    return limb("l-upper-leg", "l-knee", y, az, up)


def shin(y, az, up=0.0):
    return limb("l-knee", "l-ankle", y, az, up)


@lru_cache(maxsize=None)
def core_z(y):
    """Middle of the trunk depth at height y (between front and back skin on the midline)."""
    f = RC.first_hit(np.array([0.0, y, TORSO_Z]), np.array([0.0, 0.0, 1.0]))
    b = RC.first_hit(np.array([0.0, y, TORSO_Z]), np.array([0.0, 0.0, -1.0]))
    if f is None or b is None:
        return TORSO_Z
    return float((f[0][2] + b[0][2]) / 2)


def torso(y, az, x=0.0, z=None, up=0.0):
    """Trunk: origin inside the trunk at (x, y, core), direction by azimuth."""
    return np.array([x, y, core_z(round(y, 4)) if z is None else z]), az_dir(az, up)


def front(x, y, up=0.0, lat=0.0):
    """Front of the trunk at lateral offset x: origin in the trunk core, ray forward."""
    return np.array([x, y, core_z(round(y, 4))]), np.array([lat, up, 1.0])


def back(x, y, up=0.0, lat=0.0):
    """Back of the trunk at lateral offset x: origin in the trunk core, ray backward."""
    return np.array([x, y, core_z(round(y, 4))]), np.array([lat, up, -1.0])


def from_outside(target, direction, dist=0.25):
    """Outside-in ray that lands near `target`: starts `dist` along `direction` from it and
    travels back toward it. `direction` is the outward normal you expect at the target."""
    d = unit(direction)
    return np.asarray(target, float) + d * dist, -d


def face(x, y, z_hint=0.0, toward=(0.0, 0.0, 1.0)):
    """Face/front of the head, outside-in, landing at (x, y). `toward` is the outward normal."""
    return from_outside(np.array([x, y, z_hint]), toward, dist=0.30)


def head(dx, dy, dz):
    """Inside-out from the head centre. Fine for the scalp and the sides of the head."""
    return HEAD_C, np.array([dx, dy, dz])


def sph(az, el):
    """Head direction by azimuth (0 front, 90 lateral, 180 back) and elevation (90 = vertex)."""
    a, e = math.radians(az), math.radians(el)
    return head(math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e))


def aim(x, y, z):
    """Inside-out from the head centre toward a target point on the scalp."""
    return HEAD_C, np.array([x, y, z]) - HEAD_C


def foot_top(x, z):
    """Dorsum of the foot at (x, z): outside-in from above."""
    return np.array([x, 0.15, z]), np.array([0.0, -1.0, 0.0])


def sole(x, z):
    """Sole of the foot at (x, z): outside-in from below the floor."""
    return np.array([x, -0.10, z]), np.array([0.0, 1.0, 0.0])


# ---- arm ----
# The model stands in an A-pose with palms turned down/back and the thumb side forward.
# Arm rays use a frame tied to the bones, so anatomical terms work regardless of pose:
#   theta = 0 palmar (flexor) midline, +90 radial (thumb side), -90 ulnar (little-finger
#   side), 180 dorsal (extensor) midline. Lung ~ +45, pericardium 0, heart ~ -45,
#   large intestine ~ +135, triple burner 180, small intestine ~ -135.

def _arm_frame(a, b):
    """axis points distally; for the left arm palmar = axis x radial (anatomical position:
    axis down, radial lateral -> palmar forward)."""
    axis = unit(b - a)
    radial = J["l-finger-1-2"] - J["l-finger-5-2"]
    radial = unit(radial - axis * (radial @ axis))
    palmar = unit(np.cross(axis, radial))
    return axis, palmar, radial


def _arm_dir(a, b, theta):
    _, palmar, radial = _arm_frame(a, b)
    t = math.radians(theta)
    return palmar * math.cos(t) + radial * math.sin(t)


def upper_arm(cun_above_elbow, theta):
    """Upper arm: `cun_above_elbow` measured from the elbow crease (9 cun to the axillary fold)."""
    length = np.linalg.norm(ELBOW - SHOULDER)
    t = 1 - (cun_above_elbow * CUN_UPPER_ARM) / length
    return SHOULDER + (ELBOW - SHOULDER) * t, _arm_dir(SHOULDER, ELBOW, theta)


def forearm(cun_above_wrist, theta):
    """Forearm: `cun_above_wrist` measured from the wrist crease (12 cun to the elbow crease)."""
    length = np.linalg.norm(WRIST - ELBOW)
    t = 1 - (cun_above_wrist * CUN_FOREARM) / length
    return ELBOW + (WRIST - ELBOW) * t, _arm_dir(ELBOW, WRIST, theta)


def hand(origin, theta, along=0.0):
    """Hand/finger ray from an inside point (e.g. a finger joint J['l-finger-2-3']).
    `along` tilts the ray toward the fingertips (+) or the wrist (-)."""
    d = _arm_dir(ELBOW, WRIST, theta) + unit(J["l-finger-3-4"] - WRIST) * along
    return np.asarray(origin, float), d


def lerp(a, b, t):
    return np.asarray(a, float) + (np.asarray(b, float) - np.asarray(a, float)) * t
