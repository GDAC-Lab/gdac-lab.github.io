/**
 * Draws the vehicle with the lab's own CAD instead of MuJoCo's collision boxes.
 *
 * The bundle is built by scripts/build_drone_mesh.py from the STL files in
 * assets/models/wheeled-uav/meshes/ and carries, in its header, everything
 * needed to place a part: which primitive each mesh stands in for, the rotor
 * stations, and the wheel scale. Nothing about the vehicle is hard-coded here.
 *
 * Placement rides MuJoCo's own transforms rather than re-deriving kinematics:
 * a geom's world pose, with the geom's fixed orientation inside its body
 * divided out, is that body's pose. So the frame follows the chassis and each
 * wheel follows its hinge — including the rolling angle — for free. The rotors
 * are the one exception: the model has no rotor joint, so their spin is drawn.
 *
 * If anything here fails the caller keeps the primitives, so a missing or
 * broken bundle costs the demo nothing but the nicer picture.
 */

import * as THREE from '../../vendor/three/three.module.min.js';

const MAGIC = 'GDACMSH1';

/** Cosmetic rotor spin, in revolutions per second. */
const SPIN_IDLE = 2.5;
const SPIN_PER_NEWTON = 0.35;
// Three blades repeat every 120 deg, so past ~10 rev/s at 60 fps the rotation
// aliases and the blades appear to crawl backwards. Stay under that: the demo
// is explaining a controller, not selling a drone.
const SPIN_MAX = 8;

export async function loadDroneMesh(url) {
  const response = await fetch(url, { cache: 'force-cache' });
  if (!response.ok) throw new Error(`drone mesh: HTTP ${response.status}`);
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength < 12) throw new Error('drone mesh: truncated');
  const magic = new TextDecoder().decode(new Uint8Array(buffer, 0, 8));
  if (magic !== MAGIC) throw new Error(`drone mesh: not a mesh bundle (${magic})`);
  const headerLength = new DataView(buffer).getUint32(8, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 12, headerLength)));
  const base = 12 + headerLength;

  const geometries = {};
  for (const [name, part] of Object.entries(header.parts)) {
    const [po, pn] = part.positions;
    const [no, nn] = part.normals;
    const [io, ic] = part.indices;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(buffer, base + po, pn), 3),
    );
    geometry.setAttribute(
      'normal',
      new THREE.BufferAttribute(new Int8Array(buffer, base + no, nn), 3, true),
    );
    geometry.setIndex(new THREE.BufferAttribute(new Uint16Array(buffer, base + io, ic), 1));
    geometry.computeBoundingSphere();
    geometries[name] = geometry;
  }
  return { header, geometries };
}

/** MuJoCo stores quaternions w-first; three.js wants them last. */
function quatAt(array, index) {
  if (!array) return new THREE.Quaternion();
  const w = array[index * 4];
  const x = array[index * 4 + 1];
  const y = array[index * 4 + 2];
  const z = array[index * 4 + 3];
  const q = new THREE.Quaternion(x, y, z, w);
  return q.lengthSq() > 0 ? q.normalize() : new THREE.Quaternion();
}

function vec3At(array, index) {
  if (!array) return new THREE.Vector3();
  return new THREE.Vector3(array[index * 3], array[index * 3 + 1], array[index * 3 + 2]);
}

export class DroneMesh {
  /**
   * @param {import('./scene.js').MujocoView} view
   * @param {{header: object, geometries: object}} bundle
   * @param {object} model MjModel
   * @param {object} mujoco the loaded WASM module, for name lookups
   */
  constructor(view, bundle, model, mujoco) {
    const { header, geometries } = bundle;
    const layout = header.layout;
    const geomId = (name) =>
      mujoco.mj_name2id(model, typeof mujoco.mjtObj.mjOBJ_GEOM === 'number'
        ? mujoco.mjtObj.mjOBJ_GEOM : mujoco.mjtObj.mjOBJ_GEOM.value, name);

    this.view = view;
    this.model = model;
    this.parts = [];
    this.rotors = [];
    this.hidden = [];
    this.spinPhase = 0;

    // Lifted well off the real carbon black: the vehicle has to read against
    // the light background, the dark one and the pink wall alike.
    const frameMaterial = new THREE.MeshStandardMaterial({
      color: new THREE.Color(0x646c76), roughness: 0.52, metalness: 0.30,
    });
    // The wheels are what the demo is about, so they stay the one saturated
    // part of the vehicle rather than going carbon-black like the real tyre.
    const wheelMaterial = new THREE.MeshStandardMaterial({
      color: new THREE.Color(0x3d6bb5), roughness: 0.62, metalness: 0.08,
    });
    const rotorMaterial = new THREE.MeshStandardMaterial({
      color: new THREE.Color(0xb4bcc5), roughness: 0.58, metalness: 0.05,
    });
    this.materials = [frameMaterial, wheelMaterial, rotorMaterial];

    // ---- chassis, and the rotors that ride with it -------------------------
    const bodyGeom = geomId(layout.bodyGeom);
    if (bodyGeom < 0) throw new Error(`drone mesh: no geom named ${layout.bodyGeom}`);
    this.bodyGroup = new THREE.Group();
    this.bodyGroup.matrixAutoUpdate = false;
    view.scene.add(this.bodyGroup);
    this.bodyRef = this._reference(bodyGeom);

    const frame = new THREE.Mesh(geometries.frame, frameMaterial);
    frame.castShadow = true;
    frame.receiveShadow = true;
    this.bodyGroup.add(frame);

    for (const prop of layout.props) {
      const geometry = geometries[prop.mesh];
      if (!geometry) continue;
      const mesh = new THREE.Mesh(geometry, rotorMaterial);
      mesh.position.fromArray(prop.pos);
      mesh.castShadow = true;
      this.bodyGroup.add(mesh);
      let actuator = -1;
      if (mujoco.mjtObj.mjOBJ_ACTUATOR !== undefined) {
        const kind = typeof mujoco.mjtObj.mjOBJ_ACTUATOR === 'number'
          ? mujoco.mjtObj.mjOBJ_ACTUATOR : mujoco.mjtObj.mjOBJ_ACTUATOR.value;
        actuator = mujoco.mj_name2id(model, kind, prop.actuator);
      }
      this.rotors.push({ mesh, spin: prop.spin, actuator });
    }

    // ---- wheels, each on its own hinge -------------------------------------
    for (const wheel of layout.wheels) {
      const geometry = geometries[wheel.mesh];
      const id = geomId(wheel.geom);
      if (!geometry || id < 0) continue;
      const mesh = new THREE.Mesh(geometry, wheelMaterial);
      mesh.matrixAutoUpdate = false;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      view.scene.add(mesh);
      this.parts.push({ mesh, ref: this._reference(id) });
    }

    // ---- retire the primitives these replace -------------------------------
    const drop = [layout.bodyGeom, ...layout.wheels.map((w) => w.geom)];
    for (const name of drop) {
      const entry = view.geomMeshes.find((m) => m.mesh.name === name);
      if (entry) { entry.mesh.visible = false; this.hidden.push(entry.mesh); }
    }
    for (const name of layout.hideSites || []) {
      const entry = view.siteMeshes.find((m) => m.mesh.name === name);
      if (entry) { entry.mesh.visible = false; this.hidden.push(entry.mesh); }
    }

    this._m = new THREE.Matrix4();
    this._local = new THREE.Matrix4();
  }

  /**
   * How to get a body's pose back from one of its geoms: the geom's fixed
   * offset and orientation inside the body, ready to be divided out.
   */
  _reference(geomIndex) {
    const q = quatAt(this.model.geom_quat, geomIndex);
    const p = vec3At(this.model.geom_pos, geomIndex);
    return { index: geomIndex, invQuat: q.clone().invert(), localPos: p };
  }

  /** Place a mesh on the body frame of the geom it references. */
  _place(target, ref, data) {
    const i = ref.index;
    const m = data.geom_xmat;
    const p = data.geom_xpos;
    // geom_xmat = R_body * R_local, so R_body = geom_xmat * R_local^-1.
    this._m.set(
      m[i * 9 + 0], m[i * 9 + 1], m[i * 9 + 2], 0,
      m[i * 9 + 3], m[i * 9 + 4], m[i * 9 + 5], 0,
      m[i * 9 + 6], m[i * 9 + 7], m[i * 9 + 8], 0,
      0, 0, 0, 1,
    );
    this._m.multiply(this._local.makeRotationFromQuaternion(ref.invQuat));
    // geom_xpos = body_pos + R_body * local_pos.
    const offset = ref.localPos.clone().applyMatrix4(this._m);
    this._m.setPosition(
      p[i * 3 + 0] - offset.x,
      p[i * 3 + 1] - offset.y,
      p[i * 3 + 2] - offset.z,
    );
    target.matrix.copy(this._m);
    target.matrixWorldNeedsUpdate = true;
  }

  /**
   * @param {object} data MjData for this step
   * @param {number} dt   seconds of wall-clock since the last frame, for the
   *                      rotor spin (cosmetic, so wall-clock is what suits it)
   */
  sync(data, dt) {
    this._place(this.bodyGroup, this.bodyRef, data);
    for (const { mesh, ref } of this.parts) this._place(mesh, ref, data);

    const ctrl = data.ctrl;
    for (const rotor of this.rotors) {
      const thrust = ctrl && rotor.actuator >= 0 ? ctrl[rotor.actuator] : 0;
      const rev = Math.min(SPIN_IDLE + SPIN_PER_NEWTON * Math.max(thrust, 0), SPIN_MAX);
      rotor.mesh.rotation.z += rotor.spin * rev * 2 * Math.PI * dt;
    }
  }

  dispose() {
    for (const mesh of this.hidden) mesh.visible = true;
    this.bodyGroup.removeFromParent();
    for (const { mesh } of this.parts) mesh.removeFromParent();
    for (const material of this.materials) material.dispose();
  }
}
