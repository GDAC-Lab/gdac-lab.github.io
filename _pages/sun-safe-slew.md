---
layout: archive
title: "Sun-safe slew"
permalink: /sun-safe-slew/
author_profile: true
lang: en
lang_ref: sun-safe-slew
---

{% include base_path %}

A space telescope has to turn 95&deg; to its next science target, and the Sun sits almost exactly in the way. The animation below plays back a run of the constrained attitude control this lab works on, applied to that problem.
{: .notice}

{% include slew-demo.html %}

## Reading the scene

- **Teal** — where the telescope is actually looking: the ray now, the trail behind it.
- **Amber** — where the controller is telling it to look, a few degrees ahead.
- **Red** — the shortest path, drawn in full from the start, straight through the Sun.
- **Orange** — the 25&deg; exclusion cone around the Sun.
- The **wedge** between the Sun direction and the boresight carries the current separation as a number, and would turn red if the constraint were broken.

## The problem

The two science targets are 95&deg; apart, and the Sun lies 8&deg; off the shortest path between them. Point the optics within 25&deg; of the Sun and they are ruined, so the shortest slew is not available. Two constraints have to hold at once for the whole maneuver:

- the boresight stays at least **25&deg; from the Sun** — an exclusion cone, in the paper's notation a pointing constraint with `theta_c = 155°`;
- the reaction wheels are never asked for more than **0.17 N&middot;m**.

The vehicle is a rigid body with `J = diag(18, 25, 30) kg m²` in a 600 km orbit, and the slew starts from rest.

## What the run shows

|  | with the governor | reference applied direct |
| --- | --- | --- |
| closest approach to the Sun | **33.0&deg;** (limit 25&deg;) | **6.9&deg;** — 18.1&deg; inside the cone |
| peak wheel torque | **0.030 N&middot;m** (18 % of budget) | **0.498 N&middot;m** — 2.9&times; the limit |
| peak body rate | 0.54 &deg;/s | 4.2 &deg;/s |
| settling to within 1&deg; | 227 s | 40 s, but inadmissible |

The second column is the same inner loop handed the final attitude directly. It is not a strawman: it is what the constraints cost. The governor gets there in five times the time, and gets there admissibly.

Both tracks are drawn in the animation — the teal one is governed, the red one is the direct reference cutting straight through the Sun.

## Why it is not a path planned in advance

Nothing here was routed around the Sun beforehand. The inner loop is an ordinary PD controller that never sees either constraint. What changes is the *reference* it is given: an auxiliary attitude that the governor moves only as fast as a certified margin allows, and holds still when that margin runs out. The "safety budget used" gauge is that margin — the Lyapunov value as a fraction of the threshold the constraints permit. The telescope slides around the exclusion cone because the margin closes on that side and the governor stops pushing that way, not because a trajectory said so.

The practical consequence is the point of the method. No optimization problem is solved while the vehicle is moving: the governor evaluates expressions derived in advance. That is what makes the approach fit a small, radiation-tolerant on-board computer, where a solver running every time step does not. The [Research]({{ base_path }}/research/) page sets out the reasoning, and this animation is the small-satellite application described there.

## What the model leaves out

Stated plainly, so the picture is not read as a flight simulation.

- **Rigid body, no environmental torques.** Gravity-gradient, aerodynamic and solar-radiation-pressure torques — of order 1e-5 N&middot;m at this scale — are absent, as is flexible-appendage dynamics.
- **The wheels are a torque source only.** No momentum budget, no wheel-speed limit, no distribution across a wheel cluster, no desaturation. Stored momentum is reported for context; it is not a constraint in the model.
- **No body-rate limit.** A real mission caps the slew rate so the star trackers keep tracking. Here only the torque bound and the cone are enforced.
- **One keep-out cone.** An observatory usually carries Earth-limb, Moon and bright-object exclusions as well.
- **The torque bound is conservative.** It is the worst case over the whole safe level set, where attitude error and body rate oppose each other. A smooth slew never visits that corner, which is why the realized peak sits at 18 % of the limit.
- **The Earth is scenery.** Its direction follows from the orbit phase and enters the control problem nowhere. Its apparent size is honest: at 600 km it subtends 66&deg;, and the viewer computes that rather than picking a value.

## Where this comes from

The formulation is the explicit reference governor on SO(3):

- [Explicit reference governor on SO(3) for torque and pointing constraint management](https://doi.org/10.1016/j.automatica.2023.111103) — *Automatica*, 2023
- [Attitude Constrained Control on SO(3): An Explicit Reference Governor Approach](https://doi.org/10.1109/CDC.2018.8618908) — *IEEE CDC*, 2018

The run itself was computed offline; the page plays it back rather than solving anything, so opening it transfers about as much as a photograph and asks nothing of your processor beyond drawing. Every quantity on screen is one of the published continuous-time quantities. The spacecraft mesh is generated from primitives and released under CC0-1.0; the star field, the Earth and the Sun are procedural. The page uses [three.js](https://threejs.org/) (MIT), served from this site, and makes no external requests.

The browser demo of our wheeled-drone simulator, which does solve its physics live, is on the [Simulator]({{ base_path }}/simulator/) page.
