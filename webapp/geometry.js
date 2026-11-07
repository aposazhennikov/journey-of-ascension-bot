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
    if (att.offset) out.addScaledVector(this.normal(att.tri, _e1), att.offset);
    return out;
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
SkinSurface.prototype.layCurve = function layCurve(stops, step = 0.005) {
  if (stops.length < 2) return { atts: stops.map((s) => s.att), stopIndex: [0] };
  const curve = new THREE.CatmullRomCurve3(stops.map((s) => s.p), false, 'centripetal');
  const n = stops.length - 1;
  const atts = [];
  const stopIndex = [];
  const ray = new THREE.Ray();
  const q = new THREE.Vector3();
  const nrm = new THREE.Vector3();
  const hit = { point: new THREE.Vector3() };
  for (let i = 0; i < n; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    stopIndex.push(atts.length);
    if (a.att) atts.push({ ...a.att, offset: SURFACE_OFFSET });
    const steps = Math.max(2, Math.ceil(a.p.distanceTo(b.p) / step));
    for (let s = 1; s < steps; s++) {
      const k = s / steps;
      curve.getPoint((i + k) / n, q);
      nrm.lerpVectors(a.n, b.n, k).normalize();
      if (nrm.lengthSq() < 1e-6) nrm.copy(a.n);
      ray.origin.copy(q).addScaledVector(nrm, -0.02);
      ray.direction.copy(nrm);
      const res = this.bvh.closestPointToPoint(q, hit);
      const near = res ? res.distance : 0.05;
      // the outward ray keeps paths over the skin (temple, not cheek), but must not run off to a
      // distant surface such as the inner thigh: accept it only when it stays close to the chord
      const exit = this.bvh.raycastFirst(ray, THREE.DoubleSide, 0, Math.max(0.05, near * 2.5 + 0.02));
      if (exit && exit.face.normal.dot(nrm) > 0) {
        atts.push(this.attach(exit.point, exit.faceIndex));
      } else if (res) {
        atts.push(this.attach(res.point.clone(), res.faceIndex));
      }
    }
  }
  stopIndex.push(atts.length);
  const last = stops[n];
  if (last.att) atts.push({ ...last.att, offset: SURFACE_OFFSET });
  return { atts, stopIndex };
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
