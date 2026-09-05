---
layout: archive
title: "Simulator"
permalink: /simulator/
author_profile: true
lang: en
lang_ref: simulator
---

{% include base_path %}

Our wheeled-drone simulator is publicly available. The demo below runs the same physics engine the simulator uses, inside your browser. It is not a recording.
{: .notice}

{% include simulator-demo.html %}

## About this demo

**The physics is being solved in your browser.** The page loads MuJoCo compiled to WebAssembly and gives it the same model file the desktop simulator generates, integrated at the same 1 ms timestep. The control law is the simulator's own geometric controller, ported to JavaScript and checked to agree numerically.

Move the target and the vehicle works out what to do from there. Nothing is played back.

## What you are looking at

The vehicle has four rotors and two wheels. To climb the wall, the controller does nothing special: **the target position is simply placed behind the wall face**. The vehicle tries to reach it, the wall stops it, and the wall's reaction becomes the pressing force. The wheels roll on the wall surface, so vertical motion stays free. There is no dedicated pressing controller.

Attitude is controlled without decomposing rotation into three angles — the rotation matrix is used directly. That formulation does not break down at any attitude, and it is the idea at the centre of our work on rotational control. See the [Research]({{ base_path }}/research/) page for more.

- **Moving the target** — drag the green sphere in the 3D view, or drag on the pad in its lower-left corner (sideways is toward the wall, up is height). With the pad focused, the arrow keys work too
- **The "+" on the wall-direction value** — how far the target sits beyond the point where the wheels meet the wall (1.80 m). That excess is what becomes the pressing force
- **Real-time factor** — how fast the physics is being solved relative to real time. 1.00× means it is keeping up

## The simulator itself

The simulator pairs a MuJoCo physics process (Python) with controllers connected over UDP (MATLAB or Python). It supports single and multiple vehicles, walls and curved terrain, and hardware-in-the-loop runs with a real PX4 flight controller.

- Repository: [GDAC-Lab/mujoco-wheeled-uav-simulator](https://github.com/GDAC-Lab/mujoco-wheeled-uav-simulator)
- Licence: see `LICENSE` in the repository
- Citation: use `CITATION.cff` in the repository

This demo uses a WebAssembly build of [MuJoCo](https://mujoco.org/) (Apache-2.0) and [three.js](https://threejs.org/) (MIT). Both are served from this site, so the page makes no external requests.

## Requirements

The demo needs a browser with WebGL and WebAssembly. Loading the physics engine transfers a few megabytes, so nothing is fetched just by opening the page: the transfer starts **only when you press "Load and run"**, happens once, and affects this page only. If it does not run for you, the [Research]({{ base_path }}/research/) page describes the work in words.
