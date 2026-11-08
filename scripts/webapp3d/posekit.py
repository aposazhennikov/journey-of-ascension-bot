"""Shared helpers for the rig / pose tools: GLB reading, quaternions, FK, LBS, PIL rendering.

Conventions (same as webapp/pose.js):
  quaternions are [x, y, z, w];
  every bone's rest frame is aligned with the world axes (+x body's left, +y up, +z front),
  a pose stores for each bone a LOCAL rotation q_b relative to rest, applied about the bone's
  head in the parent's (posed) frame:
      Q_b = Q_parent * q_b
      H_b = H_parent + Q_parent * (head_b - head_parent)      (root: H = head + rootOffset)
      v'  = sum_i w_i * (H_i + Q_i * (v - head_i))
"""
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "webapp" / "assets"
GLB = {"neutral": ASSETS / "body.glb", "female": ASSETS / "body_female.glb", "male": ASSETS / "body_male.glb"}


# ---------------------------------------------------------------- GLB
def load_glb(path):
    """Return list of (positions float64 (n,3), triangles int64 (m,3)) for all primitives."""
    raw = open(path, "rb").read()
    jlen = struct.unpack_from("<I", raw, 12)[0]
    gltf = json.loads(raw[20:20 + jlen])
    bin_start = 20 + jlen + 8

    def read(acc_idx, dtype, width):
        acc = gltf["accessors"][acc_idx]
        view = gltf["bufferViews"][acc["bufferView"]]
        start = bin_start + view["byteOffset"]
        arr = np.frombuffer(raw[start:start + view["byteLength"]], dtype=dtype)
        return arr.reshape(-1, width) if width > 1 else arr

    out = []
    for prim in gltf["meshes"][0]["primitives"]:
        pos = read(prim["attributes"]["POSITION"], np.float32, 3).astype(np.float64)
        idt = np.uint16 if gltf["accessors"][prim["indices"]]["componentType"] == 5123 else np.uint32
        out.append((pos, read(prim["indices"], idt, 1).astype(np.int64).reshape(-1, 3)))
    return out


# ---------------------------------------------------------------- quaternions
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def qconj(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def qaxis(axis, deg):
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    h = np.radians(deg) / 2
    return np.array([*(axis * np.sin(h)), np.cos(h)])


def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_q(m):
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = np.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def qrot(q, v):
    return np.asarray(v) @ qmat(q).T


def qmirror(q):
    """Mirror a rotation through the x=0 plane (left <-> right)."""
    return np.array([q[0], -q[1], -q[2], q[3]])


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def frame_rot(a0, h0, a1, h1):
    """Rotation taking axis a0 -> a1 and (orthogonalised) secondary h0 -> h1, as a quaternion."""
    def basis(a, h):
        a = unit(a)
        h = unit(np.asarray(h, float) - a * (np.dot(a, h)))
        return np.stack([a, h, np.cross(a, h)], axis=1)
    return mat_q(basis(a1, h1) @ basis(a0, h0).T)


def swing(a0, a1):
    """Minimal rotation taking a0 to a1."""
    a0, a1 = unit(a0), unit(a1)
    c = np.cross(a0, a1)
    s = np.linalg.norm(c)
    if s < 1e-9:
        return np.array([0, 0, 0, 1.0])
    return qaxis(c, np.degrees(np.arctan2(s, np.dot(a0, a1))))


# ---------------------------------------------------------------- rig
class Rig:
    def __init__(self, path=ASSETS / "rig.json"):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.data = d
        self.names = [b["name"] for b in d["bones"]]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parent = np.array([b["parent"] for b in d["bones"]])
        self.heads = {v: np.array([b["head"][v] for b in d["bones"]]) for v in d["variants"]}
        self.tails = {v: np.array([b["tail"][v] for b in d["bones"]]) for v in d["variants"]}
        n = d["influences"]
        self.joints = np.array(d["joints"], dtype=np.int64).reshape(-1, n)
        self.weights = np.array(d["weights"], dtype=np.float64).reshape(-1, n) / d["weightScale"]
        self.eye_bone = d["eyeBone"]

    def fk(self, variant, local, root=(0, 0, 0)):
        """local: {bone: quat}. Returns world quats (N,4), world heads (N,3)."""
        heads = self.heads[variant]
        N = len(self.names)
        Q = np.zeros((N, 4))
        H = np.zeros((N, 3))
        for i in range(N):
            q = np.asarray(local.get(self.names[i], (0, 0, 0, 1.0)), float)
            p = self.parent[i]
            if p < 0:
                Q[i] = q
                H[i] = heads[i] + np.asarray(root, float)
            else:
                Q[i] = qmul(Q[p], q)
                H[i] = H[p] + qrot(Q[p], heads[i] - heads[p])
        return Q, H

    def skin(self, rest, variant, Q, H, method="dqs", idx=None):
        """Skin the rest vertices. method='dqs' (dual quaternion, default; keeps volume at the hips
        in the lotus poses, same as webapp/pose.js) or 'lbs' (linear blend). idx: only these vertices."""
        if idx is not None:
            full = (self.joints, self.weights)
            self.joints, self.weights = self.joints[idx], self.weights[idx]
            try:
                return self.skin(rest[idx], variant, Q, H, method)
            finally:
                self.joints, self.weights = full
        heads = self.heads[variant]
        mats = np.stack([qmat(q) for q in Q])           # (N,3,3)
        trans = H - np.einsum("nij,nj->ni", mats, heads)  # (N,3)
        if method == "lbs":
            out = np.zeros_like(rest)
            for k in range(self.joints.shape[1]):
                j = self.joints[:, k]
                w = self.weights[:, k:k + 1]
                out += w * (np.einsum("vij,vj->vi", mats[j], rest) + trans[j])
            return out
        # dual part of each bone: qd = 0.5 * (t, 0) * q
        Qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)
        D = 0.5 * np.stack([qmul(np.array([*t, 0.0]), q) for t, q in zip(trans, Qn)])
        piv = Qn[self.joints[:, 0]]
        b0 = np.zeros((len(rest), 4))
        be = np.zeros((len(rest), 4))
        for k in range(self.joints.shape[1]):
            j = self.joints[:, k]
            w = self.weights[:, k:k + 1]
            sg = np.where(np.sum(Qn[j] * piv, axis=1, keepdims=True) < 0, -1.0, 1.0)
            b0 += w * sg * Qn[j]
            be += w * sg * D[j]
        ln = np.linalg.norm(b0, axis=1, keepdims=True)
        c0, ce = b0 / ln, be / ln
        r, w0 = c0[:, :3], c0[:, 3:4]
        re, we = ce[:, :3], ce[:, 3:4]
        out = rest + 2 * np.cross(r, np.cross(r, rest) + w0 * rest)
        out += 2 * (w0 * re - we * r + np.cross(r, re))
        return out

    def rigid(self, rest, bone, Q, H, variant):
        i = self.index[bone] if isinstance(bone, str) else bone
        return (rest - self.heads[variant][i]) @ qmat(Q[i]).T + H[i]


# ---------------------------------------------------------------- points
def load_points(path=ASSETS / "points3d.json", rest_pos=None, tris=None):
    """Return list of (code, tri, bary) for both sides. Uses stored tri/bary when present,
    otherwise projects "p" (and its x-mirror) onto the nearest triangle of rest_pos/tris."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    cent = rest_pos[tris].mean(axis=1) if rest_pos is not None else None
    for code, e in d.get("points", {}).items():
        if "tri" in e and "bary" in e:
            out.append((code, int(e["tri"]), np.array(e["bary"], float)))
        if rest_pos is None:
            continue
        p = np.array(e["p"], float)
        sides = [p * [-1, 1, 1]] if "tri" in e else [p, p * [-1, 1, 1]]
        if abs(p[0]) < 0.004:
            sides = sides[:1]
        for q in sides:
            cand = np.argsort(np.linalg.norm(cent - q, axis=1))[:12]
            best = None
            for t in cand:
                bary, dist = closest_bary(q, rest_pos[tris[t]])
                if best is None or dist < best[2]:
                    best = (t, bary, dist)
            out.append((code + ("'" if q[0] * p[0] < 0 else ""), int(best[0]), best[1]))
    return out


def closest_bary(p, tri):
    a, b, c = tri
    e1, e2 = b - a, c - a
    n = np.cross(e1, e2)
    n /= np.linalg.norm(n)
    q = p - n * np.dot(p - a, n)
    m = np.array([[e1 @ e1, e1 @ e2], [e1 @ e2, e2 @ e2]])
    u, v = np.linalg.solve(m, [e1 @ (q - a), e2 @ (q - a)])
    u, v = max(u, 0), max(v, 0)
    s = u + v
    if s > 1:
        u, v = u / s, v / s
    bary = np.array([1 - u - v, u, v])
    return bary, np.linalg.norm(bary @ tri - p)


def point_on_mesh(pos, tris, tri, bary):
    return bary @ pos[tris[tri]]


# ---------------------------------------------------------------- render
VIEWS = {
    "front": ((0, 0, 1), (0, 1, 0)), "back": ((0, 0, -1), (0, 1, 0)),
    "left": ((1, 0, 0), (0, 1, 0)), "right": ((-1, 0, 0), (0, 1, 0)),
    "top": ((0, 1, 0), (0, 0, -1)), "below": ((0, -1, 0), (0, 0, 1)),
}


def view_basis(view):
    if isinstance(view, str):
        v, up = VIEWS[view]
    else:
        v, up = view
    v = unit(v)
    up = unit(np.asarray(up, float) - v * np.dot(up, v))
    return v, up, np.cross(up, v)


def render(meshes, view, out, size=800, bbox=None, points=(), title=None, grid_y0=True):
    """meshes: list of (pos, tris, rgb). points: list of (xyz, rgb, visible_bool)."""
    from PIL import Image, ImageDraw, ImageFont
    v, up, right = view_basis(view)
    allp = np.concatenate([m[0] for m in meshes])
    if bbox is None:
        lo, hi = allp.min(axis=0), allp.max(axis=0)
    else:
        lo, hi = (np.asarray(x, float) for x in bbox)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    sx, sy = corners @ right, corners @ up
    w, h = sx.max() - sx.min(), sy.max() - sy.min()
    scale = (size - 40) / max(w, h)
    W, Hh = int(w * scale) + 40, int(h * scale) + 40

    def px(p):
        p = np.atleast_2d(p)
        return np.stack([20 + (p @ right - sx.min()) * scale, 20 + (sy.max() - p @ up) * scale], axis=1)

    img = Image.new("RGB", (W, Hh), (246, 243, 238))
    draw = ImageDraw.Draw(img)
    if grid_y0:
        y0 = px(np.array([[lo[0], 0, lo[2]], [hi[0], 0, hi[2]]]))
        if abs(up[1]) > 0.5:
            draw.line([(0, y0[0, 1]), (W, y0[0, 1])], fill=(180, 170, 160), width=1)
    light = unit(v + up * 0.6 + right * 0.3)
    polys, depth, cols = [], [], []
    for pos, tris, rgb in meshes:
        tp = pos[tris]
        nrm = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
        ln = np.linalg.norm(nrm, axis=1, keepdims=True)
        ln[ln == 0] = 1
        nrm /= ln
        facing = nrm @ v
        keep = facing > 0
        if bbox is not None:
            c = tp.mean(axis=1)
            keep &= np.all((c > lo - 0.03) & (c < hi + 0.03), axis=1)
        tp, nrm = tp[keep], nrm[keep]
        shade = 0.42 + 0.58 * np.clip(nrm @ light, 0, 1)
        polys.append(tp)
        depth.append(tp.mean(axis=1) @ v)
        cols.append(shade[:, None] * np.array(rgb)[None, :])
    tp = np.concatenate(polys)
    dp = np.concatenate(depth)
    cl = np.concatenate(cols).astype(int)
    p2 = px(tp.reshape(-1, 3)).reshape(-1, 3, 2)
    for i in np.argsort(dp):
        draw.polygon([tuple(x) for x in p2[i]], fill=tuple(cl[i]))
    for xyz, rgb, vis in points:
        if bbox is not None and not np.all((xyz > lo - 0.005) & (xyz < hi + 0.005)):
            continue
        x, y = px(xyz)[0]
        r = 3
        if vis:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=rgb, outline=(30, 30, 30))
        else:
            draw.ellipse([x - r, y - r, x + r, y + r], outline=rgb, width=1)
    if title:
        draw.text((8, 4), title, fill=(20, 20, 20), font=ImageFont.load_default())
    img.save(out)
    return out
