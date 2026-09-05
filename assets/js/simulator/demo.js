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
 * Everything is served from this site; no third-party requests.
 */

import loadMujoco from '../../vendor/mujoco/mujoco.js';
import { MujocoView, enumValue } from './scene.js';
import { computeHoverControl, WALL_DEMO_CONFIG } from './controller.js';

const CONTROL_DECIMATION = 5;   // 1 kHz physics -> 200 Hz control, as in the simulator
const MAX_CATCHUP_SECONDS = 0.1; // never try to make up more than this in one frame

/**
 * Scene geometry, for describing the target slider in useful terms.
 * The wall's near face is at x = 1.95 m. The wheels have radius 0.15 m, so the
 * body cannot get past x = 1.80 m: a target beyond that is unreachable, and the
 * leftover command becomes the force pressing the wheels into the wall. That is
 * the whole trick behind the wall demo — no dedicated pressing controller.
 */
const WALL_FACE_X = 1.95;
const BODY_X_AT_CONTACT = 1.80;

const SCENARIOS = {
  'wall-climb': { x: 1.93, z: 1.60 },
  'wall-hold': { x: 1.93, z: 0.62 },
  hover: { x: 1.00, z: 1.20 },
};

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
    this.targetX = root.querySelector('[data-sim-target-x]');
    this.targetZ = root.querySelector('[data-sim-target-z]');
    this.targetXOut = root.querySelector('[data-sim-target-x-out]');
    this.targetZOut = root.querySelector('[data-sim-target-z-out]');
    this.speedSelect = root.querySelector('[data-sim-speed]');
    this.scenarioButtons = [...root.querySelectorAll('[data-sim-scenario]')];

    this.strings = JSON.parse(root.dataset.simStrings || '{}');
    this.modelUrl = root.dataset.simModel;
    this.running = false;
    this.lastFrameMs = 0;
    this.stepCounter = 0;
    this.stepsThisSecond = 0;
    this.rateWindowStart = 0;
  }

  say(key, fallback) {
    return this.strings[key] || fallback;
  }

  setStatus(text, kind) {
    if (!this.statusEl) return;
    this.statusEl.textContent = text;
    this.statusEl.dataset.kind = kind || 'info';
  }

  async load() {
    this.setStatus(this.say('loading', 'Loading the physics engine…'), 'loading');
    const [mujoco, xml] = await Promise.all([
      loadMujoco(),
      fetch(this.modelUrl).then((r) => {
        if (!r.ok) throw new Error(`model ${r.status}`);
        return r.text();
      }),
    ]);
    this.mujoco = mujoco;
    this.model = mujoco.MjModel.from_xml_string(xml);
    this.data = new mujoco.MjData(this.model);
    mujoco.mj_forward(this.model, this.data);

    this.sensors = this._sensorAddresses();
    this.wallGeomId = mujoco.mj_name2id(this.model, enumValue(mujoco.mjtObj.mjOBJ_GEOM), 'wall_geom');
    this.timestep = this.model.opt.timestep;

    // The green sphere is a mocap body: the simulator slides it along the
    // commanded path. Here the sliders set the command, so point it at them.
    const markerBody = mujoco.mj_name2id(this.model, enumValue(mujoco.mjtObj.mjOBJ_BODY), 'overlay_reference_marker_0');
    this.markerMocapId = markerBody >= 0 ? this.model.body_mocapid[markerBody] : -1;

    this.view = new MujocoView(this.canvas, this.model, mujoco);
    this.view.setBackground(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
    this.view.resize();
    this.view.sync(this.data);
    this.view.render();

    this._wireControls();
    this.setStatus(this.say('ready', 'Ready.'), 'ready');
    this.root.dataset.simState = 'ready';
    this.start();
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

  target() {
    return [Number(this.targetX.value), 0, Number(this.targetZ.value)];
  }

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

  /** Park the reference marker on the commanded target. */
  _placeMarker(target) {
    if (this.markerMocapId < 0) return;
    const base = this.markerMocapId * 3;
    const mocap = this.data.mocap_pos;
    mocap[base] = target[0];
    mocap[base + 1] = target[1];
    mocap[base + 2] = target[2];
  }

  step(seconds) {
    const { mujoco, model, data } = this;
    const steps = Math.min(Math.round(seconds / this.timestep), Math.round(MAX_CATCHUP_SECONDS / this.timestep));
    const target = this.target();
    this._placeMarker(target);
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
    this.view.sync(this.data);
    this.view.render();
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
    this.view.sync(this.data);
    this.view.render();
  }

  _syncTargetLabels() {
    const x = Number(this.targetX.value);
    const z = Number(this.targetZ.value);
    if (this.targetXOut) {
      const press = x - BODY_X_AT_CONTACT;
      this.targetXOut.textContent = press > 0.005
        ? `${x.toFixed(2)} m (+${press.toFixed(2)})`
        : `${x.toFixed(2)} m`;
      this.targetXOut.dataset.pressing = press > 0.005 ? 'true' : 'false';
    }
    if (this.targetZOut) this.targetZOut.textContent = `${z.toFixed(2)} m`;
  }

  _wireControls() {
    if (this.playButton) {
      this.playButton.addEventListener('click', () => (this.running ? this.stop() : this.start()));
    }
    if (this.resetButton) this.resetButton.addEventListener('click', () => this.reset());
    for (const input of [this.targetX, this.targetZ]) {
      if (input) input.addEventListener('input', () => this._syncTargetLabels());
    }
    for (const button of this.scenarioButtons) {
      button.addEventListener('click', () => {
        const preset = SCENARIOS[button.dataset.simScenario];
        if (!preset) return;
        this.targetX.value = preset.x;
        this.targetZ.value = preset.z;
        this._syncTargetLabels();
        this.reset();
        this.start();
      });
    }
    this._syncTargetLabels();

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
  demo.load().catch((error) => {
    console.error('[simulator]', error);
    demo.setStatus(
      `${demo.say('failed', 'The demo could not start in this browser.')} (${error.message})`,
      'error',
    );
    root.dataset.simState = 'error';
  });
}
