/**
 * three.js view of a MuJoCo model.
 *
 * Builds one mesh per geom and per cylinder site in the loaded model, then on
 * every frame copies MuJoCo's own world transforms (geom_xpos/geom_xmat,
 * site_xpos/site_xmat) onto them. Nothing about the scene is hard-coded, so the
 * view follows whatever the MJCF says — swap the model file and the picture
 * follows.
 */

import * as THREE from '../../vendor/three/three.module.min.js';
import { OrbitControls } from '../../vendor/three/OrbitControls.js';

/** Embind enums arrive as objects; the C functions want the plain int. */
export const enumValue = (entry) => (typeof entry === 'number' ? entry : entry.value);

/** mjtGeom values we draw. Anything else is skipped. */
const PLANE = 0;
const SPHERE = 2;
const CAPSULE = 3;
const CYLINDER = 5;
const BOX = 6;

/** MuJoCo's cylinders and capsules run along local z; three.js builds them along y. */
function alongZ(geometry) {
  geometry.rotateX(Math.PI / 2);
  return geometry;
}

function checkerTexture() {
  const size = 256;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#575f6a';
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = '#39404a';
  ctx.fillRect(0, 0, size / 2, size / 2);
  ctx.fillRect(size / 2, size / 2, size / 2, size / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(6, 6);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function materialFor(rgba, isFloor) {
  const [r, g, b, a] = rgba;
  const options = {
    color: new THREE.Color(r, g, b),
    roughness: isFloor ? 0.95 : 0.55,
    metalness: 0.0,
  };
  if (isFloor) {
    options.map = checkerTexture();
    options.color = new THREE.Color(1, 1, 1);
  }
  if (a < 1) {
    options.transparent = true;
    options.opacity = a;
    options.depthWrite = false;
  }
  return new THREE.MeshStandardMaterial(options);
}

function geometryFor(type, size) {
  switch (type) {
    case PLANE: {
      // size = (x half-extent, y half-extent, grid spacing); 0 means infinite,
      // which we cap so the ground stays a finite, sensible patch.
      const halfX = size[0] > 0 ? size[0] : 12;
      const halfY = size[1] > 0 ? size[1] : 12;
      return new THREE.PlaneGeometry(halfX * 2, halfY * 2);
    }
    case SPHERE:
      return new THREE.SphereGeometry(size[0], 24, 16);
    case CAPSULE:
      return alongZ(new THREE.CapsuleGeometry(size[0], size[1] * 2, 6, 12));
    case CYLINDER:
      return alongZ(new THREE.CylinderGeometry(size[0], size[0], size[1] * 2, 28));
    case BOX:
      return new THREE.BoxGeometry(size[0] * 2, size[1] * 2, size[2] * 2);
    default:
      return null;
  }
}

export class MujocoView {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} model  MjModel
   * @param {object} mujoco the loaded WASM module (for name lookups)
   */
  constructor(canvas, model, mujoco) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;

    this.scene = new THREE.Scene();
    // MuJoCo is z-up; make three.js agree so no coordinates need swapping.
    this.scene.up.set(0, 0, 1);

    // Framed on the wall face and the vehicle in front of it, from the near
    // side so the wheel-wall contact is the thing you are looking at.
    this.camera = new THREE.PerspectiveCamera(42, 16 / 9, 0.05, 100);
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(0.55, -2.35, 1.70);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(1.80, 0, 1.10);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.495; // never go under the floor
    this.controls.minDistance = 0.9;
    this.controls.maxDistance = 9;
    this.controls.update();

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.15));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(2.5, -3.5, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    const s = 5;
    Object.assign(key.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 0.5, far: 20 });
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-3, 2, 3);
    this.scene.add(fill);

    this.geomMeshes = this._buildGeoms(model, mujoco);
    this.siteMeshes = this._buildSites(model, mujoco);
    this.setBackground('light');
  }

  _buildGeoms(model, mujoco) {
    const meshes = [];
    const type = model.geom_type;
    const size = model.geom_size;
    const rgba = model.geom_rgba;
    for (let i = 0; i < model.ngeom; i += 1) {
      const t = type[i];
      const half = [size[i * 3], size[i * 3 + 1], size[i * 3 + 2]];
      const geometry = geometryFor(t, half);
      if (!geometry) continue;
      const colour = [rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2], rgba[i * 4 + 3]];
      const name = mujoco.mj_id2name(model, enumValue(mujoco.mjtObj.mjOBJ_GEOM), i) || '';
      const isFloor = t === PLANE;
      const mesh = new THREE.Mesh(geometry, materialFor(colour, isFloor));
      mesh.matrixAutoUpdate = false;
      mesh.castShadow = !isFloor;
      mesh.receiveShadow = true;
      mesh.name = name;
      this.scene.add(mesh);
      meshes.push({ index: i, mesh });
    }
    return meshes;
  }

  /** Rotor discs are sites, not geoms — without them the vehicle reads as a brick. */
  _buildSites(model, mujoco) {
    const meshes = [];
    const type = model.site_type;
    const size = model.site_size;
    const rgba = model.site_rgba;
    for (let i = 0; i < model.nsite; i += 1) {
      const t = type[i];
      if (t !== CYLINDER && t !== SPHERE) continue;
      const geometry = geometryFor(t, [size[i * 3], size[i * 3 + 1], size[i * 3 + 2]]);
      if (!geometry) continue;
      const colour = [rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2], rgba[i * 4 + 3]];
      const mesh = new THREE.Mesh(geometry, materialFor(colour, false));
      mesh.matrixAutoUpdate = false;
      mesh.castShadow = false;
      mesh.name = mujoco.mj_id2name(model, enumValue(mujoco.mjtObj.mjOBJ_SITE), i) || '';
      this.scene.add(mesh);
      meshes.push({ index: i, mesh });
    }
    return meshes;
  }

  /** Copy a MuJoCo world transform (row-major 3x3 + position) onto a mesh. */
  static _applyTransform(mesh, pos, mat, base) {
    mesh.matrix.set(
      mat[base * 9 + 0], mat[base * 9 + 1], mat[base * 9 + 2], pos[base * 3 + 0],
      mat[base * 9 + 3], mat[base * 9 + 4], mat[base * 9 + 5], pos[base * 3 + 1],
      mat[base * 9 + 6], mat[base * 9 + 7], mat[base * 9 + 8], pos[base * 3 + 2],
      0, 0, 0, 1,
    );
    mesh.matrixWorldNeedsUpdate = true;
  }

  /** Pull this frame's poses out of MjData. */
  sync(data) {
    const gp = data.geom_xpos;
    const gm = data.geom_xmat;
    for (const { index, mesh } of this.geomMeshes) MujocoView._applyTransform(mesh, gp, gm, index);
    const sp = data.site_xpos;
    const sm = data.site_xmat;
    for (const { index, mesh } of this.siteMeshes) MujocoView._applyTransform(mesh, sp, sm, index);
  }

  setBackground(theme) {
    const colour = theme === 'dark' ? 0x2f2f2f : 0xdfe3e8;
    this.scene.background = new THREE.Color(colour);
    this.scene.fog = new THREE.Fog(colour, 9, 22);
  }

  resize() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (width === 0 || height === 0) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }

  render() {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    this.controls.dispose();
    this.renderer.dispose();
  }
}
