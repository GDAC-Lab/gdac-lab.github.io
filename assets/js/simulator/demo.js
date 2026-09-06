/**
 * Browser demo of the lab's wheeled-UAV simulator.
 *
 * The physics is the real thing: MuJoCo compiled to WebAssembly (the official
 * @mujoco/mujoco bindings), loading the same MJCF the desktop simulator
 * generates, stepped at the same 1 ms timestep. The controller in
 * controller.js is a line-by-line port of the simulator's geometric hover
 * controller. Nothing here is a recording — move the target and the vehicle
 * has to work out what to do.
 *
 * The target can be set four ways, all feeding one setTarget():
 *   - drag the green reference sphere in the 3D view
 *   - drag on the side-view pad inset in the corner of the 3D view
 *   - arrow keys while the pad has focus
 *   - the scenario presets
 *
 * Everything is served from this site; no third-party requests.
 */

import { computeHoverControl, WALL_DEMO_CONFIG } from './controller.js';

// The engine glue and three.js are imported only after the visitor presses
// "Load and run" (see arm()), so opening the page costs nothing extra.
const ENGINE_URL = new URL('../../vendor/mujoco/mujoco.js', import.meta.url).href;
const VIEW_URL = new URL('./scene.js', import.meta.url).href;
const DRONE_MESH_URL = new URL('./drone-mesh.js', import.meta.url).href;

/** Embind enums arrive as objects; the C functions want the plain int. */
const enumValue = (entry) => (typeof entry === 'number' ? entry : entry.value);

const CONTROL_DECIMATION = 5;   // 1 kHz physics -> 200 Hz control, as in the simulator
const MAX_CATCHUP_SECONDS = 0.1; // never try to make up more than this in one frame

/**
 * Scene geometry, for describing the target in useful terms.
 * The wall's near face is at x = 1.95 m. The wheels have radius 0.15 m, so the
 * body cannot get past x = 1.80 m: a target beyond that is unreachable, and the
 * leftover command becomes the force pressing the wheels into the wall. That is
 * the whole trick behind the wall demo — no dedicated pressing controller.
 */
const BODY_X_AT_CONTACT = 1.80;

/** Where the target may be placed. Inside the wall is allowed on purpose. */
const TARGET_LIMITS = { x: [0.80, 2.15], z: [0.35, 1.75] };
const KEY_STEP = 0.02;
const KEY_STEP_FAST = 0.10;

/** World extent the side-view pad shows; must match the SVG in the include. */
const PAD = { x0: 0.60, x1: 2.25, z0: 0.00, z1: 1.90 };

const SCENARIOS = {
  'wall-climb': { x: 1.93, z: 1.60 },
  'wall-hold': { x: 1.93, z: 0.62 },
  hover: { x: 1.00, z: 1.20 },
};

const clamp = (v, [lo, hi]) => Math.min(Math.max(v, lo), hi);

class SimulatorDemo {
  constructor(root) {
    this.root = root;
    this.canvas = root.querySelector('[data-sim-canvas]');
    this.statusEl = root.querySelector('[data-sim-status]');
    this.readout = {
      time: root.querySelector('[data-sim-time]'),
      height: root.querySelector('[data-sim-height]'),
      contact: root.querySelector('[data-sim-contact]'),
      rate: root.querySelector('[data-sim-rate]'),
    };
    this.playButton = root.querySelector('[data-sim-play]');
    this.resetButton = root.querySelector('[data-sim-reset]');
    this.speedSelect = root.querySelector('[data-sim-speed]');
    this.scenarioButtons = [...root.querySelectorAll('[data-sim-scenario]')];
    this.pad = root.querySelector('[data-sim-pad]');
    this.padTargetDot = root.querySelector('[data-sim-pad-target]');
    this.padDroneDot = root.querySelector('[data-sim-pad-drone]');
    this.targetXOut = root.querySelector('[data-sim-target-x-out]');
    this.targetZOut = root.querySelector('[data-sim-target-z-out]');
    this.insetHeight = root.querySelector('[data-sim-inset-height]');
    this.gate = root.querySelector('[data-sim-gate]');
    this.loadButton = root.querySelector('[data-sim-load]');
    this.meteredNote = root.querySelector('[data-sim-metered]');

    this.strings = JSON.parse(root.dataset.simStrings || '{}');
    this.modelUrl = root.dataset.simModel;
    this.meshUrl = root.dataset.simMesh || '';
    this.droneMesh = null;
    this.targetPos = { x: 1.93, z: 1.30 };
    this.running = false;
    this.lastFrameMs = 0;
    this.stepCounter = 0;
    this.stepsThisSecond = 0;
    this.rateWindowStart = 0;
    this.dragging3d = false;
    this.hovering3d = false;
  }

  say(key, fallback) {
    return this.strings[key] || fallback;
  }

  setStatus(text, kind) {
    if (!this.statusEl) return;
    this.statusEl.textContent = text;
    this.statusEl.dataset.kind = kind || 'info';
    this.statusEl.hidden = !text;
  }

  /**
   * Show the gate and wait for the visitor's go-ahead. The engine is a large
   * download, so nothing is fetched until they choose to. If the connection
   * looks metered, say so on the card.
   */
  arm() {
    const conn = navigator.connection;
    const metered = !!(conn && (conn.saveData || /(^|-)(2g|3g)$/.test(conn.effectiveType || '')));
    if (metered && this.meteredNote) {
      this.meteredNote.textContent = this.say('meteredNote', 'This looks like a metered connection.');
      this.meteredNote.hidden = false;
    }
    this.root.dataset.simState = 'idle';
    if (this.loadButton) {
      this.loadButton.addEventListener('click', () => {
        this.loadButton.disabled = true;
        this.load().catch((error) => this.fail(error));
      }, { once: true });
    }
  }

  fail(error) {
    console.error('[simulator]', error);
    if (this.gate) this.gate.hidden = true;
    this.setStatus(
      `${this.say('failed', 'The demo could not start in this browser.')} (${error.message})`,
      'error',
    );
    this.root.dataset.simState = 'error';
  }

  async load() {
    this.root.dataset.simState = 'loading';
    if (this.gate) this.gate.hidden = true;
    this.setStatus(this.say('loading', 'Loading the physics engine…'), 'loading');
    const [{ default: loadMujoco }, { MujocoView }, xml] = await Promise.all([
      import(ENGINE_URL),
      import(VIEW_URL),
      fetch(this.modelUrl).then((r) => {
        if (!r.ok) throw new Error(`model ${r.status}`);
        return r.text();
      }),
    ]);
    const mujoco = await loadMujoco();
    this.mujoco = mujoco;
    this.model = mujoco.MjModel.from_xml_string(xml);
    this.data = new mujoco.MjData(this.model);
    mujoco.mj_forward(this.model, this.data);

    this.sensors = this._sensorAddresses();
    this.wallGeomId = mujoco.mj_name2id(this.model, enumValue(mujoco.mjtObj.mjOBJ_GEOM), 'wall_geom');
    this.timestep = this.model.opt.timestep;

    // The green sphere is a mocap body: the simulator slides it along the
    // commanded path. Here the visitor sets the command, so it marks that.
    const markerBody = mujoco.mj_name2id(this.model, enumValue(mujoco.mjtObj.mjOBJ_BODY), 'overlay_reference_marker_0');
    this.markerMocapId = markerBody >= 0 ? this.model.body_mocapid[markerBody] : -1;

    this.view = new MujocoView(this.canvas, this.model, mujoco);
    this.view.setBackground(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
    this.view.resize();
    await this._loadDroneMesh();
    this.setTarget(this.targetPos.x, this.targetPos.z);
    mujoco.mj_forward(this.model, this.data);
    this._syncView(0);
    this.view.render();

    this._wireControls();
    this.setStatus(this.say('ready', 'Ready.'), 'ready');
    this.root.dataset.simState = 'ready';
    this.start();
  }

  /**
   * Swap MuJoCo's collision primitives for the lab's CAD, if the bundle is
   * there. Optional by design: the demo is about the controller, so a failure
   * here leaves the boxes and cylinders in place and says nothing.
   */
  async _loadDroneMesh() {
    if (!this.meshUrl) return;
    try {
      const { loadDroneMesh, DroneMesh } = await import(DRONE_MESH_URL);
      const bundle = await loadDroneMesh(this.meshUrl);
      this.droneMesh = new DroneMesh(this.view, bundle, this.model, this.mujoco);
    } catch (error) {
      this.droneMesh = null;
      if (window.console) console.info('simulator: drawing the primitives —', error.message);
    }
  }

  /** One place that advances every drawn thing by dt seconds of wall clock. */
  _syncView(dt) {
    this.view.sync(this.data);
    if (this.droneMesh) this.droneMesh.sync(this.data, dt);
  }

  _sensorAddresses() {
    const { mujoco, model } = this;
    const address = (name) => {
      const id = mujoco.mj_name2id(model, enumValue(mujoco.mjtObj.mjOBJ_SENSOR), name);
      if (id < 0) throw new Error(`sensor "${name}" is missing from the model`);
      return model.sensor_adr[id];
    };
    return {
      position: address('drone_position'),
      velocity: address('drone_linear_velocity'),
      angularVelocity: address('drone_angular_velocity'),
      xAxis: address('drone_x_axis'),
      yAxis: address('drone_y_axis'),
      zAxis: address('drone_z_axis'),
    };
  }

  /** Assemble exactly the state the simulator publishes over UDP. */
  readState() {
    const s = this.data.sensordata;
    const a = this.sensors;
    const v3 = (adr) => [s[adr], s[adr + 1], s[adr + 2]];
    const x = v3(a.xAxis);
    const y = v3(a.yAxis);
    const z = v3(a.zAxis);
    // Columns are the body axes in world coordinates; stored row-major.
    const R = [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]];
    const omegaWorld = v3(a.angularVelocity);
    // The controller wants body-frame rates: omega_body = R^T omega_world.
    const angularVelocityBody = [
      R[0] * omegaWorld[0] + R[3] * omegaWorld[1] + R[6] * omegaWorld[2],
      R[1] * omegaWorld[0] + R[4] * omegaWorld[1] + R[7] * omegaWorld[2],
      R[2] * omegaWorld[0] + R[5] * omegaWorld[1] + R[8] * omegaWorld[2],
    ];
    return {
      position: v3(a.position),
      velocity: v3(a.velocity),
      angularVelocityBody,
      rotationMatrix: R,
    };
  }

  /* ---------------------------------------------------------------- target */

  target() {
    return [this.targetPos.x, 0, this.targetPos.z];
  }

  /**
   * The one place the target changes. Clamps, moves the marker, and refreshes
   * every readout of it. While paused it also redraws, so dragging the marker
   * still shows the marker moving.
   */
  setTarget(x, z) {
    this.targetPos = { x: clamp(x, TARGET_LIMITS.x), z: clamp(z, TARGET_LIMITS.z) };
    this._placeMarker(this.target());
    this._syncTargetLabels();
    this._syncPadTarget();
    if (this.view && !this.running) {
      this.mujoco.mj_forward(this.model, this.data);
      this._syncView(0);
      this.view.render();
    }
  }

  nudgeTarget(dx, dz) {
    this.setTarget(this.targetPos.x + dx, this.targetPos.z + dz);
  }

  /** Park the reference marker on the commanded target. */
  _placeMarker(target) {
    if (this.markerMocapId < 0) return;
    const base = this.markerMocapId * 3;
    const mocap = this.data.mocap_pos;
    mocap[base] = target[0];
    mocap[base + 1] = target[1];
    mocap[base + 2] = target[2];
  }

  _syncTargetLabels() {
    const { x, z } = this.targetPos;
    if (this.targetXOut) {
      const press = x - BODY_X_AT_CONTACT;
      this.targetXOut.textContent = press > 0.005
        ? `${x.toFixed(2)} m (+${press.toFixed(2)})`
        : `${x.toFixed(2)} m`;
      this.targetXOut.dataset.pressing = press > 0.005 ? 'true' : 'false';
    }
    if (this.targetZOut) this.targetZOut.textContent = `${z.toFixed(2)} m`;
  }

  /* ------------------------------------------------------------------- pad */

  /** World (x, z) -> pad SVG coordinates. The SVG viewBox is in centimetres. */
  static _worldToPad(x, z) {
    return { sx: (x - PAD.x0) * 100, sy: (PAD.z1 - z) * 100 };
  }

  _padToWorld(clientX, clientY) {
    const r = this.pad.getBoundingClientRect();
    const fx = (clientX - r.left) / r.width;
    const fy = (clientY - r.top) / r.height;
    return { x: PAD.x0 + fx * (PAD.x1 - PAD.x0), z: PAD.z1 - fy * (PAD.z1 - PAD.z0) };
  }

  _syncPadTarget() {
    if (!this.padTargetDot) return;
    const { sx, sy } = SimulatorDemo._worldToPad(this.targetPos.x, this.targetPos.z);
    this.padTargetDot.setAttribute('cx', sx.toFixed(1));
    this.padTargetDot.setAttribute('cy', sy.toFixed(1));
  }

  _syncPadDrone(position) {
    if (!this.padDroneDot) return;
    const { sx, sy } = SimulatorDemo._worldToPad(position[0], position[2]);
    this.padDroneDot.setAttribute('cx', sx.toFixed(1));
    this.padDroneDot.setAttribute('cy', sy.toFixed(1));
    if (this.insetHeight) {
      const text = `${position[2].toFixed(2)} m`;
      if (this.insetHeight.textContent !== text) this.insetHeight.textContent = text;
    }
  }

  _wirePad() {
    const pad = this.pad;
    if (!pad) return;
    let activePointer = null;
    const place = (event) => {
      const { x, z } = this._padToWorld(event.clientX, event.clientY);
      this.setTarget(x, z);
    };
    pad.addEventListener('pointerdown', (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      activePointer = event.pointerId;
      pad.setPointerCapture(event.pointerId);
      pad.classList.add('is-dragging');
      pad.focus({ preventScroll: true });
      place(event);
      event.preventDefault();
    });
    pad.addEventListener('pointermove', (event) => {
      if (event.pointerId !== activePointer) return;
      place(event);
    });
    const release = (event) => {
      if (event.pointerId !== activePointer) return;
      activePointer = null;
      pad.classList.remove('is-dragging');
    };
    pad.addEventListener('pointerup', release);
    pad.addEventListener('pointercancel', release);

    pad.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? KEY_STEP_FAST : KEY_STEP;
      const moves = {
        ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step],
      };
      const move = moves[event.key];
      if (!move) return;
      event.preventDefault();
      this.nudgeTarget(move[0], move[1]);
    });
  }

  /* ------------------------------------------------------------- 3D drag */

  _wire3dDrag() {
    const canvas = this.canvas;
    let activePointer = null;

    const setHover = (on) => {
      if (on === this.hovering3d) return;
      this.hovering3d = on;
      this.view.setMarkerHighlight(on);
      canvas.style.cursor = on ? 'grab' : '';
      if (!this.running) this.view.render();
    };

    // Registered in the capture phase so it runs before OrbitControls' own
    // pointerdown on the same element; the marker grab must win over orbit.
    canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      if (!this.view.pickMarker(event.clientX, event.clientY)) return;
      event.stopImmediatePropagation();
      event.preventDefault();
      activePointer = event.pointerId;
      this.dragging3d = true;
      this.view.setOrbitEnabled(false);
      canvas.setPointerCapture(event.pointerId);
      canvas.style.cursor = 'grabbing';
    }, { capture: true });

    canvas.addEventListener('pointermove', (event) => {
      if (this.dragging3d) {
        if (event.pointerId !== activePointer) return;
        const hit = this.view.projectToTargetPlane(event.clientX, event.clientY);
        if (hit) this.setTarget(hit.x, hit.z);
        return;
      }
      // Hover feedback only for a mouse: touch has no hover, and a raycast per
      // touchmove would fight the orbit gesture for no benefit.
      if (event.pointerType === 'mouse') setHover(this.view.pickMarker(event.clientX, event.clientY));
    });

    const release = (event) => {
      if (!this.dragging3d || event.pointerId !== activePointer) return;
      activePointer = null;
      this.dragging3d = false;
      this.view.setOrbitEnabled(true);
      canvas.style.cursor = this.hovering3d ? 'grab' : '';
    };
    canvas.addEventListener('pointerup', release);
    canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('pointerleave', () => { if (!this.dragging3d) setHover(false); });
  }

  /* --------------------------------------------------------------- physics */

  /** How many contacts involve the wall right now. */
  wallContacts() {
    const { data } = this;
    if (this.wallGeomId < 0) return 0;
    let count = 0;
    for (let i = 0; i < data.ncon; i += 1) {
      const c = data.contact.get(i);
      if (c.geom1 === this.wallGeomId || c.geom2 === this.wallGeomId) count += 1;
    }
    return count;
  }

  step(seconds) {
    const { mujoco, model, data } = this;
    const steps = Math.min(Math.round(seconds / this.timestep), Math.round(MAX_CATCHUP_SECONDS / this.timestep));
    const target = this.target();
    for (let i = 0; i < steps; i += 1) {
      if (this.stepCounter % CONTROL_DECIMATION === 0) {
        const thrusts = computeHoverControl(this.readState(), target, WALL_DEMO_CONFIG);
        const ctrl = data.ctrl;
        for (let j = 0; j < thrusts.length; j += 1) ctrl[j] = thrusts[j];
      }
      mujoco.mj_step(model, data);
      this.stepCounter += 1;
    }
    this.stepsThisSecond += steps;
    return steps;
  }

  frame(nowMs) {
    if (!this.running) return;
    this.rafHandle = requestAnimationFrame((t) => this.frame(t));
    const elapsed = this.lastFrameMs ? (nowMs - this.lastFrameMs) / 1000 : 0;
    this.lastFrameMs = nowMs;
    const speed = Number(this.speedSelect ? this.speedSelect.value : 1) || 1;
    if (elapsed > 0) this.step(elapsed * speed);
    this._syncView(Math.min(elapsed, 0.1) * speed);
    this.view.render();
    this._syncPadDrone(this.readState().position);
    this._updateReadout(nowMs);
  }

  _updateReadout(nowMs) {
    if (!this.rateWindowStart) this.rateWindowStart = nowMs;
    if (nowMs - this.rateWindowStart < 400) return;
    const wallSeconds = (nowMs - this.rateWindowStart) / 1000;
    const simSeconds = this.stepsThisSecond * this.timestep;
    this.stepsThisSecond = 0;
    this.rateWindowStart = nowMs;

    const position = this.readState().position;
    const contacts = this.wallContacts();
    if (this.readout.time) this.readout.time.textContent = `${this.data.time.toFixed(1)} s`;
    if (this.readout.height) this.readout.height.textContent = `${position[2].toFixed(2)} m`;
    if (this.readout.contact) {
      this.readout.contact.textContent = contacts > 0
        ? this.say('contactYes', 'in contact')
        : this.say('contactNo', 'not in contact');
    }
    if (this.readout.rate) this.readout.rate.textContent = `${(simSeconds / wallSeconds).toFixed(2)}×`;
  }

  /* -------------------------------------------------------------- lifecycle */

  start() {
    if (this.running) return;
    this.running = true;
    this.lastFrameMs = 0;
    this.rateWindowStart = 0;
    this.root.dataset.simState = 'running';
    if (this.playButton) this.playButton.textContent = this.say('pause', 'Pause');
    this.rafHandle = requestAnimationFrame((t) => this.frame(t));
  }

  stop() {
    this.running = false;
    if (this.rafHandle) cancelAnimationFrame(this.rafHandle);
    this.root.dataset.simState = 'paused';
    if (this.playButton) this.playButton.textContent = this.say('play', 'Play');
  }

  reset() {
    this.mujoco.mj_resetData(this.model, this.data);
    this._placeMarker(this.target());
    this.mujoco.mj_forward(this.model, this.data);
    this.stepCounter = 0;
    this._syncView(0);
    this.view.render();
    this._syncPadDrone(this.readState().position);
  }

  _wireControls() {
    if (this.playButton) {
      this.playButton.addEventListener('click', () => (this.running ? this.stop() : this.start()));
    }
    if (this.resetButton) this.resetButton.addEventListener('click', () => this.reset());
    for (const button of this.scenarioButtons) {
      button.addEventListener('click', () => {
        const preset = SCENARIOS[button.dataset.simScenario];
        if (!preset) return;
        this.setTarget(preset.x, preset.z);
        this.reset();
        this.start();
      });
    }
    this._wirePad();
    this._wire3dDrag();
    this._syncPadDrone(this.readState().position);

    const resize = () => {
      this.view.resize();
      this.view.render();
    };
    if (window.ResizeObserver) {
      this.resizeObserver = new ResizeObserver(resize);
      this.resizeObserver.observe(this.canvas);
    } else {
      window.addEventListener('resize', resize);
    }

    // Follow the site's light/dark toggle.
    this.themeObserver = new MutationObserver(() => {
      this.view.setBackground(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
      this.view.render();
    });
    this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // Stop burning CPU (and battery) while the page is not on screen.
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && this.running) {
        this.wasRunning = true;
        this.stop();
      } else if (!document.hidden && this.wasRunning) {
        this.wasRunning = false;
        this.start();
      }
    });
  }
}

const root = document.querySelector('[data-sim-root]');
if (root) {
  const demo = new SimulatorDemo(root);
  // Exposed on the element for tooling and tests; not part of any page API.
  root.simdemo = demo;
  demo.arm();
}
