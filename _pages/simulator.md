---
layout: archive
title: "Simulator"
description: "The wheeled-drone simulator of GDAC Lab, Nagoya Institute of Technology, with a demo that solves MuJoCo physics in your own browser."
permalink: /simulator/
author_profile: true
lang: en
lang_ref: simulator
---

{% include base_path %}

Our wheeled-drone simulator is publicly available. The demo below is not a recording: it solves the simulator's physics in your browser as you watch.
{: .notice}

{% include simulator-demo.html %}

## What you are looking at

A vehicle with four rotors and two wheels. Its shape comes from measurements of the lab's own airframe.

To climb the wall it does nothing special: **the target position is simply placed behind the wall face**. The vehicle tries to reach it, the wall stops it, and the wall's reaction becomes the force pressing the wheels into the surface. The wheels roll, so vertical motion stays free. There is no dedicated pressing controller.

Attitude is controlled without decomposing rotation into three angles; the rotation matrix is used directly. That formulation does not break down at any attitude, and it is the idea at the center of our work on rotational control. See the [Research]({{ base_path }}/research/) page for more.

## The simulator itself

It handles single and multiple vehicles, walls and curved terrain, and runs with a real flight controller in the loop. The source, its license and its citation information are on [GitHub](https://github.com/GDAC-Lab/mujoco-wheeled-uav-simulator).
