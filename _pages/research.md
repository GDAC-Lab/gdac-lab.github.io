---
layout: archive
title: "Research"
permalink: /research/
author_profile: true
lang: en
lang_ref: research
---

{% include base_path %}

This page outlines our research directions. We refine the descriptions from time to time as our work develops.
{: .notice}

## Overview

Operating a robot or a satellite as intended requires control over which direction the vehicle points. At the same time, every real machine carries limits that must be respected.

- The force a motor can produce has an **upper bound**.
- An observation camera cannot be pointed towards the sun.
- A vehicle running while pressed against a wall can take only a restricted set of attitudes.

In control engineering such limits are called **constraints**. Our research centres on building theory for controlling rotational motion while satisfying constraints, together with verification on real hardware.

The principal applications are **satellites** and **drones**.

## Research themes

### 1. Constrained control of rotational motion

#### Representing rotation, and singularities

The position of an object can be expressed by three numbers, x, y and z. Representing its **orientation** is less straightforward.

Aircraft attitude is widely described by three angles — pitch, roll and yaw, known as **Euler angles**. This representation has a weakness: at certain attitudes the computation breaks down, a phenomenon known as gimbal lock in aviation and computer graphics.

Rather than decomposing orientation into three angles, we use a mathematical framework that treats rotation itself directly — the set of rotation matrices, written SO(3). This formulation yields control designs that do not break down at any attitude.

#### Guaranteeing constraints under limited computation

A straightforward approach to constraints is to add a mechanism that restricts the motion once a dangerous state is approached. Such an approach, however, provides no **guarantee** that the constraints hold in every situation.

We work with the **Explicit Reference Governor (ERG)** and **control barrier functions (CBFs)**. Rather than redesigning the controller itself, these methods reshape the reference supplied to the controller so that it remains within a safe region, which allows constraint satisfaction to be guaranteed.

A second property is equally important: these methods require no optimization to be solved during operation.

Model predictive control, the representative approach to constrained control, solves an optimization problem at every time step, which makes it difficult to run on hardware with limited computational capacity. ERG- and CBF-based methods instead evaluate expressions derived in advance, and can therefore be implemented on small computers. We are also studying this optimization-free framework in general form ([arXiv, 2026](https://arxiv.org/abs/2604.04001)).

**Selected results**

- [Explicit reference governor on SO(3) for torque and pointing constraint management](https://doi.org/10.1016/j.automatica.2023.111103) — *Automatica*, 2023
- [Attitude Constrained Control on SO(3): An Explicit Reference Governor Approach](https://doi.org/10.1109/CDC.2018.8618908) — *IEEE CDC*, 2018
- [Periodic Event-Triggered Explicit Reference Governor for Constrained Attitude Control on SO(3)](https://arxiv.org/abs/2604.04041) — arXiv, 2026

#### Application: attitude control of small satellites

A satellite changes its attitude while orbiting the Earth, and several constraints apply simultaneously.

- The observation camera must not be pointed towards the sun, as the sensor would be damaged.
- The communication antenna must remain directed at the ground station.
- The reaction wheels that reorient the spacecraft have an upper bound on the torque they can produce.

Furthermore, an on-board computer must meet mass limits at launch and withstand the radiation environment of space, so its performance is considerably more restricted than that of ground equipment. Approaches that solve an optimization problem at every time step are therefore difficult to apply.

The optimization-free methods described above are effective in precisely this setting. We are currently working towards a framework in which several small satellites reorient cooperatively.

> **JSPS KAKENHI, Grant-in-Aid for Scientific Research (B)** (FY2026–2029, 26K00967)
>
> "Constrained cooperative attitude control without online optimization for small satellite formations"

This theme is pursued as a collaboration with [Takahiro Sasaki](https://researchmap.jp/jaxasaki) (Japan Aerospace Exploration Agency, JAXA) and Prof. [Noboru Sakamoto](https://www.st.nanzan-u.ac.jp/info/sakanobo/index.html) (Nanzan University).

#### Application: control design for three-dimensional rotation mechanisms

We are also engaged in a collaboration on control design for mechanisms that produce three-dimensional rotation, aimed at achieving **high-precision rotational control**.

{% comment %}
Once disclosure is cleared, add the partner, project name and period here.
A Liquid comment never reaches the published HTML.
{% endcomment %}

### 2. Wheeled drones and infrastructure inspection

#### A vehicle combining flight and ground locomotion

A drone can fly freely, but its power consumption in flight limits the available operating time, and holding position in the immediate vicinity of a wall without disturbing the attitude is not straightforward.

We therefore study **drones equipped with wheels**: the vehicle presses itself against a wall or ceiling, travels on its wheels, and transitions to flight as required.

<figure class="media-figure">
  <video poster="{{ base_path }}/images/research/wall-demo-poster.jpg" width="960" height="360" autoplay muted loop playsinline controls preload="metadata" aria-label="Simulation of a wheeled drone approaching a wall, making contact, climbing, holding and descending">
    <source src="{{ base_path }}/images/research/wall-demo.mp4" type="video/mp4">
    <source src="{{ base_path }}/images/research/wall-demo.webm" type="video/webm">
  </video>
  <figcaption>Wall riding in the simulator the lab develops and publishes. Left, a three-quarter view; right, the same run seen from the side: approach, contact, climb, hold and descent. The green sphere is the reference position and the arrows at the wheel–wall interface are the contact forces. An interactive version runs in your browser on the <a href="{{ base_path }}/simulator/">Simulator</a> page.</figcaption>
</figure>

From a control standpoint this vehicle presents the following difficulties.

- The wheels do not slip laterally, so the directions of motion are restricted — a **nonholonomic constraint**.
- The **pressing force against the wall** must be regulated: too little and the vehicle separates from the surface, too much and it rebounds.
- Flight and ground locomotion alternate, so the nature of the dynamics itself changes.

Constraints are again central. To handle the pressing force, the attitudes admissible during contact, and limits on flight altitude, we combine **control barrier functions**, **input–output linearization**, **passivity-based methods** and **model predictive path integral (MPPI) control**.

#### Application: infrastructure inspection

Detecting loose or delaminated tiles on tunnels, bridges and building walls is carried out by **hammering inspection**, in which a surface is struck and the resulting sound is assessed. At height this requires scaffolding, with the associated cost and risk.

Using wheeled drones, we are developing inspection systems for locations that are difficult for people to approach: **hammering inspection of wall tiles**, **inspection of bridge bearings** (the components supporting the bridge girders), and **surveys inside ceiling cavities**.

**Selected results**

- [Development of Wall Hammering Inspection Systems Using Two-Wheeled Multicopters](https://doi.org/10.20965/jrm.2024.p1043) — *Journal of Robotics and Mechatronics*, 2024
- [Position tracking control of a wheeled drone on a wall via input–output linearization](https://doi.org/10.5687/iscie.38.187) — *Trans. ISCIE*, 2025 (in Japanese)
- [Stable Haptic Shared Autonomy for Wall Landing of Two-Wheeled Drones via Control Barrier Functions](https://doi.org/10.1109/IECON58223.2025.11221286) — *IEEE IECON*, 2025

#### Control shared with a human operator

Rather than automating every action, we also study arrangements in which the operator commands the vehicle and the control system intervenes only to prevent unsafe motion. The presence of active constraints is conveyed to the operator through **haptic feedback**, while the safety guarantee itself is established theoretically.

## Other applications and collaborations

We also take part in the following themes as **collaborators**.

- **Vibration control of building structures** — suppressing the sway of buildings under earthquakes and wind. Disturbance estimation based on the equivalent-input-disturbance (EID) approach is applied to tuned mass damper design and to the control of base-isolated buildings. [Representative paper (*Control Engineering Practice*, 2024)](https://doi.org/10.1016/j.conengprac.2024.105853)
- **Visual feedback control** — estimating the position and orientation of an object from camera images and using them for control. [Representative paper (*SICE JCMSI*, 2023)](https://doi.org/10.1080/18824889.2023.2247853)

Our wheeled-drone simulator is publicly available, and the [Simulator]({{ base_path }}/simulator/) page runs a demo of it in your browser.

A full list of papers is on the [Publications]({{ base_path }}/publications/) page and our collaborators are listed under [People]({{ base_path }}/people/); funding, awards and other details are on the [faculty page](https://mcontrol.web.nitech.ac.jp/nakano/).
