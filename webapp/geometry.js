// Skin-attached geometry for meridian points and lines.
//
// Every point and every line sample is stored as an attachment to the base mesh:
// a triangle index, barycentric weights and an offset along the triangle normal.
// When the body shape changes (female/male) or the model is posed, the page swaps the
// vertex positions and calls evaluate(); attachments follow the skin because all body
// variants share the same topology and triangle order.

import * as THREE from 'three';

export const SURFACE_OFFSET = 0.0025;

const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _c = new THREE.Vector3();
const _e1 = new THREE.Vector3();
const _e2 = new THREE.Vector3();
const _tri = new THREE.Triangle();
const _bary = new THREE.Vector3();

export class SkinSurface {
  /** @param {THREE.BufferGeometry} geometry skin geometry (indexed); positions may be swapped later */
  constructor(geometry, bvh) {
    this.geometry = geometry;
    this.index = geometry.index.array;
    this.positions = geometry.attributes.position.array;
    this.bvh = bvh;
  }

  setPositions(positions) {
    this.positions = positions;
  }

  vertex(i, out) {
    const p = this.positions;
    return out.set(p[3 * i], p[3 * i + 1], p[3 * i + 2]);
  }

  triangle(tri) {
    const idx = this.index;
    this.vertex(idx[3 * tri], _a);
    this.vertex(idx[3 * tri + 1], _b);
    this.vertex(idx[3 * tri + 2], _c);
  }

  /** Attachment for a point that lies on triangle `tri` of the current mesh. */
  attach(point, tri, offset = SURFACE_OFFSET) {
    this.triangle(tri);
    _tri.set(_a, _b, _c);
    _tri.getBarycoord(point, _bary);
    return { tri, bary: [_bary.x, _bary.y, _bary.z], offset };
  }

  /** World position of an attachment on the current positions. */
  evaluate(att, out = new THREE.Vector3()) {
    this.triangle(att.tri);
    const [w0, w1, w2] = att.bary;
    out.set(0, 0, 0).addScaledVector(_a, w0).addScaledVector(_b, w1).addScaledVector(_c, w2);
    if (att.offset) out.addScaledVector(this.smoothNormal(att, _e1), att.offset);
    return out;
  }

  /**
   * Normal interpolated from the vertex normals (falls back to the face normal). Lines are lifted off
   * the skin along it: with the flat face normal the lift jumped at every edge of this low-poly mesh
   * and drew little steps along the line.
   */
  smoothNormal(att, out = new THREE.Vector3()) {
    const nAttr = this.geometry.attributes.normal;
    if (!nAttr) return this.normal(att.tri, out);
    const n = nAttr.array;
    const idx = this.index;
    const [w0, w1, w2] = att.bary;
    const i0 = 3 * idx[3 * att.tri], i1 = 3 * idx[3 * att.tri + 1], i2 = 3 * idx[3 * att.tri + 2];
    out.set(
      n[i0] * w0 + n[i1] * w1 + n[i2] * w2,
      n[i0 + 1] * w0 + n[i1 + 1] * w1 + n[i2 + 1] * w2,
      n[i0 + 2] * w0 + n[i1 + 2] * w1 + n[i2 + 2] * w2,
    );
    if (out.lengthSq() < 1e-10) return this.normal(att.tri, out);
    return out.normalize();
  }

  /** Outward normal of triangle `tri` on the current positions (MakeHuman winding faces out). */
  normal(tri, out = new THREE.Vector3()) {
    this.triangle(tri);
    _e1.subVectors(_b, _a);
    _e2.subVectors(_c, _a);
    return out.crossVectors(_e1, _e2).normalize();
  }

  /**
   * Lay a polyline on the skin through `stops` ({p, n} in rest-pose coordinates, n = outward normal).
   * A chord sample inside the body is pushed out along the blended normal (so a jump like
   * mastoid -> forehead runs over the temple); samples outside fall back to the closest point.
   * Returns attachments.
   */
  layPath(stops, step = 0.01) {
    const out = [];
    const ray = new THREE.Ray();
    const q = new THREE.Vector3();
    const n = new THREE.Vector3();
    const hit = { point: new THREE.Vector3() };
    const push = (point, faceIndex) => out.push(this.attach(point, faceIndex));
    for (let i = 0; i < stops.length - 1; i++) {
      const a = stops[i];
      const b = stops[i + 1];
      const steps = Math.max(2, Math.ceil(a.p.distanceTo(b.p) / step));
      for (let s = 0; s < steps; s++) {
        const k = s / steps;
        q.lerpVectors(a.p, b.p, k);
        n.lerpVectors(a.n, b.n, k).normalize();
        ray.origin.copy(q);
        ray.direction.copy(n);
        const exit = this.bvh.raycastFirst(ray, THREE.DoubleSide, 0, 0.3);
        if (exit && exit.face.normal.dot(n) > 0) {
          push(exit.point, exit.faceIndex);
        } else {
          const res = this.bvh.closestPointToPoint(q, hit);
          if (res) push(res.point.clone(), res.faceIndex);
        }
      }
    }
    const last = stops[stops.length - 1];
    if (last.att) out.push({ ...last.att, offset: SURFACE_OFFSET });
    return out;
  }
}

/**
 * Smooth version of layPath: a centripetal Catmull-Rom curve through the stops (rounded corners,
 * no chords), sampled every `step` metres and then pressed onto the skin the same way.
 * Returns { atts, stopIndex } where stopIndex[i] is the sample index of stop i.
 */
SkinSurface.prototype.layCurve = function layCurve(stopsIn, step = 0.005, opts = {}) {
  if (stopsIn.length < 2) return { atts: stopsIn.map((s) => s.att), stopIndex: [0] };
  // 1) long spans, spans whose end normals disagree and very uneven neighbours cut through the body:
  //    split them with extra stops pressed onto the skin (the given stops keep their index mapping)
  const { stops, original } = this.densifyStops(stopsIn, opts);
  const raw = this.sampleCurve(stops, step, opts);
  // 2) continuity: samples that jump between two facing surfaces are re-pressed or interpolated,
  // 3) a light Laplacian smoothing with the acupuncture points pinned (the inserted helper stops may
  //    move: pinned, they left small kinks wherever the ray put them a little off the smooth curve)
  const pinOriginal = raw.pinned.map((n) => (n !== -1 && original[n] ? n : -1));
  const fixed = this.cleanSamples(raw.atts, pinOriginal, opts);
  const stopIndex = [];
  fixed.pinned.forEach((stopNo, i) => { if (stopNo !== -1 && original[stopNo]) stopIndex.push(i); });
  return { atts: fixed.atts, stopIndex };
};

/** Insert skin stops into spans that are long (> 8 cm), bend the normal by > 60 deg or are > 3x their neighbours. */
SkinSurface.prototype.densifyStops = function densifyStops(stopsIn, opts = {}) {
  const out = [];
  const original = [];
  const ray = new THREE.Ray();
  const hit = { point: new THREE.Vector3() };
  const mid = new THREE.Vector3();
  const dir = new THREE.Vector3();
  const len = (i) => (i >= 0 && i < stopsIn.length - 1 ? stopsIn[i].p.distanceTo(stopsIn[i + 1].p) : 0);
  // new stops sit on the smooth curve through the original stops (not on the chord), so the line keeps
  // its arcs and only stops cutting through the body
  const curve0 = new THREE.CatmullRomCurve3(stopsIn.map((s) => s.p), false, 'centripetal');
  const nSeg = stopsIn.length - 1;
  const split = (a, b, depth, spanRatio, ta, tb) => {
    const chord = a.p.distanceTo(b.p);
    const nDot = a.n.dot(b.n);
    const need = depth < 5 && (chord > 0.08 || (nDot < 0.5 && chord > 0.02) || spanRatio > 3);
    if (!need) return [];
    if (nDot < -0.2) {
      if (!opts.quiet) console.warn('layCurve: opposite normals over a span, add a via waypoint', a.p.toArray(), b.p.toArray());
      return [];
    }
    const tm = (ta + tb) / 2;
    curve0.getPoint(tm, mid);
    dir.addVectors(a.n, b.n).normalize();
    if (opts.midline) { mid.x = 0; dir.x = 0; dir.normalize(); }
    const res = this.bvh.closestPointToPoint(mid, hit);
    const near = res ? res.distance : 0.05;
    ray.origin.copy(mid).addScaledVector(dir, -0.02);
    ray.direction.copy(dir);
    const exit = this.bvh.raycastFirst(ray, THREE.DoubleSide, 0, near + 0.04);
    let p; let face;
    if (exit && exit.face.normal.dot(dir) > 0) { p = exit.point.clone(); face = exit.faceIndex; }
    else if (res) { p = res.point.clone(); face = res.faceIndex; }
    else return [];
    if (opts.midline) p.x = 0;
    const att = this.attach(p, face);
    const m = { p: this.evaluate({ ...att, offset: 0 }), n: this.normal(face, new THREE.Vector3()), att };
    return [...split(a, m, depth + 1, 1, ta, tm), m, ...split(m, b, depth + 1, 1, tm, tb)];
  };
  for (let i = 0; i < stopsIn.length; i++) {
    out.push(stopsIn[i]);
    original.push(true);
    if (i === stopsIn.length - 1) break;
    const L = len(i);
    const nb = Math.max(1e-6, Math.min(...[len(i - 1), len(i + 1)].filter((x) => x > 0), L));
    for (const m of split(stopsIn[i], stopsIn[i + 1], 0, L / nb, i / nSeg, (i + 1) / nSeg)) { out.push(m); original.push(false); }
  }
  return { stops: out, original };
};

/**
 * Midline channels (Du Mai, Ren Mai): find the skin point ON the plane x = 0 by a ray inside that
 * plane. The closest-point search must not be used there: in the gluteal cleft (and under the chin)
 * the two sides of the body meet at the midline and the closest point flips from one wall to the
 * other, which drew a zigzag.
 */
SkinSurface.prototype.pressMidline = function pressMidline(p, dir) {
  const first = new THREE.Vector3(0, dir.y, dir.z);
  // try the blended normal, then straight back/front and down/up, all inside the plane x = 0
  const tries = [first, new THREE.Vector3(0, 0, p.z >= -0.05 ? 1 : -1), new THREE.Vector3(0, 0, p.z >= -0.05 ? -1 : 1),
    new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 1, 0)];
  for (const d of tries) {
    if (d.lengthSq() < 1e-8) continue;
    d.normalize();
    const ray = new THREE.Ray(new THREE.Vector3(0, p.y, p.z).addScaledVector(d, -0.06), d);
    const hits = this.bvh.raycast(ray, THREE.DoubleSide, 0, 0.14) || [];
    // the first place where the ray leaves the body inside the plane: the bottom of a crease, never
    // a second body part further along the ray
    let best = null;
    for (const h of hits) {
      if (h.face.normal.dot(d) <= 0) continue;
      if (!best || h.distance < best.distance) best = h;
    }
    if (!best) continue;
    const q = best.point.clone();
    if (q.distanceTo(p) > 0.05) continue;     // that ray found some other surface
    q.x = 0;
    return this.attach(q, best.faceIndex);
  }
  return null;
};

/** Catmull-Rom through the stops, every `step` m, pressed onto the skin. pinned[i] = stop number or -1. */
SkinSurface.prototype.sampleCurve = function sampleCurve(stops, step, opts = {}) {
  const curve = new THREE.CatmullRomCurve3(stops.map((s) => s.p), false, 'centripetal');
  const n = stops.length - 1;
  const atts = [];
  const pinned = [];
  const ray = new THREE.Ray();
  const q = new THREE.Vector3();
  const nrm = new THREE.Vector3();
  const fn = new THREE.Vector3();
  const hit = { point: new THREE.Vector3() };
  for (let i = 0; i < n; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (a.att) { atts.push({ ...a.att, offset: SURFACE_OFFSET }); pinned.push(i); }
    const steps = Math.max(2, Math.ceil(a.p.distanceTo(b.p) / step));
    for (let s = 1; s < steps; s++) {
      const k = s / steps;
      curve.getPoint((i + k) / n, q);
      nrm.lerpVectors(a.n, b.n, k).normalize();
      if (nrm.lengthSq() < 1e-6) nrm.copy(a.n);
      if (opts.midline) {
        q.x = 0; nrm.x = 0; nrm.normalize();
        const am = this.pressMidline(q, nrm);
        if (am) { atts.push(am); pinned.push(-1); continue; }
      }
      const res = this.bvh.closestPointToPoint(q, hit);
      const near = res ? res.distance : 0.05;
      let att = null;
      // a sample already outside the skin goes straight to the closest point; one inside is pushed
      // out by a short ray that must not reach another body part (limit near + 2 cm)
      const outside = res && fn.subVectors(q, res.point).dot(this.normal(res.faceIndex, new THREE.Vector3())) > 0;
      if (!outside) {
        ray.origin.copy(q).addScaledVector(nrm, -0.02);
        ray.direction.copy(nrm);
        const exit = this.bvh.raycastFirst(ray, THREE.DoubleSide, 0, near + 0.04);
        if (exit && exit.face.normal.dot(nrm) > 0) att = this.attach(exit.point, exit.faceIndex);
      }
      if (!att && res) att = this.attach(res.point.clone(), res.faceIndex);
      if (att) { atts.push(att); pinned.push(-1); }
    }
  }
  const last = stops[n];
  if (last.att) { atts.push({ ...last.att, offset: SURFACE_OFFSET }); pinned.push(n); }
  return { atts, pinned };
};

/**
 * Continuity and smoothing. A sample is bad when it jumps > 1.5 cm from a neighbour or its normal
 * turns away from both neighbours (dot < 0.2): it is re-pressed from the neighbours' midpoint.
 * Then 2 Laplacian passes (lambda 0.5) with the stops pinned, each result pressed onto the skin, and
 * samples closer than 0.5 mm are dropped.
 */
SkinSurface.prototype.cleanSamples = function cleanSamples(attsIn, pinnedIn, opts = {}) {
  let atts = attsIn.slice();
  let pinned = pinnedIn.slice();
  const pos = () => atts.map((a) => this.evaluate({ ...a, offset: 0 }));
  const nrm = () => atts.map((a) => this.normal(a.tri, new THREE.Vector3()));
  const tmp = new THREE.Vector3();
  const press = (p, i) => {
    if (opts.midline) {
      p.x = 0;
      const n = i != null ? this.normal(atts[i].tri, new THREE.Vector3()) : new THREE.Vector3(0, 0, p.z >= 0 ? 1 : -1);
      return this.pressMidline(p, n);   // no closest-point fallback on the midline (it flips sides)
    }
    return this.attachNearest(p);
  };
  for (let pass = 0; pass < 2; pass++) {
    const P = pos();
    const N = nrm();
    let changed = false;
    for (let i = 1; i < atts.length - 1; i++) {
      if (pinned[i] !== -1) continue;
      const jump = Math.max(P[i].distanceTo(P[i - 1]), P[i].distanceTo(P[i + 1]));
      const turned = N[i].dot(N[i - 1]) < 0.2 && N[i].dot(N[i + 1]) < 0.2;
      if (jump > 0.015 || turned) {
        const a = press(tmp.lerpVectors(P[i - 1], P[i + 1], 0.5).clone(), i);
        if (a) { atts[i] = a; P[i] = this.evaluate({ ...a, offset: 0 }); N[i] = this.normal(a.tri, new THREE.Vector3()); changed = true; }
      }
    }
    if (!changed) break;
  }
  const iters = opts.smoothIters ?? this.constructor.smoothIters ?? 4;
  for (let it = 0; it < iters; it++) {
    const P = pos();
    const next = atts.slice();
    for (let i = 1; i < atts.length - 1; i++) {
      if (pinned[i] !== -1) continue;
      const target = tmp.addVectors(P[i - 1], P[i + 1]).multiplyScalar(0.5);
      const moved = P[i].clone().lerp(target, 0.5);
      const a = press(moved, i);
      if (a) next[i] = a;
    }
    atts = next;
  }
  const P = pos();
  const keepA = [];
  const keepP = [];
  for (let i = 0; i < atts.length; i++) {
    if (pinned[i] === -1 && keepA.length && P[i].distanceTo(this.evaluate({ ...keepA[keepA.length - 1], offset: 0 })) < 0.0005) continue;
    keepA.push(atts[i]);
    keepP.push(pinned[i]);
  }
  atts = keepA;
  pinned = keepP;
  return { atts: atts.map((a) => ({ ...a, offset: SURFACE_OFFSET })), pinned };
};

/** Attachment for an arbitrary point near the skin (closest surface point). */
SkinSurface.prototype.attachNearest = function attachNearest(point, offset = SURFACE_OFFSET) {
  const res = this.bvh.closestPointToPoint(point, { point: new THREE.Vector3() });
  return res ? this.attach(res.point, res.faceIndex, offset) : null;
};

/** Arc length along a list of Vector3, normalized to 0..1 (used by the flow animation). */
export function arcFractions(points) {
  const d = [0];
  for (let i = 1; i < points.length; i++) d.push(d[i - 1] + points[i].distanceTo(points[i - 1]));
  const total = d[d.length - 1] || 1;
  return { fractions: d.map((x) => x / total), length: total };
}

/** Mirror an attachment-free rest point to the body's right side. */
export function mirrorX(v, side) {
  return side === 1 ? v.clone() : new THREE.Vector3(-v.x, v.y, v.z);
}
