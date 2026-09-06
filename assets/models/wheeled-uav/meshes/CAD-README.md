# QAV250 drone STL model

Multi-part STL model of the two-wheeled QAV250 drone, used to render the
coverage animations with a realistic body instead of the body-frame triad.
Imported from the user-provided `QAV250model` bundle (2026-07-13).

## Parts (body frame, millimeters)

All parts are expressed in the vehicle body frame — **x** forward, **y** left
(the wheel axle), **z** up along the thrust axis — and are in **millimeters**
(load with `stl_scale = 1e-3`).

| file | role | notes |
|------|------|-------|
| `frame.stl` | body / chassis | static in the body frame |
| `wheel_l.stl`, `wheel_r.stl` | wheels | radius 0.142 m; share the body-y axle through the origin, spun about y |
| `propeller_cw.stl`, `propeller_ccw.stl` | rotor blades | hub at the mesh origin; placed at the arm tips and spun about z |
| `QAV250.stl` | fully assembled body | single mesh; usable via the `stl_path` option for a static body |

Rotor arm tips (body frame, meters), CW/CCW placement matching the vendor
usage example: front-left `[+0.075, +0.100, 0.009]` CW, back-left
`[-0.075, +0.100, 0.009]` CCW, back-right `[-0.075, -0.100, 0.009]` CW,
front-right `[+0.075, -0.100, 0.009]` CCW.

## Usage

```matlab
% Load & cache the model (decimated to 30% of faces for animation speed):
model = coverage_drone_model('reduce', 0.3);

% Draw one drone at pose (xi, R) — used by the animation and can be used in
% snapshots too:
coverage_draw_drone(xi, R, 'model', model, 'wheel_angle', 0.6, 'prop_phase', 1.2);

% Render an animation with the STL body (instead of the triad):
coverage_animate_run(out, cov, surf_fns, 'output', 'anim.mp4', 'drone_model', 'qav250');

% Or end-to-end through the runners:
coverage_mujoco_paper_run(..., 'drone_model', 'qav250');
coverage_run_reference_scenario('scenario', 'steep', 'drone_model', 'qav250');
```

The wheels roll at the physically correct rate derived from the body-x
displacement in the log; the propeller spin (`prop_hz`, default 12 Hz) is
cosmetic. The default rendering everywhere remains the body-frame triad; STL
is opt-in via `drone_model`.
