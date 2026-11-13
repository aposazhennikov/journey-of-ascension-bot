// 3D scene of the meridian map: body, channel lines, points, energy flow, camera.
// Everything on the skin is stored as an attachment (triangle + barycentrics), so it follows
// the body when the shape is switched (female/male) or the model takes a pose.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { MeshBVH, acceleratedRaycast } from 'three-mesh-bvh';
import { SkinSurface, SURFACE_OFFSET } from './geometry.js';
import { PALETTE, BODY_TONE } from './channels.js';

THREE.Mesh.prototype.raycast = acceleratedRaycast;

const BODY_COLORS = {
  // warm skin with warm shadows, a cool fill from the sky on the shadow side, a light rim along the
  // silhouette and a warm band where light turns to shadow (the artist of the council: the grey-beige
  // clay with flat front light read as a plastic dummy)
  light: { base: '#dcb89d', shadow: '#7f5b49', rim: '#fff6ec', fill: '#a9bccd', sss: '#d58e74' },
  // dark: lighter skin and a dimmer rim (round 3: with the narrower light wrap the figure went near black
  // on the dark theme and the rim drew a white line along the arms)
  dark: { base: '#75655a', shadow: '#33291f', rim: '#a3b2c2', fill: '#5d7186', sss: '#8a5644' },
};

export const reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };

// ---------- shaders ----------

// One comet per pass (spec 4.2); uWave turns it into a soft wave (vessels), uConst into a steady glow.
const FLOW_GLSL = /* glsl */`
uniform float uHeadS;
uniform float uTail;
uniform float uHead;
uniform float uIntensity;
uniform float uWave;
uniform float uConst;
float flowPulse(float s) {
  float d = uHeadS - s;
  float k = d < 0.0 ? exp(-d * d / (uHead * uHead))
                    : exp(-d / (0.35 * uTail)) * (1.0 - smoothstep(0.8 * uTail, uTail, d));
  float w = exp(-(s - uHeadS) * (s - uHeadS) / (2.0 * 0.15 * 0.15));
  k = mix(k, w, uWave);
  k = mix(k, 1.0, uConst);
  return k * uIntensity * step(-500.0, s);
}`;

function makeFlowUniforms() {
  return {
    uHeadS: { value: -10 }, uTail: { value: 0.12 }, uHead: { value: 0.012 },
    uIntensity: { value: 0 }, uWave: { value: 0 }, uConst: { value: 0 },
  };
}

const LINE_VERTEX_ANCHOR = 'vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );';
const LINE_FRAGMENT_ANCHOR = 'gl_FragColor = vec4( diffuseColor.rgb, alpha );';
const DASH_DISCARD = /if \( mod\( vLineDistance[^\n]*\n/;

function patchLift(material, lift = 0.003) {
  let vs = material.vertexShader;
  if (!vs.includes(LINE_VERTEX_ANCHOR)) throw new Error('LineMaterial vertex shader changed');
  // vFace: how much the skin under the line faces the camera. A line on skin seen edge-on along the
  // silhouette turned into a solid band (the heart line along the forearm read as a red cut, council);
  // it fades out there. Needs instanceNStart / instanceNEnd (skin normals) and uUseFace = 1.
  vs = vs.replace('void main() {', 'uniform float uLift;\nuniform float uUseFace;\nattribute vec3 instanceNStart;\nattribute vec3 instanceNEnd;\nvarying float vFace;\nvoid main() {')
    .replace(LINE_VERTEX_ANCHOR, `${LINE_VERTEX_ANCHOR}
      {
        vec3 nS = normalMatrix * instanceNStart;
        vec3 nE = normalMatrix * instanceNEnd;
        float fS = dot( nS, nS ) > 0.0 ? dot( normalize( nS ), normalize( -start.xyz ) ) : 1.0;
        float fE = dot( nE, nE ) > 0.0 ? dot( normalize( nE ), normalize( -end.xyz ) ) : 1.0;
        vFace = uUseFace > 0.5 ? ( position.y < 0.5 ? fS : fE ) : 1.0;
      }
      start.xyz -= normalize( start.xyz ) * uLift;
      end.xyz -= normalize( end.xyz ) * uLift;`);
  material.vertexShader = vs;
  material.uniforms.uLift = { value: lift };
  material.uniforms.uUseFace = { value: 0 };
  // the muted overview fades early; a chosen channel only right at the silhouette (the heart line on the
  // inner arm, seen from the front, vanished with the overview's thresholds)
  material.uniforms.uFaceLo = { value: -0.02 };
  material.uniforms.uFaceHi = { value: 0.12 };
  material.uniforms.uFaceFloor = { value: 0 };
}

const FACE_FADE = 'mix( uFaceFloor, 1.0, smoothstep( uFaceLo, uFaceHi, vFace ) )';

/** Channel line: soft dark casing (light theme) or fading edge (dark theme), AA edges; optional beads. */
class CasedLineMaterial extends LineMaterial {
  constructor({ beads = false, dashedLink = false, ...params }) {
    // transparent: the AA edge alpha must blend with the body, not punch through the alpha canvas to the page
    super({ transparent: true, ...params, worldUnits: false, dashed: beads || dashedLink || params.dashed });
    patchLift(this);
    this.uniforms.uCasing = { value: 0.55 };
    this.uniforms.uDarkEdge = { value: 0 };
    this.uniforms.uBeads = { value: beads ? 1 : 0 };
    let fs = this.fragmentShader;
    if (!fs.includes(LINE_FRAGMENT_ANCHOR)) throw new Error('LineMaterial fragment shader changed');
    if (beads) fs = fs.replace(DASH_DISCARD, '');
    fs = fs.replace('void main() {', 'uniform float uCasing;\nuniform float uDarkEdge;\nuniform float uBeads;\nuniform float uFaceLo;\nuniform float uFaceHi;\nuniform float uFaceFloor;\nvarying float vFace;\nvoid main() {')
      .replace(LINE_FRAGMENT_ANCHOR, `
        float x = abs( vUv.x );
        float aa = fwidth( x );
        vec3 casing = diffuseColor.rgb * 0.42;
        vec3 col = mix( diffuseColor.rgb, casing, smoothstep( 0.7, 0.92, x ) * uCasing );
        float a = alpha * ( 1.0 - smoothstep( 1.0 - aa, 1.0, x ) ) * ${FACE_FADE};
        a *= 1.0 - 0.6 * smoothstep( 0.5, 1.0, x ) * uDarkEdge;
        #ifdef USE_DASH
          float bead = 1.0 - smoothstep( 0.55, 0.75, abs( fract( vLineDistance / 0.03 ) - 0.5 ) * 2.0 );
          a *= mix( 1.0, bead * 0.55 + 0.0, uBeads );
        #endif
        gl_FragColor = vec4( col, a );`);
    this.fragmentShader = fs;
  }
}

/** Comet / wave layer; arc length comes from instanceDistanceStart/End. */
class FlowLineMaterial extends LineMaterial {
  constructor(params, uniforms) {
    super({ ...params, dashed: true, transparent: true, depthWrite: false, worldUnits: false });
    patchLift(this, 0.006);
    Object.assign(this.uniforms, uniforms);
    let fs = this.fragmentShader;
    if (!fs.includes(LINE_FRAGMENT_ANCHOR)) throw new Error('LineMaterial fragment shader changed');
    this.uniforms.uWhite = { value: 0.6 };
    fs = fs.replace(DASH_DISCARD, '')
      .replace('void main() {', `${FLOW_GLSL}\nuniform float uWhite;\nuniform float uFaceLo;\nuniform float uFaceHi;\nuniform float uFaceFloor;\nvarying float vFace;\nvoid main() {`)
      .replace(LINE_FRAGMENT_ANCHOR, `
        float I = flowPulse( vLineDistance );
        float x = abs( vUv.x );
        float core = 1.0 - smoothstep( 0.2 + 0.4 * I, 0.35 + 0.65 * I, x );
        // light theme: keep the comet in the channel colour (a white comet vanishes on light skin)
        vec3 col = mix( diffuseColor.rgb, vec3( 1.0 ), uWhite * I * ( 1.0 - x ) * ( 1.0 - x ) );
        gl_FragColor = vec4( col, alpha * core * I * ${FACE_FADE} );`);
    this.fragmentShader = fs;
  }
}

const POINTS_VS = /* glsl */`
attribute vec3 aColor;
attribute vec3 aCore;
attribute vec3 aRing;
attribute float aArc;
attribute float aState;
attribute float aShape;
attribute float aSize;
uniform float uDpr;
uniform float uFlowOn;
uniform vec3 uCamTarget;
varying vec3 vColor;
varying vec3 vCore;
varying vec3 vRing;
varying float vFacing;
varying float vGlow;
varying float vHasRing;
varying float vShape;
varying float vDim;
${FLOW_GLSL}
void main() {
  vec4 mv = modelViewMatrix * vec4( position, 1.0 );
  vec3 n = normalize( normalMatrix * normal );
  vFacing = smoothstep( -0.05, 0.3, dot( n, normalize( -mv.xyz ) ) ) * step( 0.5, aState );
  vDim = aState < 1.5 ? 0.6 : 1.0;
  mv.xyz -= normalize( mv.xyz ) * 0.007;   // above the selected line (5 mm) and the flow (6 mm)
  gl_Position = projectionMatrix * mv;
  vGlow = uFlowOn * flowPulse( aArc );
  vHasRing = step( 0.01, aRing.r + aRing.g + aRing.b );
  vColor = aColor;
  vCore = aCore;
  vRing = aRing;
  vShape = aShape;
  float closeUp = 1.0 - smoothstep( 0.6, 1.0, length( mv.xyz ) );
  float base = aState > 2.5 ? 13.0 : ( aState < 1.5 ? 5.0 : aSize * ( 1.0 + 0.43 * closeUp ) );
  gl_PointSize = min( 64.0, base * uDpr * ( 1.0 + 0.5 * vGlow ) );
}`;

const POINTS_FS = /* glsl */`
varying vec3 vColor;
varying vec3 vCore;
varying vec3 vRing;
varying float vFacing;
varying float vGlow;
varying float vHasRing;
varying float vShape;
varying float vDim;
void main() {
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  float r = vShape < 0.5 ? length( q ) : ( vShape < 1.5 ? ( abs( q.x ) + abs( q.y ) ) : max( abs( q.x ), abs( q.y ) ) * 1.04 );
  float aa = fwidth( r ) + 0.001;
  float disc = 1.0 - smoothstep( 1.0 - aa, 1.0, r );
  float ringStart = vHasRing > 0.5 ? 0.8 : 1.1;
  float core = 1.0 - smoothstep( 0.55 - aa, 0.55 + aa, r );
  vec3 col = mix( vColor, vCore, core );
  col = mix( col, vRing, smoothstep( ringStart - aa, ringStart + aa, r ) * vHasRing );
  col = mix( col, vec3( 1.0 ), 0.6 * vGlow );
  float a = disc * vFacing * vDim;
  if ( a < 0.01 ) discard;
  gl_FragColor = vec4( col, a );
}`;

// ---------- helpers ----------

function makeClayMatcap({ base, shadow, rim, fill, sss }, size = 256) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  const img = g.createImageData(size, size);
  // key light from the upper left at ~45 deg
  const L = new THREE.Vector3(-0.5, 0.6, 0.62).normalize();
  // the canvas holds sRGB bytes: THREE.Color keeps linear values, so read them back as sRGB (writing the
  // linear ones made every tone darker and more saturated - the dark skin #75655a came out as (33,23,18),
  // and the light skin read as evenly orange to the artist, round 3)
  const srgb = (hex) => { const o = { r: 0, g: 0, b: 0 }; new THREE.Color(hex).getRGB(o, THREE.SRGBColorSpace); return o; };
  const b = srgb(base);
  const s = srgb(shadow);
  const r = srgb(rim);
  const f = srgb(fill || shadow);
  const t = srgb(sss || base);
  const ch = [[s.r, b.r, r.r, f.r, t.r], [s.g, b.g, r.g, f.g, t.g], [s.b, b.b, r.b, f.b, t.b]];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const nx = ((x + 0.5) / size) * 2 - 1;
      const ny = 1 - ((y + 0.5) / size) * 2;
      const r2 = nx * nx + ny * ny;
      const i = 4 * (y * size + x);
      img.data[i + 3] = 255;
      if (r2 > 1) continue;
      const nz = Math.sqrt(1 - r2);
      const ndl = nx * L.x + ny * L.y + nz * L.z;
      // wrap 0.25 (was 0.4): with the wider wrap the whole front was one tone and the legs had no volume,
      // light to shadow ~15 % (artist round 3)
      const wrap = THREE.MathUtils.smoothstep((ndl + 0.25) / 1.25, 0, 1);
      const fres = Math.pow(1 - nz, 2.5);
      const spec = Math.pow(Math.max(0, 2 * ndl * nz - L.z), 24) * 0.035;
      // the cool fill lifts the side away from the key; the warm band sits on the terminator; the rim
      // is strongest on the upper and side edges (light from behind), weaker at the bottom
      const fillK = (1 - wrap) * 0.22 * THREE.MathUtils.smoothstep(nx * 0.7 + 0.3, 0, 1);
      // (band .26, rim .58: at .18 / .42 neither showed against the photo, artist round 2)
      const band = Math.exp(-Math.pow((wrap - 0.42) / 0.16, 2)) * 0.26;
      const rimK = fres * 0.58 * (0.55 + 0.45 * THREE.MathUtils.smoothstep(ny + 0.3, 0, 1));
      for (let k = 0; k < 3; k++) {
        let v = ch[k][0] + (ch[k][1] - ch[k][0]) * wrap;
        v += (ch[k][3] - v) * fillK;
        v += (ch[k][4] - v) * band;
        v += (ch[k][2] - v) * rimK + spec;
        img.data[i + k] = Math.min(255, Math.max(0, v * 255));
      }
    }
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeRingTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.lineWidth = 10;
  g.strokeStyle = 'rgba(255,255,255,0.95)';
  g.beginPath(); g.arc(64, 64, 36, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 12;
  g.strokeStyle = 'rgba(255,255,255,0.5)';
  g.beginPath(); g.arc(64, 64, 54, 0, Math.PI * 2); g.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeFloorShadow() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  // a little stronger, so the figure stands on the fog of the photos instead of floating (artist round 2)
  // round 3: a denser core under the feet, the contact read as barely there
  grad.addColorStop(0, 'rgba(30,20,10,0.4)');
  grad.addColorStop(0.45, 'rgba(30,20,10,0.22)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(0.7, 0.45),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.001;
  return mesh;
}

const easeInOutCubic = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

function segmentsGeometry(polylines, { colors = null, withDistance = false } = {}) {
  const segs = [];
  const dist = [];
  const cols = [];
  const nrms = [];
  const withNormals = polylines.every((pl) => pl.normals && pl.normals.length === pl.positions.length);
  for (const pl of polylines) {
    const c = colors ? colors(pl) : null;
    for (let i = 0; i < pl.positions.length - 1; i++) {
      const a = pl.positions[i];
      const b = pl.positions[i + 1];
      segs.push(a.x, a.y, a.z, b.x, b.y, b.z);
      if (withNormals) { const na = pl.normals[i], nb = pl.normals[i + 1]; nrms.push(na.x, na.y, na.z, nb.x, nb.y, nb.z); }
      if (withDistance) dist.push(pl.arcs[i], pl.arcs[i + 1]);
      if (c) cols.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
  }
  if (!segs.length) return null;
  const geom = new LineSegmentsGeometry();
  geom.setPositions(segs);
  if (colors) geom.setColors(cols);
  if (withDistance) {
    const buf = new THREE.InstancedInterleavedBuffer(new Float32Array(dist), 2, 1);
    geom.setAttribute('instanceDistanceStart', new THREE.InterleavedBufferAttribute(buf, 1, 0));
    geom.setAttribute('instanceDistanceEnd', new THREE.InterleavedBufferAttribute(buf, 1, 1));
  }
  if (withNormals) setLineNormals(geom, new Float32Array(nrms));
  geom.userData.hasFace = withNormals;
  return geom;
}

function setLineNormals(geom, arr) {
  const buf = new THREE.InstancedInterleavedBuffer(arr, 6, 1);
  geom.setAttribute('instanceNStart', new THREE.InterleavedBufferAttribute(buf, 3, 0));
  geom.setAttribute('instanceNEnd', new THREE.InterleavedBufferAttribute(buf, 3, 3));
  return buf;
}

// ---------- scene ----------

export class MeridianScene {
  constructor(container, { theme = 'light', getViewport }) {
    this.container = container;
    this.getViewport = getViewport;
    this.theme = theme;
    const weak = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 3;
    const dpr = window.devicePixelRatio || 1;
    // antialiasing on phones too (it was off at dpr >= 2: jagged figure edges showed against the darker
    // photo, artist of the council); MSAA is cheap on tile-based mobile GPUs, weak devices still skip it
    this.renderer = new THREE.WebGLRenderer({ antialias: !weak, alpha: true, powerPreference: 'high-performance' });
    this.dpr = Math.min(dpr, weak ? 1.5 : 2);
    this.renderer.setPixelRatio(this.dpr);
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.onContextLost?.(); });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => { this.rebuildMatcap(); this.requestRender(); this.onContextRestored?.(); });

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.05, 30);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    Object.assign(this.controls, {
      enableDamping: true, dampingFactor: 0.09, rotateSpeed: 0.7, zoomSpeed: 0.9, zoomToCursor: true,
      minDistance: 0.3, maxDistance: 6, minPolarAngle: 0.25, maxPolarAngle: Math.PI - 0.35, screenSpacePanning: true,
    });
    this.controls.target.set(0, 0.86, 0);
    this.controls.addEventListener('change', () => this.requestRender());
    this.controls.addEventListener('start', () => { this.tween = null; this.onUserMove?.(); });

    this.shadow = makeFloorShadow();
    this.scene.add(this.shadow);
    this.flowUniforms = makeFlowUniforms();
    this.flow = { mode: 'off', time: 0, playing: false, fades: [], v: 0.15, period: 10, passes: 0 };
    this.needsRender = true;
    this.tween = null;
    this.channels = new Map();
    this.pointIndex = new Map();
    this.selection = {};
    this.ringTex = makeRingTexture();
    this.halos = [0, 1].map(() => this.makeSprite(5));
    this.contactSprites = [];
    this.lastFrame = performance.now();
    this.resize = this.resize.bind(this);
    window.addEventListener('resize', this.resize);
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  makeSprite(order) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.ringTex, transparent: true, depthWrite: false }));
    s.visible = false;
    s.renderOrder = order;
    this.scene.add(s);
    return s;
  }

  requestRender() { this.needsRender = true; }

  colorOf(id) { return PALETTE[this.theme][id] || '#888888'; }

  // ----- body -----

  async loadBody(url, onProgress) {
    const gltf = await new GLTFLoader().loadAsync(url, onProgress);
    const meshes = [];
    gltf.scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
    this.bodyMaterial = new THREE.MeshMatcapMaterial({ matcap: makeClayMatcap(BODY_COLORS[this.theme]) });
    this.eyeMaterial = new THREE.MeshMatcapMaterial({ matcap: this.bodyMaterial.matcap, color: new THREE.Color(0.92, 0.92, 0.92) });
    this.body = meshes.find((m) => m.geometry.attributes.position.count > 1000);
    this.eyes = meshes.filter((m) => m !== this.body);
    this.body.material = this.bodyMaterial;
    for (const e of this.eyes) e.material = this.eyeMaterial;
    this.scene.add(gltf.scene);
    this.restPositions = Float32Array.from(this.body.geometry.attributes.position.array);
    this.eyeRest = this.eyes.map((e) => Float32Array.from(e.geometry.attributes.position.array));
    // indirect: keep the original index order, stored tri ids refer to it
    this.bvh = new MeshBVH(this.body.geometry, { indirect: true });
    this.body.geometry.boundsTree = this.bvh;
    this.skin = new SkinSurface(this.body.geometry, this.bvh);
    // lines and stops are always laid on a separate copy of the rest (standing) skin: laid on a posed
    // body (or with a stale BVH after a pose change) samples stuck to the wrong body part, and once the
    // limbs moved those segments ran through the air as long straight dashes
    const restGeom = new THREE.BufferGeometry();
    restGeom.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(this.restPositions), 3));
    restGeom.setIndex(new THREE.BufferAttribute(Uint32Array.from(this.body.geometry.index.array), 1));
    restGeom.computeVertexNormals();
    this.restSkin = new SkinSurface(restGeom, new MeshBVH(restGeom, { indirect: true }));
    this.requestRender();
  }

  /** Replace body vertex positions (another body shape or a pose) and move everything attached. */
  setBodyPositions(positions, eyePositions, { normals = true } = {}) {
    const attr = this.body.geometry.attributes.position;
    attr.array.set(positions);
    attr.needsUpdate = true;
    if (normals) this.body.geometry.computeVertexNormals();
    this.body.geometry.computeBoundingSphere();
    if (eyePositions) {
      this.eyes.forEach((e, i) => {
        if (!eyePositions[i]) return;
        e.geometry.attributes.position.array.set(eyePositions[i]);
        e.geometry.attributes.position.needsUpdate = true;
        if (normals) e.geometry.computeVertexNormals();
        e.geometry.computeBoundingSphere();
      });
    }
    this.skin.setPositions(attr.array);
    this.bvhDirty = true;
    this.relayout();
  }

  refitBvh() {
    if (!this.bvhDirty) return;
    this.bvh.refit();
    this.bvhDirty = false;
  }

  rebuildMatcap() {
    if (!this.bodyMaterial) return;
    this.bodyMaterial.matcap?.dispose();
    this.bodyMaterial.matcap = makeClayMatcap(BODY_COLORS[this.theme]);
    this.eyeMaterial.matcap = this.bodyMaterial.matcap;
    this.bodyMaterial.needsUpdate = true;
    this.eyeMaterial.needsUpdate = true;
  }

  setTheme(theme) {
    if (theme === this.theme) return;
    this.theme = theme;
    this.rebuildMatcap();
    if (this.overview) this.setSelection(this.selection);
    this.requestRender();
  }

  // ----- channels -----

  /**
   * channels: [{ id, kind: 'regular'|'vessel', bilateral, chains: [[codes]], link: {from,to,internal}, points: [codes] }]
   */
  buildChannels(channels, coords, via) {
    this.coords = coords;
    this.via = via || {};
    this.restAttCache = new Map();
    this.channels.clear();
    for (const ch of channels) this.channels.set(ch.id, this.layChannel(ch));
    this.buildOverview();
    this.buildPoints(channels);
    this.relayout();
  }

  /**
   * Stop for a stored point on the CURRENT mesh. Points were placed on the neutral body, but all
   * bodies share topology, so the left attachment (tri/bary) is valid everywhere; the right side is
   * found by mirroring the left point evaluated on the loaded body.
   */
  stopFromEntry(c, side) {
    if (!c) return null;
    const rs = this.restSkin;
    let attL = c.tri != null ? { tri: c.tri, bary: c.bary, offset: SURFACE_OFFSET } : rs.attachNearest(new THREE.Vector3(...c.p));
    if (!attL) return null;
    let att = attL;
    if (side === -1) {
      if (c.tri_r != null) att = { tri: c.tri_r, bary: c.bary_r, offset: SURFACE_OFFSET };
      else {
        const pL = rs.evaluate({ ...attL, offset: 0 });
        att = rs.attachNearest(new THREE.Vector3(-pL.x, pL.y, pL.z));
      }
    }
    if (!att) return null;
    const p = rs.evaluate({ ...att, offset: 0 });
    const n = rs.normal(att.tri, new THREE.Vector3());
    return { p, n, att };
  }

  restAtt(code, side) {
    const key = `${code}|${side}`;
    if (this.restAttCache.has(key)) return this.restAttCache.get(key);
    const res = this.stopFromEntry(this.coords[code], side);
    this.restAttCache.set(key, res);
    return res;
  }

  viaStops(a, b, side) {
    return (this.via[`${a}>${b}`] || []).map((w) => this.stopFromEntry(w, side)).filter(Boolean);
  }

  layChain(codes, side, s0, flags = {}) {
    const stops = [];
    const stopCodes = [];
    codes.forEach((code, i) => {
      // "CODE*" = the point on the opposite side (the large intestine crosses to the other GI19/GI20)
      const flip = code.endsWith('*');
      const st = this.restAtt(flip ? code.slice(0, -1) : code, flip ? -side : side);
      if (!st) return;
      stops.push(st);
      stopCodes.push(code);
      if (i < codes.length - 1) for (const v of this.viaStops(code, codes[i + 1], side)) { stops.push(v); stopCodes.push(null); }
    });
    if (stops.length < 2) return null;
    const { atts, stopIndex } = this.restSkin.layCurve(stops, 0.005, { midline: !!flags.midline, quiet: true });
    return { side, atts, stopIndex, stopCodes, s0, positions: null, arcs: null, ...flags };
  }

  layChannel(ch) {
    const sides = ch.bilateral ? [1, -1] : [1];
    const chains = ch.chains.map((codes) => codes.filter((c) => this.coords[c.replace(/\*$/, '')]));
    const arcOf = new Map();
    const polylines = [];
    let mainLen = 0;
    chains.forEach((codes, ci) => {
      if (codes.length < 2) return;
      const s0 = arcOf.has(codes[0]) ? arcOf.get(codes[0]) : 0;
      // unpaired channels (Du Mai, Ren Mai) stay exactly on the midline
      const midline = !ch.bilateral && ch.kind !== 'vessel';
      const made = sides.map((side) => this.layChain(codes, side, s0, { chain: ci, midline })).filter(Boolean);
      polylines.push(...made);
      const ref = made[0];
      if (!ref) return;
      const pos = ref.atts.map((a) => this.restSkin.evaluate(a));
      let s = s0;
      const arcs = [s];
      for (let i = 1; i < pos.length; i++) { s += pos[i].distanceTo(pos[i - 1]); arcs.push(s); }
      ref.stopCodes.forEach((code, i) => { if (code && !arcOf.has(code)) arcOf.set(code, arcs[ref.stopIndex[i]] ?? s); });
      if (ci === 0) mainLen = s;
    });
    // transition link: a branch from the exit point to the next channel's entry point
    if (ch.link && this.coords[ch.link.from] && this.coords[ch.link.to]) {
      const s0 = arcOf.get(ch.link.from) ?? mainLen;
      for (const side of sides) {
        const pl = this.layChain([ch.link.from, ch.link.to], side, s0, { link: true, internal: !!ch.link.internal });
        if (pl) polylines.push(pl);
      }
    }
    for (const pl of polylines) pl.channelId = ch.id;
    return { ...ch, sides, polylines, arcOf, mainLen };
  }

  buildOverview() {
    if (this.overview) { this.scene.remove(this.overview); this.overview.geometry.dispose(); }
    this.segRanges = new Map();
    let count = 0;
    for (const [id, ch] of this.channels) {
      if (ch.kind !== 'regular') continue;
      const start = count;
      for (const pl of ch.polylines) if (!pl.link) count += Math.max(0, pl.atts.length - 1);
      this.segRanges.set(id, [start, count]);
    }
    const geom = new LineSegmentsGeometry();
    geom.setPositions(new Float32Array(count * 6));
    geom.setColors(new Float32Array(count * 6));
    this.overviewNormals = setLineNormals(geom, new Float32Array(count * 6));
    this.overview = new LineSegments2(geom, new CasedLineMaterial({ vertexColors: true, linewidth: 2.5 }));
    this.overview.material.uniforms.uUseFace.value = 1;
    this.overview.material.uniforms.uFaceLo.value = 0.1;
    this.overview.material.uniforms.uFaceHi.value = 0.4;
    // depth order toward the camera: all channels 3.5 mm < selected channel 5 mm < flow 6 mm
    this.overview.material.uniforms.uLift.value = 0.0035;
    this.overview.frustumCulled = false;
    this.overview.renderOrder = 1;
    this.scene.add(this.overview);
  }

  buildPoints(channelList) {
    if (this.points) { this.scene.remove(this.points); this.points.geometry.dispose(); }
    const entries = [];
    this.pointIndex.clear();
    for (const ch of channelList) {
      if (ch.kind !== 'regular') continue;
      for (const code of ch.points) {
        for (const side of ch.bilateral ? [1, -1] : [1]) {
          const st = this.restAtt(code, side);
          if (!st?.att) continue;
          this.pointIndex.set(`${code}|${side}`, entries.length);
          entries.push({ code, side, channel: ch.id, att: st.att });
        }
      }
    }
    this.pointEntries = entries;
    const n = entries.length;
    const g = new THREE.BufferGeometry();
    const f = (k) => new THREE.BufferAttribute(new Float32Array(n * k), k);
    for (const [name, k] of [['position', 3], ['normal', 3], ['aColor', 3], ['aCore', 3], ['aRing', 3], ['aArc', 1], ['aState', 1], ['aShape', 1], ['aSize', 1]]) g.setAttribute(name, f(k));
    const mat = new THREE.ShaderMaterial({
      vertexShader: POINTS_VS,
      fragmentShader: POINTS_FS,
      transparent: true,
      depthWrite: false,
      uniforms: { uDpr: { value: this.dpr }, uFlowOn: { value: 1 }, uCamTarget: { value: new THREE.Vector3() }, ...this.flowUniforms },
    });
    this.points = new THREE.Points(g, mat);
    this.points.frustumCulled = false;
    this.points.renderOrder = 3;
    this.scene.add(this.points);
  }

  /** Re-evaluate every attachment on the current body positions. */
  relayout() {
    if (!this.channels.size) return;
    const tmp = new THREE.Vector3();
    for (const ch of this.channels.values()) {
      for (const pl of ch.polylines) {
        pl.positions = pl.atts.map((a) => this.skin.evaluate(a, new THREE.Vector3()));
        pl.normals = pl.atts.map((a) => this.skin.smoothNormal(a, new THREE.Vector3()));
        let s = pl.s0;
        pl.arcs = [s];
        for (let i = 1; i < pl.positions.length; i++) { s += pl.positions[i].distanceTo(pl.positions[i - 1]); pl.arcs.push(s); }
      }
    }
    const arr = this.overview.geometry.attributes.instanceStart.data.array;
    const narr = this.overviewNormals.array;
    let k = 0;
    for (const [id] of this.segRanges) {
      for (const pl of this.channels.get(id).polylines) {
        if (pl.link) continue;
        for (let i = 0; i < pl.positions.length - 1; i++) {
          const a = pl.positions[i];
          const b = pl.positions[i + 1];
          const na = pl.normals[i], nb = pl.normals[i + 1];
          narr[k] = na.x; narr[k + 1] = na.y; narr[k + 2] = na.z; narr[k + 3] = nb.x; narr[k + 4] = nb.y; narr[k + 5] = nb.z;
          arr[k++] = a.x; arr[k++] = a.y; arr[k++] = a.z; arr[k++] = b.x; arr[k++] = b.y; arr[k++] = b.z;
        }
      }
    }
    this.overview.geometry.attributes.instanceStart.data.needsUpdate = true;
    this.overviewNormals.needsUpdate = true;
    const pos = this.points.geometry.attributes.position;
    const nrm = this.points.geometry.attributes.normal;
    const nn = new THREE.Vector3();
    this.pointEntries.forEach((e, i) => {
      this.skin.evaluate(e.att, tmp);
      pos.setXYZ(i, tmp.x, tmp.y, tmp.z);
      this.skin.normal(e.att.tri, nn);
      nrm.setXYZ(i, nn.x, nn.y, nn.z);
    });
    pos.needsUpdate = true;
    nrm.needsUpdate = true;
    this.rebuildLayers();
    this.placeSprites();
    this.requestRender();
  }

  // ----- selection -----

  /**
   * sel: {
   *   level: 'home'|'channel'|'point'|'vessel'|'asana'|'mudra',
   *   channel, point, side, highlight: [ids], pair, fullColor: [ids],
   *   luo: [{from, to, color}], crossings: Map(code -> color), special: bool,
   *   vessel: {id, path, confluent, coupled, coupledColor},
   *   flowChannels: [ids], visiblePoints: Set(codes), contacts: [{codes:[...], colors:[...]}]
   * }
   */
  setSelection(sel) {
    this.selection = sel;
    this.applyStyles();
    this.rebuildLayers();
    this.placeSprites();
    this.requestRender();
  }

  applyStyles() {
    const sel = this.selection;
    // the matcap shades the skin darker than its base colour, so dim towards a slightly darker tone
    const tone = new THREE.Color(BODY_TONE[this.theme]).multiplyScalar(this.theme === 'light' ? 0.6 : 1.15);
    const colors = this.overview.geometry.attributes.instanceColorStart.data.array;
    const level = sel.level || 'home';
    const highlight = new Set(sel.highlight || []);
    const full = new Set(sel.fullColor || []);
    for (const [id, [a, b]] of this.segRanges) {
      const c = new THREE.Color(this.colorOf(id));
      // home: only the active channel is bright, the rest recede (14 bright lines merged into a tangle);
      // the muted lines keep a darker version of their hue instead of turning white
      // on the dark body the muted lines need more muting to recede (round 3: they glowed like neon and the
      // channel active by the clock did not stand out)
      let mix = level === 'home' ? (this.theme === 'dark' ? 0.66 : 0.45) : 0.75;
      if (id === sel.pair) mix = 0.5;
      if (full.has(id) || highlight.has(id)) mix = 0;
      c.lerp(tone, mix);
      for (let i = a; i < b; i++) colors.set([c.r, c.g, c.b, c.r, c.g, c.b], i * 6);
    }
    this.overview.geometry.attributes.instanceColorStart.data.needsUpdate = true;
    // three line weights, about 1 : 2.5 : 5 (overview, a group or pose, one chosen channel), artist round 2
    // home 1.8: at 1.5 the muted lines read as yellow-grey scratches and nearly vanished on the male body (artist round 3)
    this.overview.material.linewidth = level === 'home' ? 1.8 : 1.25;
    // no white casing on the muted overview: on the light theme it made them look like scratches
    this.overview.material.uniforms.uCasing.value = 0;
    this.overview.material.uniforms.uDarkEdge.value = this.theme === 'dark' ? 1 : 0;
    this.overview.visible = true;

    const g = this.points.geometry;
    const A = (name) => g.attributes[name].array;
    const st = A('aState'); const col = A('aColor'); const core = A('aCore'); const ring = A('aRing');
    const arc = A('aArc'); const shape = A('aShape'); const size = A('aSize');
    const vessel = sel.vessel;
    const vesselCodes = vessel ? new Set(vessel.path) : null;
    const vesselArc = vessel ? this.channels.get(vessel.id)?.arcOf : null;
    const vesselColor = vessel ? new THREE.Color(this.colorOf(vessel.id)) : null;
    const crossings = sel.crossings || new Map();
    const visible = sel.visiblePoints || null;
    const flowSet = new Set(sel.flowChannels || []);
    const white = [1, 1, 1];
    this.pointEntries.forEach((e, i) => {
      const own = this.channels.get(e.channel);
      const c = new THREE.Color(this.colorOf(e.channel));
      let state = 0;
      let shp = e.shape || 0;
      let sz = 10 + (shp === 1 ? 1 : 0);   // 7 px was too small to see on a phone
      let coreC = white;
      let ringC = null;
      let a = -1000;
      if (vesselCodes) {
        if (vesselCodes.has(e.code)) {
          state = 2;
          coreC = [c.r, c.g, c.b];
          ringC = vesselColor;
          a = vesselArc?.get(e.code) ?? -1000;
          if (e.code === vessel.confluent || e.code === vessel.coupled) { shp = 2; sz = 12; }
          if (e.code === vessel.coupled && vessel.coupledColor) ringC = new THREE.Color(vessel.coupledColor);
        }
      } else if (visible) {
        // a pose's own points are few and seen from afar: larger markers (10 px read as 8 px specks)
        if (visible.has(e.code)) { state = 2; if (level === 'asana' || level === 'mudra') sz += 3; }
      } else if (sel.channel && e.channel === sel.channel) {
        state = 2;
      }
      if (state === 2 && sel.special && !(e.special)) state = 1;
      if (state >= 1 && !vesselCodes) {
        if (crossings.has(e.code)) ringC = new THREE.Color(crossings.get(e.code));
        if (flowSet.has(e.channel)) a = own?.arcOf.get(e.code) ?? -1000;
      }
      if (sel.point && e.code === sel.point) state = 3;
      st[i] = state;
      col.set([c.r, c.g, c.b], i * 3);
      core.set(coreC, i * 3);
      ring.set(ringC ? [ringC.r, ringC.g, ringC.b] : [0, 0, 0], i * 3);
      arc[i] = a;
      shape[i] = shp;
      size[i] = sz;
    });
    for (const name of ['aState', 'aColor', 'aCore', 'aRing', 'aArc', 'aShape', 'aSize']) g.attributes[name].needsUpdate = true;
  }

  /** Point metadata that changes the marker shape: 1 luo (diamond), 2 vessel key (square); special flag for the filter. */
  setPointMeta(meta) {
    for (const e of this.pointEntries) {
      const m = meta(e.code, e.channel) || {};
      e.shape = m.shape || 0;
      e.special = !!m.special;
    }
  }

  rebuildLayers() {
    for (const key of ['selBase', 'selFlow', 'linkLayer']) {
      const o = this[key];
      if (o) { this.scene.remove(o); o.geometry.dispose(); this[key] = null; }
    }
    const sel = this.selection;
    if (!this.channels.size || !sel) return;
    const flowIds = sel.flowChannels || [];
    const baseIds = new Set([...(sel.highlight || []), ...flowIds]);
    const vesselId = sel.vessel?.id;

    // base lines of the highlighted / selected channels (full colour)
    const basePolys = [];
    for (const id of baseIds) {
      const ch = this.channels.get(id);
      if (!ch || id === vesselId) continue;
      basePolys.push(...ch.polylines.filter((p) => !p.link));
    }
    if (basePolys.length) {
      // home shows the channel active by the clock only as a hint: thinner and a little towards the skin tone.
      // At full weight the bladder line, seen from the front only on the forehead and the little toes, read as
      // two bars of war paint (artist round 3)
      const home = (sel.level || 'home') === 'home';
      const tone = new THREE.Color(BODY_TONE[this.theme]);
      const geom = segmentsGeometry(basePolys, { colors: (pl) => {
        const c = new THREE.Color(this.colorOf(pl.channelId));
        return home ? c.lerp(tone, 0.2) : c;
      } });
      // poses: the whole figure is in view, so the lines are thin on screen; 2.5 px yellow and green lines
      // were lost on the skin (UX council 2026-11-12), the hand close-ups of the mudras need less
      const group = baseIds.size > 1;
      this.selBase = new LineSegments2(geom, new CasedLineMaterial({ vertexColors: true, linewidth: home ? 2.0 : 3.0 }));
      // one chosen channel is never faded: on the inner forearm seen from the front it is only visible at the
      // silhouette, and fading it there hid most of the heart line. Several channels (a pose, a group) fade on
      // skin turning away down to 35 %: unfaded they outlined the trunk like a comic (artist round 2)
      this.selBase.material.uniforms.uUseFace.value = group && geom.userData.hasFace ? 1 : 0;
      this.selBase.material.uniforms.uFaceLo.value = 0.0;
      this.selBase.material.uniforms.uFaceHi.value = 0.3;
      this.selBase.material.uniforms.uFaceFloor.value = 0.35;
      this.selBase.material.uniforms.uLift.value = 0.005;
      this.selBase.material.uniforms.uCasing.value = this.theme === 'light' ? (home ? 0.3 : 0.55) : 0;
      this.selBase.material.uniforms.uDarkEdge.value = this.theme === 'dark' ? 1 : 0;
      this.selBase.renderOrder = 2;
    }
    if (vesselId) {
      const ch = this.channels.get(vesselId);
      const geom = segmentsGeometry(ch.polylines, { withDistance: true });
      if (geom) {
        const vb = new LineSegments2(geom, new CasedLineMaterial({ color: new THREE.Color(this.colorOf(vesselId)), linewidth: 3.0, beads: true, transparent: true }));
        vb.material.uniforms.uCasing.value = this.theme === 'light' ? 0.4 : 0;
        vb.material.uniforms.uUseFace.value = 0;
        vb.material.uniforms.uLift.value = 0.005;
        vb.renderOrder = 2;
        if (this.selBase) { this.scene.remove(this.selBase); this.selBase.geometry.dispose(); }
        this.selBase = vb;
      }
    }

    // flow layer: selected channels incl. branches and the transition link
    // several channels (sel.nextOf): a transition link is drawn only when it leads to another chosen channel
    const flowSet = new Set(flowIds);
    const linkShown = (id) => !sel.nextOf || flowSet.has(sel.nextOf[id]);
    const flowPolys = [];
    for (const id of flowIds) {
      const ch = this.channels.get(id);
      if (ch) flowPolys.push(...ch.polylines.filter((p) => !p.link || linkShown(id)));
    }
    if (flowPolys.length) {
      const geom = segmentsGeometry(flowPolys, { withDistance: true, colors: (pl) => new THREE.Color(this.colorOf(pl.channelId)) });
      const mat = new FlowLineMaterial({ vertexColors: true, linewidth: 6 }, this.flowUniforms);
      mat.uniforms.uWhite.value = this.theme === 'dark' ? 0.6 : 0.25;
      mat.uniforms.uUseFace.value = 0;
      if (this.theme === 'dark') mat.blending = THREE.AdditiveBlending;
      this.selFlow = new LineSegments2(geom, mat);
      this.selFlow.renderOrder = 4;
    }

    // dashed links: luo arcs and transition links of the selected channel
    const linkPolys = [];
    for (const l of sel.luo || []) {
      for (const side of [1, -1]) {
        const a = this.restAtt(l.from, side);
        const b = this.restAtt(l.to, side);
        if (!a?.att || !b?.att) continue;
        const key = `${l.from}>${l.to}|${side}`;
        if (!this.luoCache) this.luoCache = new Map();
        if (!this.luoCache.has(key)) this.luoCache.set(key, this.restSkin.layCurve([a, b], 0.005, { quiet: true }).atts);
        const positions = this.luoCache.get(key).map((x) => this.skin.evaluate(x, new THREE.Vector3()));
        linkPolys.push({ positions, color: new THREE.Color(l.color), strong: l.strong });
      }
    }
    for (const id of flowIds) {
      const ch = this.channels.get(id);
      if (!linkShown(id)) continue;
      for (const pl of ch?.polylines || []) {
        if (!pl.link) continue;
        const next = new THREE.Color(this.colorOf(sel.nextOf?.[id] || sel.nextChannel || id));
        if (pl.internal) next.lerp(new THREE.Color(BODY_TONE[this.theme]), 0.55);
        linkPolys.push({ positions: pl.positions, color: next });
      }
    }
    if (linkPolys.length) {
      const segs = [];
      const cols = [];
      const dist = [];
      for (const lp of linkPolys) {
        let s = 0;
        for (let i = 0; i < lp.positions.length - 1; i++) {
          const a = lp.positions[i];
          const b = lp.positions[i + 1];
          segs.push(a.x, a.y, a.z, b.x, b.y, b.z);
          cols.push(lp.color.r, lp.color.g, lp.color.b, lp.color.r, lp.color.g, lp.color.b);
          const d = a.distanceTo(b);
          dist.push(s, s + d);
          s += d;
        }
      }
      const geom = new LineSegmentsGeometry();
      geom.setPositions(segs);
      geom.setColors(cols);
      const buf = new THREE.InstancedInterleavedBuffer(new Float32Array(dist), 2, 1);
      geom.setAttribute('instanceDistanceStart', new THREE.InterleavedBufferAttribute(buf, 1, 0));
      geom.setAttribute('instanceDistanceEnd', new THREE.InterleavedBufferAttribute(buf, 1, 1));
      const mat = new CasedLineMaterial({ vertexColors: true, linewidth: 2, dashedLink: true, dashSize: 0.006, gapSize: 0.004 });
      mat.uniforms.uCasing.value = this.theme === 'light' ? 0.35 : 0;
      mat.uniforms.uLift.value = 0.005;
      this.linkLayer = new LineSegments2(geom, mat);
      this.linkLayer.renderOrder = 2;
    }
    for (const o of [this.selBase, this.selFlow, this.linkLayer]) {
      if (!o) continue;
      o.frustumCulled = false;
      this.scene.add(o);
    }
    this.resizeLineMaterials();
  }

  placeSprites() {
    const sel = this.selection;
    for (const h of this.halos) h.visible = false;
    if (sel.point && this.points) {
      const ch = this.channels.get(sel.channel);
      const side = sel.side || 1;
      const sides = ch?.bilateral ? [side, -side] : [1];
      sides.forEach((s, i) => {
        const pp = this.pointPosition(sel.point, s);
        if (!pp) return;
        const h = this.halos[i];
        h.position.copy(pp.p).addScaledVector(pp.n, 0.004);
        h.material.color.set(this.colorOf(sel.channel));
        h.material.opacity = i === 0 ? 1 : 0.6;
        h.userData.base = i === 0 ? 1 : 0.6;
        h.visible = true;
      });
    }
    const groups = sel.contacts || [];
    while (this.contactSprites.length < groups.length) this.contactSprites.push(this.makeSprite(6));
    this.contactSprites.forEach((s, i) => {
      const g = groups[i];
      s.visible = false;
      if (!g) return;
      const box = [];
      for (const code of g.codes) {
        const pp = this.pointPosition(code, g.side ?? 1);
        if (pp) box.push(pp);
      }
      if (!box.length) return;
      const c = box.reduce((acc, pp) => acc.add(pp.p), new THREE.Vector3()).multiplyScalar(1 / box.length);
      const n = box.reduce((acc, pp) => acc.add(pp.n), new THREE.Vector3()).normalize();
      s.position.copy(c).addScaledVector(n, 0.006);
      s.material.color.set(g.color || '#ffffff');
      s.userData.base = 0.75;
      s.userData.codes = g.codes;
      s.visible = true;
    });
  }

  /**
   * A cun ruler from point `from` to point `to`: a line just above the skin with a mark at every cun
   * (and the last mark at a half cun when the distance is 1.5, 2.5…). Drawn over the body so it is not
   * hidden by the curve of a limb. Returns {box, normal} to frame it, or null.
   */
  showRuler(from, to, cun, side = 1) {
    this.clearRuler();
    const a = this.pointPosition(from, side);
    const b = this.pointPosition(to, side);
    if (!a || !b || !(cun > 0)) return null;
    const lift = (pp) => pp.p.clone().addScaledVector(pp.n, 0.004);
    const pa = lift(a);
    const pb = lift(b);
    const group = new THREE.Group();
    const ink = 0x1b1b1f;
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([pa, pb]),
      new THREE.LineBasicMaterial({ color: ink, depthTest: false, transparent: true, opacity: 0.9 }));
    line.renderOrder = 30;
    group.add(line);
    const marks = [];
    for (let i = 0; i <= Math.floor(cun + 1e-6); i++) marks.push(i);
    if (cun - Math.floor(cun) > 1e-6) marks.push(cun);
    const dotGeo = new THREE.SphereGeometry(1, 12, 8);
    for (const m of marks) {
      const end = m === 0 || Math.abs(m - cun) < 1e-6;
      const dot = new THREE.Mesh(dotGeo, new THREE.MeshBasicMaterial({ color: end ? ink : 0xffffff, depthTest: false, transparent: true }));
      dot.scale.setScalar(end ? 0.0045 : 0.0032);
      dot.position.copy(pa).lerp(pb, m / cun);
      dot.renderOrder = 31;
      group.add(dot);
      if (!end) {
        const rim = new THREE.Mesh(dotGeo, new THREE.MeshBasicMaterial({ color: ink, depthTest: false, transparent: true }));
        rim.scale.setScalar(0.0042);
        rim.position.copy(dot.position);
        rim.renderOrder = 30;
        group.add(rim);
      }
    }
    this.ruler = group;
    this.scene.add(group);
    this.requestRender();
    return { box: new THREE.Box3().setFromPoints([pa, pb]), normal: a.n.clone().add(b.n).normalize() };
  }

  clearRuler() {
    if (!this.ruler) return;
    this.scene.remove(this.ruler);
    this.ruler.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
    this.ruler = null;
    this.requestRender();
  }

  pointPosition(code, side = 1) {
    let idx = this.pointIndex.get(`${code}|${side}`);
    if (idx == null) idx = this.pointIndex.get(`${code}|1`);
    if (idx == null) return null;
    const pos = this.points.geometry.attributes.position;
    const nrm = this.points.geometry.attributes.normal;
    return {
      p: new THREE.Vector3(pos.getX(idx), pos.getY(idx), pos.getZ(idx)),
      n: new THREE.Vector3(nrm.getX(idx), nrm.getY(idx), nrm.getZ(idx)),
    };
  }

  // ----- flow -----

  /** mode: 'comet' | 'wave' | 'breath'; L = main chain length, Lend = max arc incl. branches. */
  startFlow({ mode = 'comet', slow = false, once = false } = {}) {
    const ids = this.selection.flowChannels || [];
    if (!ids.length && !this.selection.vessel) return;
    let L = 0;
    let Lend = 0;
    for (const id of [...ids, this.selection.vessel?.id].filter(Boolean)) {
      const ch = this.channels.get(id);
      if (!ch) continue;
      // L: longest path through the channel itself (branches start at their fork arc), Lend: incl. the transition link
      L = Math.max(L, ch.polylines.filter((p) => !p.link).reduce((m, p) => Math.max(m, p.arcs[p.arcs.length - 1]), 0));
      Lend = Math.max(Lend, ...ch.polylines.map((p) => p.arcs[p.arcs.length - 1]));
    }
    const u = this.flowUniforms;
    let v = mode === 'comet' ? THREE.MathUtils.clamp(L / 9, 0.11, 0.18) : 0.12;
    if (slow) v /= 1.5;
    this.flow = { ...this.flow, mode, v, playing: true, time: 0, once, passes: 0, Lend, period: (Lend + v * (mode === 'wave' ? 2 : 1.5)) / v };
    u.uTail.value = THREE.MathUtils.clamp(0.15 * L, 0.08, 0.22);
    u.uWave.value = mode === 'wave' ? 1 : 0;
    u.uConst.value = mode === 'breath' ? 1 : 0;
    u.uHeadS.value = -1;
    this.fadeUniform(u.uIntensity, u.uIntensity.value, 1, 300, 150);
  }

  stopFlow(immediate = false) {
    const u = this.flowUniforms;
    if (immediate) {
      u.uIntensity.value = 0;
      this.flow.playing = false;
      this.requestRender();
      return;
    }
    this.fadeUniform(u.uIntensity, u.uIntensity.value, 0, 200, 0, () => { this.flow.playing = false; });
  }

  get flowPlaying() { return this.flow.playing; }

  fadeUniform(uniform, from, to, ms, delay = 0, onEnd) {
    this.flow.fades = this.flow.fades.filter((f) => f.uniform !== uniform);
    this.flow.fades.push({ uniform, from, to, ms, t0: performance.now() + delay, onEnd });
    this.requestRender();
  }

  // ----- camera -----

  fitDistance(height = 1.8, width = 1.15) {
    const vp = this.getViewport();
    const h = window.innerHeight;
    const w = window.innerWidth - (vp.right || 0);
    const free = Math.max(0.35, (h - vp.top - vp.bottom) / h);
    const tanHalf = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    return Math.max(height / (2 * free * tanHalf), width / (2 * tanHalf * (w / h)), 1.2);
  }

  flyTo(target, position, { onEnd, ms } = {}) {
    const s0 = new THREE.Spherical().setFromVector3(new THREE.Vector3().subVectors(this.camera.position, this.controls.target));
    const s1 = new THREE.Spherical().setFromVector3(new THREE.Vector3().subVectors(position, target));
    let dTheta = s1.theta - s0.theta;
    dTheta = Math.atan2(Math.sin(dTheta), Math.cos(dTheta));
    const angle = Math.hypot(dTheta, s1.phi - s0.phi);
    const zoom = Math.abs(Math.log(s1.radius / Math.max(1e-3, s0.radius)));
    const dur = ms ?? (reducedMotion.matches ? 120 : THREE.MathUtils.clamp(380 + (320 * angle) / Math.PI + 220 * zoom, 400, 1000));
    this.tween = { t0: performance.now(), ms: dur, fromT: this.controls.target.clone(), toT: target.clone(), s0, dTheta, phi1: s1.phi, r1: s1.radius, onEnd };
    this.requestRender();
  }

  bodyCenter() {
    this.body.geometry.computeBoundingBox();
    const bb = this.body.geometry.boundingBox;
    return { center: bb.getCenter(new THREE.Vector3()), size: bb.getSize(new THREE.Vector3()) };
  }

  setView(name, opts = {}) {
    const { center, size } = this.bodyCenter();
    const d = this.fitDistance(size.y + 0.15, size.x * 0.95 + 0.15);
    this.controls.maxDistance = d * 1.3;
    const dirs = { front: [0, 0.12, 1], back: [0, 0.12, -1], left: [1, 0.12, 0], right: [-1, 0.12, 0] };
    const dv = new THREE.Vector3(...(dirs[name] || dirs.front)).normalize().multiplyScalar(d);
    if (opts.instant) {
      this.controls.target.copy(center);
      this.camera.position.copy(center).add(dv);
      this.requestRender();
      return;
    }
    this.flyTo(center, center.clone().add(dv), opts);
  }

  frameBox(box, dir, opts = {}) {
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, opts.minRadius || 0.1);
    const vp = this.getViewport();
    const free = Math.max(0.35, (window.innerHeight - vp.top - vp.bottom) / window.innerHeight);
    const tanHalf = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    const aspect = (window.innerWidth - (vp.right || 0)) / window.innerHeight;
    // height and width fitted separately (the diagonal alone pushed a standing mudra 5.6 m away on a
    // narrow phone once the button column was left out of the free area); never farther than before
    // extents as the camera sees them: the box corners projected on its right / up / view axes
    const d = dir.clone().normalize();
    const right = new THREE.Vector3(0, 1, 0).cross(d);
    if (right.lengthSq() < 1e-6) right.set(1, 0, 0);
    right.normalize();
    const up = d.clone().cross(right).normalize();
    let halfW = 0, halfH = 0, halfD = 0;
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
      const v = new THREE.Vector3(x, y, z).sub(center);
      halfW = Math.max(halfW, Math.abs(v.dot(right)));
      halfH = Math.max(halfH, Math.abs(v.dot(up)));
      halfD = Math.max(halfD, Math.abs(v.dot(d)));
    }
    const fit = (Math.max(halfH / (tanHalf * free), halfW / (tanHalf * aspect)) + halfD) * 1.08;
    const old = (radius / (tanHalf * free * Math.min(1, aspect * 1.4))) * 1.05;
    const dist = THREE.MathUtils.clamp(Math.min(old, fit), opts.minDist || 0.3, this.fitDistance() * 1.1);
    const pos = center.clone().addScaledVector(dir.clone().normalize(), dist);
    if (opts.instant) {
      this.controls.target.copy(center);
      this.camera.position.copy(pos);
      this.requestRender();
      opts.onEnd?.();
      return;
    }
    this.flyTo(center, pos, opts);
  }

  channelBox(id, side = null) {
    const ch = this.channels.get(id);
    const box = new THREE.Box3();
    if (!ch) return box;
    for (const pl of ch.polylines) if (!pl.link && (side == null || pl.side === side)) for (const p of pl.positions) box.expandByPoint(p);
    return box;
  }

  focusPoint(code, side, opts = {}) {
    const pp = this.pointPosition(code, side);
    if (!pp) return;
    const dir = pp.n.clone().multiplyScalar(0.8).add(new THREE.Vector3(0, 0.2, 0)).normalize();
    const pos = pp.p.clone().addScaledVector(dir, opts.distance || 0.5);
    if (opts.instant) {
      this.controls.target.copy(pp.p);
      this.camera.position.copy(pos);
      this.requestRender();
      opts.onEnd?.();
      return;
    }
    this.flyTo(pp.p, pos, opts);
  }

  sideFacingCamera(code) {
    let best = 1;
    let bestDot = -Infinity;
    for (const side of [1, -1]) {
      const pp = this.pointPosition(code, side);
      if (!pp) continue;
      const d = this.camera.position.clone().sub(pp.p).normalize().dot(pp.n);
      if (d > bestDot) { bestDot = d; best = side; }
    }
    return best;
  }

  // ----- picking -----

  toScreen(v, out = new THREE.Vector3()) {
    out.copy(v).project(this.camera);
    return [((out.x + 1) / 2) * window.innerWidth, ((1 - out.y) / 2) * window.innerHeight, out.z];
  }

  isVisible(p, n, min = 0.1) {
    const toCam = this.camera.position.clone().sub(p).normalize();
    return toCam.dot(n) > min;
  }

  /** True when nothing of the body lies between the camera and p (BVH ray). */
  unoccluded(p) {
    this.refitBvh();
    const from = this.camera.position;
    const dir = p.clone().sub(from);
    const dist = dir.length();
    const rc = new THREE.Raycaster(from, dir.normalize(), 0, dist);
    rc.firstHitOnly = true;
    const hit = rc.intersectObject(this.body, false)[0];
    return !hit || hit.distance > dist - 0.006;
  }

  bodyHit(x, y) {
    this.refitBvh();
    const ndc = new THREE.Vector2((x / window.innerWidth) * 2 - 1, -(y / window.innerHeight) * 2 + 1);
    const rc = new THREE.Raycaster();
    rc.setFromCamera(ndc, this.camera);
    return rc.intersectObject(this.body, false)[0] || null;
  }

  pick(x, y, { pointsEnabled = true } = {}) {
    const hit = this.bodyHit(x, y);
    const bodyDist = hit ? hit.distance : Infinity;
    const tmp = new THREE.Vector3();
    if (pointsEnabled) {
      const pos = this.points.geometry.attributes.position;
      const st = this.points.geometry.attributes.aState.array;
      const near = [];
      for (let i = 0; i < this.pointEntries.length; i++) {
        if (st[i] < 1) continue;
        tmp.set(pos.getX(i), pos.getY(i), pos.getZ(i));
        if (this.camera.position.distanceTo(tmp) > bodyDist + 0.015) continue;
        const [sx, sy, sz] = this.toScreen(tmp);
        if (sz > 1) continue;
        const d = Math.hypot(sx - x, sy - y);
        if (d < 24) near.push({ d, i, sx, sy });
      }
      near.sort((a, b) => a.d - b.d);
      if (near.length) {
        if (near.length >= 2 && Math.hypot(near[0].sx - near[1].sx, near[0].sy - near[1].sy) < 12) {
          return { type: 'cluster', hit, candidates: near.slice(0, 4).map((n) => this.pointEntries[n.i]) };
        }
        const e = this.pointEntries[near[0].i];
        return { type: 'point', channel: e.channel, code: e.code, side: e.side, hit };
      }
    }
    let best = null;
    let bestD = 16;
    const sel = this.selection;
    const focus = sel.channel || sel.vessel?.id;
    for (const [id, ch] of this.channels) {
      if (ch.kind !== 'regular' && id !== focus) continue;
      for (const pl of ch.polylines) {
        if (pl.link && id !== focus) continue;
        for (let i = 0; i < pl.positions.length; i += 3) {
          const v = pl.positions[i];
          if (this.camera.position.distanceTo(v) > bodyDist + 0.012) continue;
          const [sx, sy] = this.toScreen(v);
          let d = Math.hypot(sx - x, sy - y);
          if (focus && id !== focus) d += 4;
          if (d < bestD) { bestD = d; best = { type: pl.link ? 'link' : 'line', channel: id, side: pl.side, hit }; }
        }
      }
    }
    if (best) return best;
    return { type: 'none', hit };
  }

  // ----- frame loop -----

  resizeLineMaterials() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    for (const o of [this.overview, this.selBase, this.selFlow, this.linkLayer]) o?.material.resolution.set(w, h);
  }

  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    const vp = this.getViewport();
    // centre the picture in the free area: above the sheet, left of the button column
    this.camera.setViewOffset(w, h, Math.round((vp.right || 0) / 2), Math.round((vp.bottom - vp.top) / 2), w, h);
    this.camera.updateProjectionMatrix();
    this.resizeLineMaterials();
    this.requestRender();
  }

  loop(now) {
    requestAnimationFrame(this.loop);
    const dt = Math.min(0.05, (now - this.lastFrame) / 1000);
    this.lastFrame = now;
    let animating = false;

    if (this.tween) {
      const tw = this.tween;
      const k = Math.min(1, (now - tw.t0) / tw.ms);
      const e = easeInOutCubic(k);
      this.controls.target.lerpVectors(tw.fromT, tw.toT, e);
      const s = new THREE.Spherical(
        tw.s0.radius * Math.pow(tw.r1 / Math.max(1e-3, tw.s0.radius), e),
        THREE.MathUtils.lerp(tw.s0.phi, tw.phi1, e),
        tw.s0.theta + tw.dTheta * e,
      );
      this.camera.position.setFromSpherical(s).add(this.controls.target);
      animating = true;
      if (k >= 1) { this.tween = null; tw.onEnd?.(); }
    }
    for (const f of [...this.flow.fades]) {
      animating = true;
      if (now < f.t0) continue;
      const k = THREE.MathUtils.clamp((now - f.t0) / f.ms, 0, 1);
      f.uniform.value = f.from + (f.to - f.from) * easeInOutCubic(k);
      if (k >= 1) {
        this.flow.fades.splice(this.flow.fades.indexOf(f), 1);
        f.onEnd?.();
      }
    }
    const fl = this.flow;
    if (fl.playing && !this.paused) {
      fl.time += dt;
      const u = this.flowUniforms;
      if (fl.mode === 'breath') {
        u.uIntensity.value = 0.45 + 0.55 * (0.5 - 0.5 * Math.cos((2 * Math.PI * fl.time) / 5));
      } else {
        const passes = Math.floor(fl.time / fl.period);
        if (passes > fl.passes) {
          fl.passes = passes;
          this.onFlowPass?.(passes);
          if (fl.once) { this.stopFlow(); }
        }
        u.uHeadS.value = fl.v * (fl.time % fl.period);
      }
      animating = true;
    }
    if (this.onFrame?.(now, dt)) animating = true;
    const breathe = !reducedMotion.matches && !this.idle;
    const pulse = breathe ? 1 + 0.125 * (1 - Math.cos((now / 2400) * Math.PI * 2)) : 1;
    for (const h of [...this.halos, ...this.contactSprites]) {
      if (!h.visible) continue;
      const dist = this.camera.position.distanceTo(h.position);
      h.scale.setScalar(0.024 * dist * pulse * (h.userData.base || 1));
      if (breathe) animating = true;
    }
    const camDist = this.camera.position.distanceTo(this.controls.target);
    this.shadow.material.opacity = THREE.MathUtils.smoothstep(camDist, 1.2, 2.5);
    if (this.controls.update()) animating = true;
    if (animating || this.needsRender) {
      this.renderer.render(this.scene, this.camera);
      this.needsRender = false;
      this.onRendered?.();
    }
  }
}
