"""Convert MakeHuman base.obj into a compact GLB plus joint landmarks.

Usage: python3 -I build_body.py <base.obj> <out_dir>
Writes <out_dir>/body.glb and <out_dir>/landmarks.json (meters, y up, feet at y=0).
"""
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

SCALE = 0.1  # MakeHuman units are decimeters
KEEP = {"body": "skin", "helper-l-eye": "eye", "helper-r-eye": "eye"}


def parse_obj(path):
    verts = []
    groups = defaultdict(list)
    current = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("g "):
                current = line.split(maxsplit=1)[1].strip()
            elif line.startswith("f "):
                idx = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
                groups[current].append(idx)
    return np.array(verts, dtype=np.float64), groups


def triangulate(faces):
    tris = []
    for f in faces:
        for i in range(1, len(f) - 1):
            tris.append((f[0], f[i], f[i + 1]))
    return np.array(tris, dtype=np.int64)


def vertex_normals(pos, tris):
    n = np.zeros_like(pos)
    a, b, c = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    length[length == 0] = 1
    return n / length


def compact(all_verts, tris):
    used = np.unique(tris)
    remap = -np.ones(len(all_verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return all_verts[used], remap[tris]


def write_glb(path, prims):
    """prims: list of (name, material_index, pos, nrm, tris)."""
    bin_parts = []
    buffer_views = []
    accessors = []
    meshes_prims = []
    offset = 0

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b"\0" * pad)
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        offset += len(data) + pad
        return len(buffer_views) - 1

    for name, mat, pos, nrm, tris in prims:
        p = pos.astype(np.float32)
        nm = nrm.astype(np.float32)
        idx_type, ctype = (np.uint16, 5123) if len(p) < 65535 else (np.uint32, 5125)
        idx = tris.astype(idx_type).reshape(-1)
        pv = add_view(p.tobytes(), 34962)
        nv = add_view(nm.tobytes(), 34962)
        iv = add_view(idx.tobytes(), 34963)
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(p), "type": "VEC3",
                          "min": p.min(axis=0).tolist(), "max": p.max(axis=0).tolist()})
        pa = len(accessors) - 1
        accessors.append({"bufferView": nv, "componentType": 5126, "count": len(nm), "type": "VEC3"})
        na = len(accessors) - 1
        accessors.append({"bufferView": iv, "componentType": ctype, "count": len(idx), "type": "SCALAR"})
        ia = len(accessors) - 1
        meshes_prims.append({"attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia, "material": mat})

    gltf = {
        "asset": {"version": "2.0", "generator": "build_body.py (MakeHuman hm08 base mesh, CC0)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "body"}],
        "meshes": [{"name": "body", "primitives": meshes_prims}],
        "materials": [
            {"name": "skin", "pbrMetallicRoughness": {"baseColorFactor": [0.86, 0.76, 0.68, 1], "metallicFactor": 0, "roughnessFactor": 0.8}},
            {"name": "eye", "pbrMetallicRoughness": {"baseColorFactor": [0.95, 0.95, 0.95, 1], "metallicFactor": 0, "roughnessFactor": 0.4}},
        ],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": offset}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binary = b"".join(bin_parts)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def main():
    src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    verts, groups = parse_obj(src)

    body_idx = np.unique(triangulate(groups["body"]))
    body = verts[body_idx]
    ground_y = body[:, 1].min()
    center = np.array([(body[:, 0].min() + body[:, 0].max()) / 2, ground_y, (body[:, 2].min() + body[:, 2].max()) / 2])
    world = (verts - center) * SCALE

    prims = []
    for gname, kind in KEEP.items():
        tris = triangulate(groups[gname])
        pos, ltris = compact(world, tris)
        prims.append((gname, 0 if kind == "skin" else 1, pos, vertex_normals(pos, ltris), ltris))
        print(f"{gname}: {len(pos)} verts, {len(ltris)} tris")
    write_glb(out_dir / "body.glb", prims)

    landmarks = {}
    for gname, faces in groups.items():
        if gname and gname.startswith("joint-"):
            ids = np.unique(np.concatenate([np.array(f) for f in faces]))
            landmarks[gname[6:]] = np.round(world[ids].mean(axis=0), 4).tolist()
    bmin, bmax = world[body_idx].min(axis=0), world[body_idx].max(axis=0)
    meta = {"bbox_min": bmin.round(4).tolist(), "bbox_max": bmax.round(4).tolist(), "joints": landmarks}
    (out_dir / "landmarks.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("bbox", meta["bbox_min"], meta["bbox_max"])
    for k in ["head", "neck", "l-clavicle", "l-shoulder", "l-elbow", "l-hand", "l-upperleg", "l-knee", "l-ankle", "ground"]:
        print(k, landmarks.get(k))
    print("joint names:", " ".join(sorted(landmarks)))
    print("glb bytes", (out_dir / "body.glb").stat().st_size)


if __name__ == "__main__":
    main()
