"""Anatomical joint angles -> world bone rotations for the MakeHuman default rig.

All angles are in degrees, positive = flexion / abduction / external rotation / dorsiflexion /
inversion / supination / wrist flexion / radial deviation, the same convention for both sides.
They are measured from a "neutral" frame N that is not the rest pose of the rig:

  leg  N: thigh and shin straight down, knee hinge = +x, foot pointing straight forward, sole down;
  arm  N: arm hanging straight down, elbow straight, thumb forward (palm facing the thigh),
          elbow hinge such that flexion brings the forearm forward, hand in line with the forearm.

World rotation of a bone = Q_parent_segment * A(angles) * R0, where R0 takes the rest bone to N.
Twist about the long axis is spread over the two bones of a segment (upperleg01 50 %, upperarm01
40 %, lowerarm01 50 %, the second bone 100 %) and the wrist gets none: a single joint turning more
than ~60 deg about its own axis twists the skin like a candy wrapper.
"""
import numpy as np

from posekit import frame_rot, qaxis, qconj, qmul, qrot, swing, unit

X, Y, Z = np.eye(3)
ID = np.array([0, 0, 0, 1.0])
SIDES = {"L": 1.0, "R": -1.0}

TWIST_SHARE = {"upperleg01": 0.5, "upperarm01": 0.4, "lowerarm01": 0.5}


def twist_angle(q, axis):
    """Signed twist (deg) of rotation q about `axis` (swing-twist decomposition)."""
    axis = unit(axis)
    v = np.asarray(q[:3], float)
    p = np.dot(v, axis) * axis
    t = np.array([*p, q[3]])
    n = np.linalg.norm(t)
    if n < 1e-9:
        return 180.0
    t /= n
    ang = 2 * np.degrees(np.arctan2(np.dot(t[:3], axis), t[3]))
    return (ang + 180) % 360 - 180


def split_twist(Q, axis_world_rest, share):
    """Q = swing * twist(axis in the rest frame); return swing * twist * share."""
    a1 = qrot(Q, axis_world_rest)
    sw = swing(axis_world_rest, a1)
    tw = qmul(qconj(sw), Q)
    ang = twist_angle(tw, axis_world_rest)
    return qmul(sw, qaxis(axis_world_rest, ang * share))


class Anatomy:
    """Rest-frame data of one body variant."""

    def __init__(self, ps):
        self.ps = ps
        P = ps.P
        self.R0 = {}
        self.axes = {}
        for s, sg in SIDES.items():
            hip, knee, ank = P(f"upperleg01.{s}"), P(f"lowerleg01.{s}"), P(f"foot.{s}")
            a0, s0 = unit(knee - hip), unit(ank - knee)
            self.axes[f"thigh.{s}"], self.axes[f"shin.{s}"] = a0, s0
            self.R0[f"thigh.{s}"] = frame_rot(a0, X, -Y, X)
            self.R0[f"shin.{s}"] = frame_rot(s0, X, -Y, X)
            f0 = unit([sg * 0.12, 0, 1])
            self.R0[f"foot.{s}"] = frame_rot(f0, -Y, Z, -Y)
            sh, el, wr = P(f"upperarm01.{s}"), P(f"lowerarm01.{s}"), P(f"wrist.{s}")
            u0, f0a = unit(el - sh), unit(wr - el)
            h0 = unit(np.cross(u0, f0a))
            self.axes[f"upper.{s}"], self.axes[f"fore.{s}"] = u0, f0a
            self.R0[f"upper.{s}"] = frame_rot(u0, h0, -Y, -X)
            self.R0[f"fore.{s}"] = frame_rot(f0a, h0, -Y, -X)
            d0, n0 = ps.hand_frame0(s)
            self.hand_axis = getattr(self, "hand_axis", {})
            self.hand_axis[s] = unit(P(f"finger3-1.{s}") - P(f"wrist.{s}"))
            self.R0[f"hand.{s}"] = frame_rot(d0, n0, -Y, np.array([-sg, 0, 0]))
            # rest pronation of the hand relative to the elbow-hinge frame of the forearm, in N
            n_n = qrot(self.R0[f"fore.{s}"], n0)
            n_n = unit(n_n - np.dot(n_n, Y) * Y)
            neutral = np.array([-sg, 0, 0])
            ang = np.degrees(np.arctan2(np.dot(np.cross(neutral, n_n), Y), np.dot(neutral, n_n)))
            self.rest_pron = getattr(self, "rest_pron", {})
            self.rest_pron[s] = ang          # palm angle about +y in N at rest

    # ---------------------------------------------------------------- legs
    def leg(self, s, hip=(0, 0, 0), knee=0.0, ankle=(0, 0), tibia=0.0, Qp=ID):
        """World rotations of the leg bones. hip = (flexion, abduction, external rotation)."""
        sg = SIDES[s]
        flex, abd, rot = hip
        A_thigh = qmul(qaxis(X, -flex), qmul(qaxis(Z, sg * abd), qaxis(Y, sg * rot)))
        Wt = qmul(Qp, qmul(A_thigh, self.R0[f"thigh.{s}"]))
        a0 = self.axes[f"thigh.{s}"]
        W1 = split_twist(Wt, a0, TWIST_SHARE["upperleg01"])
        A_shin = qmul(A_thigh, qmul(qaxis(X, knee), qaxis(Y, sg * tibia)))
        Ws = qmul(Qp, qmul(A_shin, self.R0[f"shin.{s}"]))
        dorsi, inv = ankle
        A_foot = qmul(A_shin, qmul(qaxis(X, -dorsi), qaxis(Z, -sg * inv)))
        Wf = qmul(Qp, qmul(A_foot, self.R0[f"foot.{s}"]))
        return {f"upperleg01.{s}": W1, f"upperleg02.{s}": Wt, f"lowerleg01.{s}": Ws, f"lowerleg02.{s}": Ws, f"foot.{s}": Wf}

    # ---------------------------------------------------------------- arms
    def arm(self, s, shoulder=(0, 0, 0), elbow=0.0, sup=0.0, wrist=(0, 0), Qp=ID):
        """World rotations of the arm bones. shoulder = (flexion, abduction, external rotation);
        sup = forearm supination (+) / pronation (-) from thumb-forward; wrist = (flexion, radial dev)."""
        sg = SIDES[s]
        flex, abd, rot = shoulder
        A_up = qmul(qaxis(X, -flex), qmul(qaxis(Z, sg * abd), qaxis(Y, sg * rot)))
        Wu = qmul(Qp, qmul(A_up, self.R0[f"upper.{s}"]))
        W1 = split_twist(Wu, self.axes[f"upper.{s}"], TWIST_SHARE["upperarm01"])
        A_el = qmul(A_up, qaxis(X, -elbow))
        # forearm twist about its own axis (+y in N), from the rest pronation to the requested one
        tw = sg * sup - self.rest_pron[s]
        tw = (tw + 180) % 360 - 180
        Wf1 = qmul(Qp, qmul(A_el, qmul(qaxis(Y, tw * TWIST_SHARE["lowerarm01"]), self.R0[f"fore.{s}"])))
        Wf2 = qmul(Qp, qmul(A_el, qmul(qaxis(Y, tw), self.R0[f"fore.{s}"])))
        wf, dev = wrist
        A_hand = qmul(A_el, qmul(qaxis(Y, sg * sup), qmul(qaxis(Z, -sg * wf), qaxis(X, -dev))))
        Wh = qmul(Qp, qmul(A_hand, self.R0[f"hand.{s}"]))
        # the wrist must not twist: drop whatever twist about the hand axis is left relative to the forearm
        rel = qmul(qconj(Wf2), Wh)
        Wh = qmul(Wf2, split_twist(rel, self.hand_axis[s], 0.0))
        return {f"upperarm01.{s}": W1, f"upperarm02.{s}": Wu, f"lowerarm01.{s}": Wf1, f"lowerarm02.{s}": Wf2, f"wrist.{s}": Wh}

    def wrist_twist(self, W, s):
        """Twist (deg) between lowerarm02 and the hand about the forearm axis: should be ~0."""
        rel = qmul(qconj(W[f"lowerarm02.{s}"]), W[f"wrist.{s}"])
        return twist_angle(rel, self.axes[f"fore.{s}"])
