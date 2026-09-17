---
layout: archive
title: "A satellite that avoids the Sun"
description: "A satellite turns 95 degrees with the Sun in the way, and the controller finds its own way around: an animation of constrained attitude control from GDAC Lab, Nagoya Institute of Technology."
permalink: /sun-safe-slew/
author_profile: true
lang: en
lang_ref: sun-safe-slew
---

{% include base_path %}

A satellite has to turn 95&deg; to put its telescope on the next science target, and the Sun sits almost exactly in the way. Pointing the telescope at the Sun would destroy it, so the short way round is not available. The animation below is this lab's controller solving that problem.
{: .notice}

{% include slew-demo.html %}

## Reading the scene

The Sun, the keep-out region and the two science targets are labelled on screen. The lines are:

- **Teal** — where the satellite is actually pointing, and the trail behind it
- **Amber** — the direction the controller is currently aiming for; the teal ray follows it a little behind
- **Red** — the path taken by turning the short way without avoiding the Sun, which runs through the keep-out region
- **Orange cone** — the 25&deg; keep-out region around the Sun

The angle to the Sun is shown as a number on screen. It turns red below 25&deg;.

## The path is not planned in advance

No detour around the Sun is worked out beforehand. The controller itself is an ordinary one that knows nothing about the Sun or about the torque limit. The only thing that changes is **where the target is put**.

The target is moved a little at a time towards the final attitude, but it is not moved in a direction that would take it somewhere unsafe. The amber ray on screen is that target. The satellite goes around the keep-out region because that is what is left of the directions it may move in, not because the detour was specified. The "safety margin used" gauge shows how close the current state is to the constraints.

What makes this practical is that **no optimization is solved while it runs**. The controller evaluates expressions worked out in advance, which is why it fits on the small, radiation-hardened computers a spacecraft carries. The [Research]({{ base_path }}/research/) page sets out the idea.

## Results

With this controller, the satellite never points closer to the Sun than **33&deg;** — the limit is 25&deg; — and never asks the reaction wheels for more than **18 %** of their torque.

For comparison: give the same controller the final attitude directly as its target (the red path on screen), and it passes **6.9&deg;** from the Sun and demands **2.9 times** the torque the wheels can produce. The constrained run takes five times as long to get there, which is what respecting the constraints costs.

## What this is not

This is a calculation made to show how the control works. Disturbance torques, a limit on how fast the spacecraft may turn, and keep-out regions for the Earth and the Moon — all of which a real mission has to account for as well — are not part of it.

## Sources

The formulation is an Explicit Reference Governor (ERG) on SO(3).

- [Explicit reference governor on SO(3) for torque and pointing constraint management](https://doi.org/10.1016/j.automatica.2023.111103) — *Automatica*, 2023
- [Attitude Constrained Control on SO(3): An Explicit Reference Governor Approach](https://doi.org/10.1109/CDC.2018.8618908) — *IEEE CDC*, 2018

The run was computed in advance; this page only plays it back. The demo that solves its physics in your browser, on a wheeled drone, is on the [Simulator]({{ base_path }}/simulator/) page.
