"""Small helpers: read our own GLB back and cast rays against it."""
import json
import struct

import numpy as np


def load_glb_body(path):
    """Return (positions, triangles) of the first primitive (the skin)."""
    raw = open(path, "rb").read()
    jlen = struct.unpack_from("<I", raw, 12)[0]
    gltf = json.loads(raw[20:20 + jlen])
    bin_start = 20 + jlen + 8
    prim = gltf["meshes"][0]["primitives"][0]

    def read(acc_idx, dtype, width):
        acc = gltf["accessors"][acc_idx]
        view = gltf["bufferViews"][acc["bufferView"]]
        start = bin_start + view["byteOffset"]
        arr = np.frombuffer(raw[start:start + view["byteLength"]], dtype=dtype)
        return arr.reshape(-1, width) if width > 1 else arr

    pos = read(prim["attributes"]["POSITION"], np.float32, 3).astype(np.float64)
    idx_dtype = np.uint16 if gltf["accessors"][prim["indices"]]["componentType"] == 5123 else np.uint32
    tris = read(prim["indices"], idx_dtype, 1).astype(np.int64).reshape(-1, 3)
    return pos, tris


class RayCaster:
    def __init__(self, pos, tris):
        self.a = pos[tris[:, 0]]
        self.e1 = pos[tris[:, 1]] - self.a
        self.e2 = pos[tris[:, 2]] - self.a
        n = np.cross(self.e1, self.e2)
        self.n = n / np.linalg.norm(n, axis=1, keepdims=True)

    def first_hit(self, origin, direction):
        """Nearest intersection along the ray; returns (point, normal) or None."""
        hit = self.first_hit_full(origin, direction)
        return None if hit is None else (hit[0], hit[1])

    def first_hit_full(self, origin, direction):
        """Like first_hit, plus the triangle index and barycentric (u, v) of the hit.
        The triangle + barycentrics let a point follow the skin if the body shape is morphed."""
        d = np.asarray(direction, float)
        d = d / np.linalg.norm(d)
        o = np.asarray(origin, float)
        p = np.cross(d, self.e2)
        det = np.einsum("ij,ij->i", self.e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.zeros_like(det)
        inv[ok] = 1.0 / det[ok]
        t_vec = o - self.a
        u = np.einsum("ij,ij->i", t_vec, p) * inv
        q = np.cross(t_vec, self.e1)
        v = (q @ d) * inv
        t = np.einsum("ij,ij->i", self.e2, q) * inv
        mask = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
        if not mask.any():
            return None
        i = np.where(mask)[0][np.argmin(t[mask])]
        # MakeHuman winding faces outward, so the triangle normal is the skin normal
        # whether the ray started inside the body or outside it.
        return o + d * t[i], self.n[i], int(i), (float(u[i]), float(v[i]))
