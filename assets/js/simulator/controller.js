/**
 * Geometric hover controller, ported from the lab's simulator.
 *
 * Source: wheeled_uav/controllers/hover.py — compute_hover_control() in
 * https://github.com/GDAC-Lab/mujoco-wheeled-uav-simulator (v1.1.0).
 *
 * In the simulator this runs in MATLAB or Python and talks to the physics over
 * UDP. In the browser there is no network hop: the same law runs in this file,
 * on the state read straight out of MuJoCo's sensors.
 *
 * The law is the SE(3) geometric controller the lab's rotational-control work is
 * built on: the attitude error is taken on the rotation matrix itself rather
 * than on three angles, so it has no singularity at any attitude.
 *
 * Gains and limits are the wall_demo preset's, and the mixer is
 * pinv(allocation_matrix) for this rotor geometry — both taken from the
 * simulator so the browser reproduces its behaviour rather than approximating
 * it. Regenerate them with scripts/dump_simulator_constants.py.
 */

/** wall_demo preset (configs/vehicle_params.wall_demo.json). */
export const WALL_DEMO_CONFIG = Object.freeze({
  mass: 1.0,                       // drone body + both wheels
  gravity: 9.81,
  maxRotorThrust: 20.0,
  desiredHeading: [1.0, 0.0, 0.0],
  positionGain: [3.0, 3.0, 6.0],
  velocityGain: [2.2, 2.2, 4.0],
  attitudeGain: [0.8, 0.8, 0.25],
  angularVelocityGain: [0.12, 0.12, 0.08],
  positionErrorLimitM: 1.5,
  maxTiltDeg: 35.0,
  minVerticalForceFactor: 0.25,
  // Wrench [collective, Mx, My, Mz] -> the four rotor thrusts, in the actuator
  // order of the generated model (fr, fl, br, bl).
  mixer: [
    [0.25, -2.5, -3.125, -16.666666666666668],
    [0.25, 2.5, -3.125, 16.666666666666668],
    [0.25, -2.5, 3.125, 16.666666666666668],
    [0.25, 2.5, 3.125, -16.666666666666668],
  ],
});

/* ------------------------------------------------------------------ vectors */

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => Math.hypot(a[0], a[1], a[2]);
const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

function normalize(v, fallback) {
  const n = norm(v);
  if (n < 1e-12) return fallback.slice();
  return [v[0] / n, v[1] / n, v[2] / n];
}

/** Saturate the position-error norm so a far-away target commands a bounded pull. */
function clampPositionError(error, limit) {
  if (limit <= 0) return error;
  const n = norm(error);
  if (n <= limit) return error;
  const s = limit / n;
  return [error[0] * s, error[1] * s, error[2] * s];
}

/**
 * Floor the vertical force and cap the tilt of the desired thrust.
 *
 * Without this the raw PD can produce a near-horizontal or downward force when
 * the vehicle is far from its target: the collective collapses and the vehicle
 * flips instead of recovering.
 */
function applyForceSafetyClamps(force, minVerticalForce, maxTiltDeg) {
  if (maxTiltDeg <= 0) return force;
  const out = [force[0], force[1], Math.max(force[2], minVerticalForce)];
  if (maxTiltDeg >= 90) return out;
  const maxHorizontal = out[2] * Math.tan((maxTiltDeg * Math.PI) / 180);
  const horizontal = Math.hypot(out[0], out[1]);
  if (horizontal > maxHorizontal) {
    const s = maxHorizontal / horizontal;
    out[0] *= s;
    out[1] *= s;
  }
  return out;
}

/* --------------------------------------------------------------- the law */

/**
 * One control evaluation.
 *
 * @param {{position:number[], velocity:number[], angularVelocityBody:number[],
 *          rotationMatrix:number[]}} state
 *        rotationMatrix is row-major; its columns are the body axes in world.
 * @param {number[]} target  desired position, world frame
 * @param {object} config    see WALL_DEMO_CONFIG
 * @returns {number[]} the four rotor thrusts, in actuator order
 */
export function computeHoverControl(state, target, config) {
  const { position: p, velocity: v, angularVelocityBody: omega } = state;
  const R = state.rotationMatrix; // [r00 r01 r02 r10 r11 r12 r20 r21 r22]
  const heading = normalize(config.desiredHeading, [1, 0, 0]);

  const positionError = clampPositionError(
    [target[0] - p[0], target[1] - p[1], target[2] - p[2]],
    config.positionErrorLimitM,
  );

  const hoverForce = config.mass * config.gravity;
  let desiredForce = [
    config.positionGain[0] * positionError[0] - config.velocityGain[0] * v[0],
    config.positionGain[1] * positionError[1] - config.velocityGain[1] * v[1],
    config.positionGain[2] * positionError[2] - config.velocityGain[2] * v[2] + hoverForce,
  ];
  desiredForce = applyForceSafetyClamps(
    desiredForce,
    config.minVerticalForceFactor * hoverForce,
    config.maxTiltDeg,
  );

  // Collective is the desired force projected on the current body z-axis
  // (column 2 of R), never negative: rotors cannot pull.
  const bodyZ = [R[2], R[5], R[8]];
  const collective = Math.max(0, dot(desiredForce, bodyZ));

  // Desired attitude: body z along the desired force, body x as close to the
  // desired heading as that allows.
  const zDes = normalize(desiredForce, [0, 0, 1]);
  let yDes = cross(zDes, heading);
  if (norm(yDes) < 1e-6) yDes = cross(zDes, [0, 1, 0]);
  yDes = normalize(yDes, [0, 1, 0]);
  const xDes = normalize(cross(yDes, zDes), [1, 0, 0]);
  // Rd = [xDes yDes zDes] as columns, row-major.
  const Rd = [
    xDes[0], yDes[0], zDes[0],
    xDes[1], yDes[1], zDes[1],
    xDes[2], yDes[2], zDes[2],
  ];

  // Attitude error on SO(3): vee( (Rd^T R - R^T Rd) / 2 ).
  const m = (A, B, i, j) =>
    A[0 * 3 + i] * B[0 * 3 + j] + A[1 * 3 + i] * B[1 * 3 + j] + A[2 * 3 + i] * B[2 * 3 + j];
  const e = (i, j) => 0.5 * (m(Rd, R, i, j) - m(R, Rd, i, j));
  const attitudeError = [e(2, 1), e(0, 2), e(1, 0)];

  const moment = [
    -config.attitudeGain[0] * attitudeError[0] - config.angularVelocityGain[0] * omega[0],
    -config.attitudeGain[1] * attitudeError[1] - config.angularVelocityGain[1] * omega[1],
    -config.attitudeGain[2] * attitudeError[2] - config.angularVelocityGain[2] * omega[2],
  ];

  const wrench = [collective, moment[0], moment[1], moment[2]];
  return config.mixer.map((row) => {
    const t = row[0] * wrench[0] + row[1] * wrench[1] + row[2] * wrench[2] + row[3] * wrench[3];
    return Math.min(Math.max(t, 0), config.maxRotorThrust);
  });
}
