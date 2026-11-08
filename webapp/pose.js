// CPU dual-quaternion skinning for the meridian body (MakeHuman default rig, see assets/rig.json)
// and named poses (assets/poses.json): asanas (body) + mudras (hands).
//
// Rotation convention (same as scripts/webapp3d/posekit.py): every bone's rest frame is aligned
// with the world axes (+x body's left, +y up, +z front). A pose gives each bone a LOCAL rotation
// q (quaternion [x, y, z, w]) relative to rest, applied about the bone head in the parent's
// posed frame:  Q_b = Q_parent * q_b,  H_b = H_parent + Q_parent * (head_b - head_parent),
// and a skin vertex is moved by the weighted dual-quaternion blend of the bone transforms
// (v -> H_i + Q_i * (v - head_i)), as posekit.Rig.skin(method='dqs') does.  The root also gets the
// pose's root offset (metres), which lowers the pelvis to the floor in seated poses.
//
// Usage: see the comment at the end of the file.
import * as THREE from 'three';

const IDQ = [0, 0, 0, 1];

export async function loadRig(url, posesUrl = url.replace(/rig\.json(\?.*)?$/, 'poses.json')) {
  const [r, poses] = await Promise.all([
    fetch(url).then((res) => res.json()),
    posesUrl ? fetch(posesUrl).then((res) => res.json()) : Promise.resolve(null),
  ]);
  const n = r.bones.length;
  const rig = {
    names: r.bones.map((b) => b.name),
    index: Object.fromEntries(r.bones.map((b, i) => [b.name, i])),
    parent: Int16Array.from(r.bones.map((b) => b.parent)),
    heads: {},
    variants: r.variants,
    vertexCount: r.vertexCount,
    influences: r.influences,
    joints: Uint8Array.from(r.joints),
    weights: Float32Array.from(r.weights, (w) => w / r.weightScale),
    eyeBone: r.eyeBone,
    poses,
  };
  for (const v of r.variants) {
    const h = new Float32Array(n * 3);
    r.bones.forEach((b, i) => h.set(b.head[v], i * 3));
    rig.heads[v] = h;
  }
  return rig;
}

export async function loadPoses(url) {
  return fetch(url).then((res) => res.json());
}

// ---------------------------------------------------------------- quaternion helpers (flat arrays)
function qmulTo(o, oi, a, ai, b, bi) {
  const ax = a[ai], ay = a[ai + 1], az = a[ai + 2], aw = a[ai + 3];
  const bx = b[bi], by = b[bi + 1], bz = b[bi + 2], bw = b[bi + 3];
  o[oi] = aw * bx + ax * bw + ay * bz - az * by;
  o[oi + 1] = aw * by - ax * bz + ay * bw + az * bx;
  o[oi + 2] = aw * bz + ax * by - ay * bx + az * bw;
  o[oi + 3] = aw * bw - ax * bx - ay * by - az * bz;
}

function slerpTo(o, oi, a, b, i, t) {
  let bx = b[i], by = b[i + 1], bz = b[i + 2], bw = b[i + 3];
  const ax = a[i], ay = a[i + 1], az = a[i + 2], aw = a[i + 3];
  let d = ax * bx + ay * by + az * bz + aw * bw;
  if (d < 0) { d = -d; bx = -bx; by = -by; bz = -bz; bw = -bw; }
  let s0 = 1 - t, s1 = t;
  if (d < 0.9995) {
    const th = Math.acos(d), sn = Math.sin(th);
    s0 = Math.sin((1 - t) * th) / sn;
    s1 = Math.sin(t * th) / sn;
  }
  let x = s0 * ax + s1 * bx, y = s0 * ay + s1 * by, z = s0 * az + s1 * bz, w = s0 * aw + s1 * bw;
  const l = Math.hypot(x, y, z, w) || 1;
  o[oi] = x / l; o[oi + 1] = y / l; o[oi + 2] = z / l; o[oi + 3] = w / l;
}

// rotation matrix (row-major 3x3) of quaternion q[qi..] into m[mi..mi+8]
function qmat(m, mi, q, qi) {
  const x = q[qi], y = q[qi + 1], z = q[qi + 2], w = q[qi + 3];
  m[mi] = 1 - 2 * (y * y + z * z); m[mi + 1] = 2 * (x * y - z * w); m[mi + 2] = 2 * (x * z + y * w);
  m[mi + 3] = 2 * (x * y + z * w); m[mi + 4] = 1 - 2 * (x * x + z * z); m[mi + 5] = 2 * (y * z - x * w);
  m[mi + 6] = 2 * (x * z - y * w); m[mi + 7] = 2 * (y * z + x * w); m[mi + 8] = 1 - 2 * (x * x + y * y);
}

/** Local rotations (Float32Array n*4) and root offset for a body pose + hand pose (ids or objects). */
export function composePose(rig, variant, bodyPose, handPose) {
  const poses = rig.poses;
  const n = rig.names.length;
  const local = new Float32Array(n * 4);
  for (let i = 0; i < n; i++) local[i * 4 + 3] = 1;
  const body = typeof bodyPose === 'string' ? poses.body[bodyPose] : bodyPose;
  const hand = typeof handPose === 'string' ? poses.hand[handPose] : handPose;
  if (!body) throw new Error(`unknown body pose ${bodyPose}`);
  const put = (name, q) => {
    const i = rig.index[name];
    if (i !== undefined) local.set(q, i * 4);
  };
  const pick = (obj) => (obj ? obj[variant] || obj.neutral || {} : {});
  for (const [k, q] of Object.entries(pick(body.rot))) put(k, q);
  if (hand) {
    // a mudra without its own arm pose: the seated pose's "palm up, back of the wrist on the knee" arms
    const isMudra = typeof handPose === 'string' ? handPose !== 'open' : true;
    if (!hand.arms && isMudra) for (const [k, q] of Object.entries(pick(body.mudraArms))) put(k, q);
    for (const [k, q] of Object.entries(pick(hand.arms))) put(k, q);
    // the open hand of the lotus is dhyana: the pose's own fingers (thumb tips touching)
    const own = !isMudra ? pick(body.openRot) : {};
    const fingers = Object.keys(own).length ? own : pick(hand.rot);
    for (const [k, q] of Object.entries(fingers)) {
      put(k, q);
      put(k.replace(/\.L$/, '.R'), [q[0], -q[1], -q[2], q[3]]); // mirror through x = 0
    }
  }
  const root = (body.root && (body.root[variant] || body.root.neutral)) || [0, 0, 0];
  return { local, root: Float32Array.from(root) };
}

/**
 * rig: from loadRig; restPositions: Float32Array of the skin primitive (primitive 0) of the glb for
 * `variant` ('neutral' | 'female' | 'male'). The array is copied, so the page may reuse the
 * geometry's own position array as output.
 */
export function createSkinner(rig, restPositions, variant = 'neutral') {
  if (!rig.heads[variant]) throw new Error(`unknown variant ${variant}`);
  const n = rig.names.length;
  const nv = restPositions.length / 3;
  if (nv !== rig.vertexCount) throw new Error(`vertex count ${nv} != rig ${rig.vertexCount}`);
  const rest = Float32Array.from(restPositions);
  const positions = Float32Array.from(restPositions);
  const heads = rig.heads[variant];
  const parent = rig.parent;
  const J = rig.joints, Wt = rig.weights, K = rig.influences;

  const from = new Float32Array(n * 4), to = new Float32Array(n * 4), cur = new Float32Array(n * 4);
  for (let i = 0; i < n; i++) { from[i * 4 + 3] = 1; to[i * 4 + 3] = 1; cur[i * 4 + 3] = 1; }
  const fromRoot = new Float32Array(3), toRoot = new Float32Array(3), curRoot = new Float32Array(3);
  const Qw = new Float32Array(n * 4), Hw = new Float32Array(n * 3);
  const M = new Float32Array(n * 12); // per bone: 3x3 rotation (row-major) + translation
  const DQ = new Float32Array(n * 8); // per bone: dual quaternion (real xyzw, dual xyzw)
  let targetKey = 'stand|open';
  let lastT = 1;

  function forward() {
    for (let i = 0; i < n; i++) {
      const p = parent[i];
      const qi = i * 4, hi = i * 3;
      if (p < 0) {
        Qw.set(cur.subarray(qi, qi + 4), qi);
        Hw[hi] = heads[hi] + curRoot[0];
        Hw[hi + 1] = heads[hi + 1] + curRoot[1];
        Hw[hi + 2] = heads[hi + 2] + curRoot[2];
      } else {
        qmulTo(Qw, qi, Qw, p * 4, cur, qi);
        const m = M, mp = p * 12;
        const dx = heads[hi] - heads[p * 3], dy = heads[hi + 1] - heads[p * 3 + 1], dz = heads[hi + 2] - heads[p * 3 + 2];
        Hw[hi] = Hw[p * 3] + m[mp] * dx + m[mp + 1] * dy + m[mp + 2] * dz;
        Hw[hi + 1] = Hw[p * 3 + 1] + m[mp + 3] * dx + m[mp + 4] * dy + m[mp + 5] * dz;
        Hw[hi + 2] = Hw[p * 3 + 2] + m[mp + 6] * dx + m[mp + 7] * dy + m[mp + 8] * dz;
      }
      const mi = i * 12;
      qmat(M, mi, Qw, qi);
      // translation = H - R * head
      M[mi + 9] = Hw[hi] - (M[mi] * heads[hi] + M[mi + 1] * heads[hi + 1] + M[mi + 2] * heads[hi + 2]);
      M[mi + 10] = Hw[hi + 1] - (M[mi + 3] * heads[hi] + M[mi + 4] * heads[hi + 1] + M[mi + 5] * heads[hi + 2]);
      M[mi + 11] = Hw[hi + 2] - (M[mi + 6] * heads[hi] + M[mi + 7] * heads[hi + 1] + M[mi + 8] * heads[hi + 2]);
      // dual quaternion of the bone: real part = Qw (normalised), dual part = 0.5 * (t, 0) * Qw
      const l = Math.hypot(Qw[qi], Qw[qi + 1], Qw[qi + 2], Qw[qi + 3]) || 1;
      const ax = Qw[qi] / l, ay = Qw[qi + 1] / l, az = Qw[qi + 2] / l, aw = Qw[qi + 3] / l;
      const tx = M[mi + 9], ty = M[mi + 10], tz = M[mi + 11];
      const di = i * 8;
      DQ[di] = ax; DQ[di + 1] = ay; DQ[di + 2] = az; DQ[di + 3] = aw;
      DQ[di + 4] = 0.5 * (tx * aw + ty * az - tz * ay);
      DQ[di + 5] = 0.5 * (-tx * az + ty * aw + tz * ax);
      DQ[di + 6] = 0.5 * (tx * ay - ty * ax + tz * aw);
      DQ[di + 7] = -0.5 * (tx * ax + ty * ay + tz * az);
    }
  }

  // Dual quaternion skinning: unlike a linear blend it keeps the volume where a joint turns far
  // (hips in the lotus poses, the twisted forearm), so the buttocks and elbows do not collapse.
  function skin() {
    let minY = Infinity;
    for (let v = 0, o = 0, w = 0; v < nv; v++, o += 3) {
      const x = rest[o], y = rest[o + 1], z = rest[o + 2];
      let b0x = 0, b0y = 0, b0z = 0, b0w = 0, bex = 0, bey = 0, bez = 0, bew = 0;
      const p = J[w] * 8;
      const px0 = DQ[p], py0 = DQ[p + 1], pz0 = DQ[p + 2], pw0 = DQ[p + 3];
      for (let k = 0; k < K; k++, w++) {
        let wt = Wt[w];
        if (wt === 0) continue;
        const d = J[w] * 8;
        if (DQ[d] * px0 + DQ[d + 1] * py0 + DQ[d + 2] * pz0 + DQ[d + 3] * pw0 < 0) wt = -wt;
        b0x += wt * DQ[d]; b0y += wt * DQ[d + 1]; b0z += wt * DQ[d + 2]; b0w += wt * DQ[d + 3];
        bex += wt * DQ[d + 4]; bey += wt * DQ[d + 5]; bez += wt * DQ[d + 6]; bew += wt * DQ[d + 7];
      }
      const il = 1 / (Math.hypot(b0x, b0y, b0z, b0w) || 1);
      const rx = b0x * il, ry = b0y * il, rz = b0z * il, rw = b0w * il;
      const ex = bex * il, ey = bey * il, ez = bez * il, ew = bew * il;
      // rotate: v + 2 r x (r x v + w v)
      const cx = ry * z - rz * y + rw * x, cy = rz * x - rx * z + rw * y, cz = rx * y - ry * x + rw * z;
      let px = x + 2 * (ry * cz - rz * cy);
      let py = y + 2 * (rz * cx - rx * cz);
      let pz = z + 2 * (rx * cy - ry * cx);
      // translate: 2 (w e - ew r + r x e)
      px += 2 * (rw * ex - ew * rx + ry * ez - rz * ey);
      py += 2 * (rw * ey - ew * ry + rz * ex - rx * ez);
      pz += 2 * (rw * ez - ew * rz + rx * ey - ry * ex);
      positions[o] = px; positions[o + 1] = py; positions[o + 2] = pz;
      if (py < minY) minY = py;
    }
    return minY;
  }

  // Mid-transition the root offset and the leg rotations are interpolated separately, so the
  // legs could dip below the floor; lift the whole body (and the bone transforms) when they do.
  function liftAboveFloor(minY) {
    if (!(minY < 0)) return;
    const d = -minY;
    for (let o = 1; o < positions.length; o += 3) positions[o] += d;
    for (let i = 0; i < n; i++) M[i * 12 + 10] += d;
  }

  const skinner = {
    variant,
    positions,
    get poseKey() { return targetKey; },
    /**
     * Pose the body. When (bodyPose, handPose) differ from the current target, the pose shown right
     * now becomes the start of a new transition. t in 0..1 is the progress (pass an eased value;
     * the page drives it over ~0.8 s); omit t (= 1) to jump. Returns `positions`.
     */
    apply(bodyPose = 'stand', handPose = 'open', t = 1) {
      const key = `${typeof bodyPose === 'string' ? bodyPose : 'custom'}|${typeof handPose === 'string' ? handPose : 'custom'}`;
      if (key !== targetKey || typeof bodyPose !== 'string' || typeof handPose !== 'string') {
        if (key !== targetKey) {
          from.set(cur);
          fromRoot.set(curRoot);
        }
        const c = composePose(rig, variant, bodyPose, handPose);
        to.set(c.local);
        toRoot.set(c.root);
        targetKey = key;
      }
      t = Math.min(1, Math.max(0, t));
      lastT = t;
      for (let i = 0; i < n; i++) slerpTo(cur, i * 4, from, to, i * 4, t);
      for (let k = 0; k < 3; k++) curRoot[k] = fromRoot[k] + (toRoot[k] - fromRoot[k]) * t;
      forward();
      const minY = skin();
      if (t < 1) liftAboveFloor(minY);
      return positions;
    },
    /** World transform of a bone (rest -> posed) as a THREE.Matrix4, e.g. for the eyes (head bone). */
    boneMatrix(bone = rig.eyeBone, target = new THREE.Matrix4()) {
      const i = typeof bone === 'string' ? rig.index[bone] : bone;
      const m = M, b = i * 12;
      return target.set(m[b], m[b + 1], m[b + 2], m[b + 9], m[b + 3], m[b + 4], m[b + 5], m[b + 10],
        m[b + 6], m[b + 7], m[b + 8], m[b + 11], 0, 0, 0, 1);
    },
    /** Rigidly move vertices with one bone (default: head, for the eye primitives). */
    skinRigid(restArr, out = new Float32Array(restArr.length), bone = rig.eyeBone) {
      const i = typeof bone === 'string' ? rig.index[bone] : bone;
      const b = i * 12;
      for (let o = 0; o < restArr.length; o += 3) {
        const x = restArr[o], y = restArr[o + 1], z = restArr[o + 2];
        out[o] = M[b] * x + M[b + 1] * y + M[b + 2] * z + M[b + 9];
        out[o + 1] = M[b + 3] * x + M[b + 4] * y + M[b + 5] * z + M[b + 10];
        out[o + 2] = M[b + 6] * x + M[b + 7] * y + M[b + 8] * z + M[b + 11];
      }
      return out;
    },
    /** Area-weighted vertex normals for the current positions (same result as computeVertexNormals). */
    normalsFor(index, out = new Float32Array(positions.length)) {
      out.fill(0);
      const p = positions;
      for (let f = 0; f < index.length; f += 3) {
        const a = index[f] * 3, b = index[f + 1] * 3, c = index[f + 2] * 3;
        const e1x = p[b] - p[a], e1y = p[b + 1] - p[a + 1], e1z = p[b + 2] - p[a + 2];
        const e2x = p[c] - p[a], e2y = p[c + 1] - p[a + 1], e2z = p[c + 2] - p[a + 2];
        const nx = e1y * e2z - e1z * e2y, ny = e1z * e2x - e1x * e2z, nz = e1x * e2y - e1y * e2x;
        out[a] += nx; out[a + 1] += ny; out[a + 2] += nz;
        out[b] += nx; out[b + 1] += ny; out[b + 2] += nz;
        out[c] += nx; out[c + 1] += ny; out[c + 2] += nz;
      }
      for (let o = 0; o < out.length; o += 3) {
        const l = Math.hypot(out[o], out[o + 1], out[o + 2]) || 1;
        out[o] /= l; out[o + 1] /= l; out[o + 2] /= l;
      }
      return out;
    },
    /** True while a transition started by apply() has not reached t = 1. */
    get transitioning() { return lastT < 1; },
  };
  return skinner;
}

/** A point stored as (tri, bary) on primitive 0, evaluated on the current positions. */
export function pointOnMesh(positions, indices, tri, bary, target = new THREE.Vector3()) {
  const a = indices[tri * 3] * 3, b = indices[tri * 3 + 1] * 3, c = indices[tri * 3 + 2] * 3;
  const [w0, w1, w2] = bary;
  return target.set(
    w0 * positions[a] + w1 * positions[b] + w2 * positions[c],
    w0 * positions[a + 1] + w1 * positions[b + 1] + w2 * positions[c + 1],
    w0 * positions[a + 2] + w1 * positions[b + 2] + w2 * positions[c + 2],
  );
}

/*
Usage in the page (body.glb / body_female.glb / body_male.glb share topology):

  import { loadRig, createSkinner, pointOnMesh } from './pose.js';
  const rig = await loadRig('assets/rig.json');            // also loads assets/poses.json
  const gltf = await new GLTFLoader().loadAsync('assets/body_female.glb');
  const meshes = []; gltf.scene.traverse((o) => o.isMesh && meshes.push(o));
  const [skinMesh, eyeL, eyeR] = meshes;                   // primitive order of the glb
  const geo = skinMesh.geometry;
  const skinner = createSkinner(rig, geo.attributes.position.array, 'female');
  geo.setAttribute('position', new THREE.BufferAttribute(skinner.positions, 3));
  const eyeRest = [eyeL, eyeR].map((m) => Float32Array.from(m.geometry.attributes.position.array));
  skinMesh.frustumCulled = false;

  let anim = null;                                          // start a transition on a button press
  function setPose(body, hand) { anim = { body, hand, t0: performance.now() }; }
  function tick(now) {                                      // call from the render loop
    if (!anim) return;
    const u = Math.min(1, (now - anim.t0) / 800);
    const e = u * u * (3 - 2 * u);                          // smoothstep
    skinner.apply(anim.body, anim.hand, e);
    geo.attributes.position.needsUpdate = true;
    geo.computeVertexNormals();                             // or skinner.normalsFor(geo.index.array, normalAttr.array)
    [eyeL, eyeR].forEach((m, i) => {
      skinner.skinRigid(eyeRest[i], m.geometry.attributes.position.array);
      m.geometry.attributes.position.needsUpdate = true;
    });
    // meridian points follow the skin:
    //   pointOnMesh(skinner.positions, geo.index.array, pt.tri, pt.bary, marker.position);
    if (u >= 1) anim = null;
  }
  // body ids: rig.poses.body (stand, tadasana, vrikshasana, sukhasana, ardha_padmasana, padmasana,
  // vajrasana, dandasana); hand ids: rig.poses.hand (open, gyan, prithvi, shuni, vyana, apana,
  // hakini, anjali). vrikshasana has defaultHand 'anjali'.
  // Right-side points (mirrored x) need their own tri/bary on the mirrored triangle.
*/
