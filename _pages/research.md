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

Our group develops **control theory and experimental validation for safety-critical systems**, with applications in **robotics and mobility**. We focus on **nonlinear dynamics and constrained systems in real environments**, aiming to **jointly ensure safety and performance** in controller design.

## Research themes

### 1. Safety-critical control

With the spread of autonomous driving, drones, and related technologies, **control methods with explicit safety guarantees** are increasingly important. We study controller design based on ideas such as **control barrier functions and passivity**, enforcing **state and input constraints** while preserving **stability and safety**. We also build **robust control** approaches that account for **disturbances and model uncertainty**, and we verify effectiveness through **hardware experiments**.

### 2. Rigid-body attitude control and applications

Attitude motion of a rigid body is described by **nonlinear dynamics on the rotation group**, which makes control both theoretically rich and practically relevant. We develop **attitude control methods that respect geometric structure** on groups such as **SE(3) and SO(3)** to obtain **singularity-free, consistent feedback designs**. A central focus is **attitude synchronization and tracking for multirotors and related aerial platforms**, while **spacecraft and other vehicles** remain an important part of the application scope where the same geometric viewpoint applies.

### 3. Wheeled drones (flight with contact and rolling)

A distinctive theme in our lab is **drones equipped with wheels**, combining **aerial motion with contact and ground locomotion**. These systems involve **nonholonomic constraints, contact forces, and hybrid dynamics**, and require approaches beyond classical multirotor control. We combine tools such as **model predictive control, disturbance observers, and passivity-based methods** to enable behaviors including **wall following, obstacle avoidance, and infrastructure inspection**. This includes system development aimed at **inspection of bridges and built structures**.
