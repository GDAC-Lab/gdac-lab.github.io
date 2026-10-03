---
layout: archive
title: "Research"
description: "Research at GDAC Lab, Nagoya Institute of Technology: constrained control of rotational motion on SO(3), explicit reference governors and control barrier functions, small-satellite attitude control, and wheeled drones for infrastructure inspection."
permalink: /research/
author_profile: true
lang: en
lang_ref: research
---

{% include base_path %}

## Overview

Operating a robot or a satellite as intended requires control over which direction the vehicle points. At the same time, every real machine carries limits that must be respected.

- The force a motor can produce has an **upper bound**.
- A telescope on a satellite must not be pointed toward the Sun.
- A vehicle running while pressed against a wall can take only a restricted set of attitudes.

In control engineering, such limits are called **constraints**. Our research centers on building theory for controlling rotational motion while satisfying constraints, together with verification on real hardware.

The principal applications are **satellites** and **drones**.

## Research themes

### 1. Constrained control of rotational motion

#### Rotation representations and singularities

The position of an object can be expressed by three numbers, x, y, and z. Representing its **orientation** is less straightforward.

Aircraft attitude is commonly described by three angles (pitch, roll, and yaw), known as **Euler angles**. This representation has a weakness: at certain attitudes the computation breaks down, a phenomenon known as gimbal lock in aviation and computer graphics.

Rather than decomposing orientation into three angles, we use a mathematical framework that treats rotation itself directly: the set of rotation matrices, written SO(3). Because this formulation has no singularities arising from how attitude is represented, the computation does not break down at any attitude.

#### Guaranteeing constraints under limited computation

A quick way to handle constraints is to bolt on rules of thumb, such as slowing down when a dangerous state is near. Such rules, however, give no **guarantee** that the constraints hold in every situation.

We work with the **Explicit Reference Governor (ERG)** and **control barrier functions (CBFs)**. Neither replaces the existing controller; both are added around it. The ERG modifies the **reference** given to the controller, and a CBF-based safety filter modifies the **command** the controller issues, keeping each within what the constraints allow. Because the modification rule is constructed mathematically, constraint satisfaction can be guaranteed in theory.

A second property is equally important: the computation is light.

Model predictive control, the representative approach to constrained control, predicts future motion and solves an optimization problem at every time step, which is a heavy load for hardware with limited computational capacity. The ERG instead updates the reference by evaluating expressions derived in advance, with no optimization to solve during operation, and a CBF-based safety filter can be computed in closed form for a single constraint, and otherwise requires only a small quadratic program. Both therefore fit on small computers.

**Selected results**

- [Explicit reference governor on SO(3) for torque and pointing constraint management](https://doi.org/10.1016/j.automatica.2023.111103) — *Automatica*, 2023
- [Attitude Constrained Control on SO(3): An Explicit Reference Governor Approach](https://doi.org/10.1109/CDC.2018.8618908) — *IEEE CDC*, 2018

#### Application: attitude control of small satellites

A satellite changes its attitude while orbiting the Earth, and several constraints apply simultaneously.

- Telescopes and other observation sensors must not be pointed toward the Sun, as intense sunlight can damage them.
- The communication antenna must point at the ground station during communication passes.
- The reaction wheels that reorient the spacecraft have an upper bound on the torque they can produce.

Furthermore, an on-board computer must meet launch-mass and on-board power limits and withstand the radiation environment of space, so its performance is considerably more limited than that of ground equipment. Approaches that solve an optimization problem at every time step are therefore difficult to apply.

The computationally light methods described above are effective in precisely this setting. We are currently working toward a framework in which several small satellites reorient cooperatively.

<figure class="media-figure">
  <img src="{{ base_path }}/images/research/sun-safe-slew.jpg" width="1280" height="720" loading="lazy" decoding="async" alt="The scene viewed from the Sun. The 25-degree keep-out cone around the Sun appears as an orange circle with the satellite at its centre. The red shortest path between two science targets runs through the circle; a second path bulges well outside it.">
  <figcaption>A 95&deg; retargeting slew with the Sun almost exactly in the way, <strong>seen from the Sun</strong>. From that direction the 25&deg; keep-out cone appears as the orange circle, and pointing anywhere inside it violates the constraint. The lower marker is the science target the satellite starts from and the upper one is where it has to get to: the red shortest path runs through the circle, the teal one stays outside it. The animation runs in your browser on the <a href="{{ base_path }}/sun-safe-slew/">satellite that avoids the Sun</a> page.</figcaption>
</figure>

> **JSPS KAKENHI, Grant-in-Aid for Scientific Research (B)** (FY2026–2029, 26K00967)
>
> "Constrained cooperative attitude control without online optimization for small satellite formations"

This theme is a collaboration with [Takahiro Sasaki](https://researchmap.jp/jaxasaki) of the Japan Aerospace Exploration Agency (JAXA) and Prof. [Noboru Sakamoto](https://www.st.nanzan-u.ac.jp/info/sakanobo/index.html) of Nanzan University.

#### Application: control design for three-dimensional rotation mechanisms

Gimbals, with several rotation axes nested inside one another, are the usual way to turn an object mechanically. Like Euler angles, however, a gimbal has attitudes at which two axes line up and rotation in some direction becomes impossible (**singular configurations**).

In a collaboration with Osaka University, we are developing a mechanism that has no singular configurations and can keep rotating in any direction. Our part is the control design that lets this mechanism achieve **high-precision rotational control**.

> **NEDO Young Researcher Support Program, joint research formation track** (selected in FY2026)
>
> "Development of an omnidirectional, endlessly rotating mechanism free of singular configurations based on geometric power transmission"

### 2. Wheeled drones and infrastructure inspection

#### A vehicle combining flight and ground locomotion

A drone can fly freely, but its power consumption in flight limits the operating time, and holding position right next to a wall without disturbing the attitude is not straightforward.

We therefore study **drones equipped with wheels**: the vehicle presses itself against a wall or ceiling, travels on its wheels, and transitions to flight as required.

<figure class="media-figure">
  <video poster="{{ base_path }}/images/research/wall-demo-poster.jpg" width="960" height="360" autoplay muted loop playsinline controls preload="metadata" aria-label="Simulation of a wheeled drone approaching a wall, making contact, climbing, holding, and descending">
    <source src="{{ base_path }}/images/research/wall-demo.mp4" type="video/mp4">
    <source src="{{ base_path }}/images/research/wall-demo.webm" type="video/webm">
  </video>
  <figcaption>Wall running in the simulator the lab develops and publishes. Left, a three-quarter view; right, the same run seen from the side: approach, contact, climb, hold, and descent. The green sphere is the reference position, and the arrows at the wheel–wall interface are the contact forces. An interactive version runs in your browser on the <a href="{{ base_path }}/simulator/">Simulator</a> page.</figcaption>
</figure>

From a control standpoint, this vehicle presents the following difficulties.

- The wheels do not slip laterally, so the directions of motion are restricted — a **nonholonomic constraint**.
- The **pressing force against the wall** must be regulated: too little and the wheels slip or the vehicle separates from the surface, too much and rolling resistance and the load on the airframe grow. Touching down too hard also makes the vehicle bounce off.
- Flight and ground locomotion alternate, so the nature of the dynamics itself changes.

Constraints are again central. To handle the pressing force, the attitudes admissible during contact, and limits on flight altitude, we combine **control barrier functions**, **input–output linearization**, **passivity-based methods**, and **model predictive path integral (MPPI) control**.

#### Application: infrastructure inspection

Detecting loose or delaminated concrete in tunnels and bridges, and loose tiles on building walls, relies on **hammering inspection**, in which the surface is struck and the resulting sound is assessed. At height this requires scaffolding, with the associated cost and risk.

Using wheeled drones, we are developing inspection systems for locations that are difficult for people to approach: **hammering inspection of wall tiles**, **inspection of bridge bearings** (the components supporting the bridge girders), and **surveys inside ceiling cavities**.

**Selected results**

- [Development of Wall Hammering Inspection Systems Using Two-Wheeled Multicopters](https://doi.org/10.20965/jrm.2024.p1043) — *Journal of Robotics and Mechatronics*, 2024
- [Position tracking control of a wheeled drone on a wall via input–output linearization](https://doi.org/10.5687/iscie.38.187) — *Trans. ISCIE*, 2025 (in Japanese)
- [Stable Haptic Shared Autonomy for Wall Landing of Two-Wheeled Drones via Control Barrier Functions](https://doi.org/10.1109/IECON58223.2025.11221286) — *IEEE IECON*, 2025

#### Control shared with a human operator

Rather than automating every action, we also study arrangements in which the operator commands the vehicle and the control system intervenes only to prevent unsafe motion. The presence of active constraints is conveyed to the operator through **haptic feedback**, while the safety guarantee itself is established theoretically.

## Other applications and collaborations

We also take part in the following themes as **collaborators**.

- **Vibration control of building structures** — suppressing the sway of buildings under earthquakes and wind. The equivalent-input-disturbance (EID) approach estimates the effect of wind and earthquakes from measurements, as an equivalent disturbance on the control input, and the estimate is used for active control that counteracts the motion (for example, estimating the wind load on a base-isolated building). Tuned-mass-damper (TMD) design based on robust control theory is also covered. [Representative paper (*Control Engineering Practice*, 2024)](https://doi.org/10.1016/j.conengprac.2024.105853)
- **Visual feedback control** — estimating the position and orientation of an object from camera images and using them for control, with estimation and control timed to the camera's frame rate. [Representative paper (*SICE JCMSI*, 2023)](https://doi.org/10.1080/18824889.2023.2247853)

A full list of papers is on the [Publications]({{ base_path }}/publications/) page, and our collaborators are listed under [People]({{ base_path }}/people/). Funding, awards, and other details are on [Satoshi Nakano's personal page](https://gdaclab.web.nitech.ac.jp/nakano/).
