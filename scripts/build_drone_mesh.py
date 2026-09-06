#!/usr/bin/env python3
"""Turn the wheeled-QAV250 CAD into one compact mesh bundle for the browser demo.

Usage:  python3 scripts/build_drone_mesh.py [--check]

Reads the STL files in assets/models/wheeled-uav/meshes/ (kept in the repository
but excluded from the published site — see `exclude:` in _config.yml) and writes

    assets/models/wheeled-uav/drone-mesh.bin

which assets/js/simulator/drone-mesh.js loads after the visitor asks for the
demo. Re-run this whenever the CAD changes; the .bin is a build product but is
committed, because the site is served as static files with no build step of its
own beyond Jekyll.

What it does, per part
----------------------
1. Reads the binary STL (a triangle soup with no shared vertices).
2. Welds vertices on an exact micrometre grid, giving an indexed mesh.
3. Collapses edges (quadric error metric) down to the triangle budget below.
   The vehicle is a few hundred pixels across in the demo, so most of the CAD
   detail is far below one pixel.
4. Moves the part onto the pivot the renderer needs and converts mm to m.
5. Computes vertex normals that are smoothed only across shallow edges, so
   cylinders round off while plate corners stay sharp.
6. Packs positions (float32), normals (int8, normalised) and indices.

Everything the renderer needs to place a part — pivots, the propeller stations,
the wheel scale — is written into the bundle header, so the JavaScript side
hard-codes none of it.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "assets/models/wheeled-uav/meshes"
OUT = REPO / "assets/models/wheeled-uav/drone-mesh.bin"

MAGIC = b"GDACMSH1"

# Triangle budget per part. The frame carries all the shape the eye reads; the
# wheels and rotors are near-circular and survive heavy reduction.
BUDGET = {"frame": 6000, "wheel_l": 1200, "wheel_r": 1200, "propeller_cw": 1600, "propeller_ccw": 1600}

# Below this angle between neighbouring faces the shared edge is shaded smooth.
SMOOTH_ANGLE_DEG = 45.0

# The collision wheel in the MuJoCo model is a 0.15 m cylinder, and the demo's
# whole point is the wheels meeting the wall at that radius. The CAD wheel is
# 0.142 m, so it is scaled up about its axle; 6% is invisible next to a wheel
# drawn hanging off the wall.
WHEEL_RADIUS_CAD = 0.142
WHEEL_RADIUS_SIM = 0.15

# Rotor stations in the body frame (metres), from the CAD README. The CW/CCW
# assignment matches the yaw gears of the MuJoCo actuators named alongside them,
# so a rotor spins the way the model says it does.
PROPS = [
    {"station": "fl", "mesh": "propeller_cw", "pos": [0.075, 0.100, 0.009], "spin": -1, "actuator": "drone_thrust_fl"},
    {"station": "bl", "mesh": "propeller_ccw", "pos": [-0.075, 0.100, 0.009], "spin": 1, "actuator": "drone_thrust_bl"},
    {"station": "br", "mesh": "propeller_cw", "pos": [-0.075, -0.100, 0.009], "spin": -1, "actuator": "drone_thrust_br"},
    {"station": "fr", "mesh": "propeller_ccw", "pos": [0.075, -0.100, 0.009], "spin": 1, "actuator": "drone_thrust_fr"},
]


def read_stl(path: Path) -> np.ndarray:
    """Binary STL -> (n, 3, 3) triangle corners. ASCII STL is rejected loudly."""
    raw = path.read_bytes()
    if raw[:5] == b"solid" and b"facet normal" in raw[:2048]:
        raise SystemExit(f"{path.name}: ASCII STL; re-export as binary STL")
    if len(raw) < 84:
        raise SystemExit(f"{path.name}: too short to be an STL")
    count = struct.unpack("<I", raw[80:84])[0]
    want = 84 + count * 50
    if len(raw) < want:
        raise SystemExit(f"{path.name}: truncated ({len(raw)} bytes, header claims {want})")
    rows = np.frombuffer(raw[84:want], dtype=np.uint8).reshape(count, 50)
    # bytes 12..48 of each record are the three corners; 0..12 is the (unused,
    # frequently wrong) facet normal and 48..50 the attribute word.
    return rows[:, 12:48].copy().view("<f4").reshape(count, 3, 3).astype(np.float64)


def weld(tri: np.ndarray, grid: float = 1e-3) -> tuple[np.ndarray, np.ndarray]:
    """Triangle soup -> (vertices, faces), merging corners on a micrometre grid."""
    flat = tri.reshape(-1, 3)
    keys = np.round(flat / grid).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    verts = flat[first]
    faces = inverse.reshape(-1, 3)
    # An edge collapse cannot do anything useful with a triangle that has two
    # corners welded onto each other, and the simplifier dislikes them.
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])
    return verts, faces[keep]


def decimate(verts: np.ndarray, faces: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    if len(faces) <= target:
        return verts, faces
    import fast_simplification

    v, f = fast_simplification.simplify(
        verts.astype(np.float32), faces.astype(np.int32), target_count=int(target)
    )
    return np.asarray(v, dtype=np.float64), np.asarray(f, dtype=np.int64)


def _point_triangle_distance(pts: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Distance from each of `pts` (m, 3) to every triangle in `tri` (n, 3, 3).

    Returns (m, n). Closest-point-on-triangle by the usual barycentric region
    test, vectorised; the caller chunks so the (m, n, 3) temporaries stay small.
    """
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac = b - a, c - a
    ap = pts[:, None, :] - a[None]
    d1 = np.einsum("mnk,nk->mn", ap, ab)
    d2 = np.einsum("mnk,nk->mn", ap, ac)
    bp = pts[:, None, :] - b[None]
    d3 = np.einsum("mnk,nk->mn", bp, ab)
    d4 = np.einsum("mnk,nk->mn", bp, ac)
    cp = pts[:, None, :] - c[None]
    d5 = np.einsum("mnk,nk->mn", cp, ab)
    d6 = np.einsum("mnk,nk->mn", cp, ac)

    with np.errstate(divide="ignore", invalid="ignore"):
        vc = d1 * d4 - d3 * d2
        vb = d5 * d2 - d1 * d6
        va = d3 * d6 - d5 * d4
        denom = va + vb + vc
        # interior point, in barycentric coordinates
        v = np.nan_to_num(vb / denom)
        w = np.nan_to_num(vc / denom)
        closest = a[None] + v[..., None] * ab[None] + w[..., None] * ac[None]

        def on_edge(p0, edge, t):
            t = np.clip(np.nan_to_num(t), 0.0, 1.0)
            return p0[None] + t[..., None] * edge[None]

        edge_ab = on_edge(a, ab, d1 / (d1 - d3))
        edge_ac = on_edge(a, ac, d2 / (d2 - d6))
        edge_bc = on_edge(b, c - b, (d4 - d3) / ((d4 - d3) + (d5 - d6)))

    closest = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[..., None], edge_ab, closest)
    closest = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[..., None], edge_ac, closest)
    closest = np.where(((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0))[..., None], edge_bc, closest)
    closest = np.where(((d1 <= 0) & (d2 <= 0))[..., None], a[None], closest)
    closest = np.where(((d3 >= 0) & (d4 <= d3))[..., None], b[None], closest)
    closest = np.where(((d6 >= 0) & (d5 <= d6))[..., None], c[None], closest)
    return np.linalg.norm(pts[:, None, :] - closest, axis=2)


def surface_error(a_verts, a_faces, b_verts, b_faces, samples=1500) -> float:
    """Worst one-sided distance from the original surface to the reduced one.

    Samples the original faces by area and measures the true point-to-surface
    distance, so a large flat span reduced to two triangles scores ~0 rather
    than the vertex spacing.
    """
    rng = np.random.default_rng(0)
    tri = a_verts[a_faces]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    if area.sum() <= 0 or len(b_faces) == 0:
        return 0.0
    pick = rng.choice(len(tri), size=samples, p=area / area.sum())
    u, v = rng.random((samples, 1)), rng.random((samples, 1))
    over = (u + v > 1).ravel()
    u[over], v[over] = 1 - u[over], 1 - v[over]
    pts = tri[pick, 0] + u * e1[pick] + v * e2[pick]

    target = b_verts[b_faces]
    best = np.full(samples, np.inf)
    for i in range(0, samples, 128):
        block = pts[i : i + 128]
        rows = np.full(len(block), np.inf)
        for j in range(0, len(target), 2048):
            np.minimum(rows, _point_triangle_distance(block, target[j : j + 2048]).min(1), out=rows)
        best[i : i + 128] = rows
    return float(best.max())


def split_normals(verts: np.ndarray, faces: np.ndarray, angle_deg: float):
    """Per-vertex normals, duplicating a vertex where its faces meet sharply.

    Faces around a vertex are grouped while their normals stay within
    `angle_deg` of the group's running average; each group becomes one output
    vertex. Corners therefore keep a crisp edge and curved surfaces do not.
    """
    tri = verts[faces]
    face_n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    face_area = np.linalg.norm(face_n, axis=1)
    safe = np.where(face_area[:, None] > 0, face_area[:, None], 1.0)
    face_n = face_n / safe

    order = np.argsort(-face_area)  # large faces set the tone for their group
    incident: list[list[int]] = [[] for _ in range(len(verts))]
    for f in order:
        for c in faces[f]:
            incident[c].append(int(f))

    limit = np.cos(np.radians(angle_deg))
    out_pos: list[np.ndarray] = []
    out_nrm: list[np.ndarray] = []
    remap: dict[tuple[int, int], int] = {}  # (vertex, face) -> output vertex
    for vi, fs in enumerate(incident):
        if not fs:
            continue
        groups: list[tuple[np.ndarray, list[int]]] = []  # (summed normal, faces)
        for f in fs:
            n = face_n[f] * face_area[f]
            for gi, (acc, members) in enumerate(groups):
                ref = acc / (np.linalg.norm(acc) or 1.0)
                if float(ref @ face_n[f]) >= limit:
                    groups[gi] = (acc + n, members + [f])
                    break
            else:
                groups.append((n, [f]))
        for acc, members in groups:
            norm = np.linalg.norm(acc)
            out_index = len(out_pos)
            out_pos.append(verts[vi])
            out_nrm.append(acc / norm if norm > 0 else np.array([0.0, 0.0, 1.0]))
            for f in members:
                remap[(vi, f)] = out_index

    new_faces = np.array(
        [[remap[(int(c), int(f))] for c in faces[f]] for f in range(len(faces))], dtype=np.int64
    )
    return np.array(out_pos), np.array(out_nrm), new_faces


def build_part(name: str, transform) -> dict:
    """Read, reduce and pack one STL. `transform` maps CAD mm to demo metres."""
    tri = read_stl(SRC / f"{name}.stl")
    verts, faces = weld(tri)
    before = len(faces)
    rv, rf = decimate(verts, faces, BUDGET[name])
    err = surface_error(verts, faces, rv, rf)
    rv = transform(rv)
    pos, nrm, idx = split_normals(rv, rf, SMOOTH_ANGLE_DEG)
    print(
        f"  {name:16s} {before:>7,} -> {len(rf):>6,} tri   {len(pos):>6,} vert   "
        f"error <= {err:.2f} mm",
        file=sys.stderr,
    )
    if len(pos) > 65535:
        raise SystemExit(f"{name}: {len(pos)} vertices exceeds the 16-bit index range")
    return {
        "positions": pos.astype(np.float32),
        "normals": np.clip(np.rint(nrm * 127.0), -127, 127).astype(np.int8),
        "indices": idx.astype(np.uint16),
        "triangles": int(len(rf)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; do not write the bundle")
    args = ap.parse_args()

    if not SRC.is_dir():
        raise SystemExit(f"no CAD directory at {SRC}")

    mm = 1e-3
    wheel_scale = WHEEL_RADIUS_SIM / WHEEL_RADIUS_CAD

    def frame_tf(v):
        return v * mm

    def wheel_tf(v):
        # Centre on the axle, then grow to the collision radius. The renderer
        # hangs the result off the wheel body, which already carries the offset
        # to +/-0.2 m and the rolling angle.
        centred = v - np.array([0.0, (v[:, 1].min() + v[:, 1].max()) / 2.0, 0.0])
        return centred * mm * wheel_scale

    def prop_tf(v):
        return v * mm  # hub is already the mesh origin

    print("building the drone mesh bundle", file=sys.stderr)
    parts = {
        "frame": build_part("frame", frame_tf),
        "wheel_l": build_part("wheel_l", wheel_tf),
        "wheel_r": build_part("wheel_r", wheel_tf),
        "propeller_cw": build_part("propeller_cw", prop_tf),
        "propeller_ccw": build_part("propeller_ccw", prop_tf),
    }

    blobs: list[bytes] = []
    offset = 0
    manifest: dict[str, dict] = {}
    for name, part in parts.items():
        entry = {"triangles": part["triangles"]}
        for key in ("positions", "normals", "indices"):
            arr = part[key]
            data = arr.tobytes()
            pad = (-len(data)) % 4
            entry[key] = [offset, int(arr.size)]
            blobs.append(data + b"\0" * pad)
            offset += len(data) + pad
        manifest[name] = entry

    header = {
        "unit": "m",
        "frame": "vehicle body: x forward, y left, z up",
        "source": "assets/models/wheeled-uav/meshes/*.stl (lab CAD, reverse-engineered from the airframe)",
        "smoothAngleDeg": SMOOTH_ANGLE_DEG,
        "parts": manifest,
        "layout": {
            # Which primitive each part stands in for. The renderer reads the
            # geom's own orientation out of the model to undo it, so these are
            # names, not numbers.
            "bodyGeom": "drone_body_box",
            "wheels": [
                {"mesh": "wheel_l", "geom": "left_wheel_geom"},
                {"mesh": "wheel_r", "geom": "right_wheel_geom"},
            ],
            "wheelRadius": {"cad": WHEEL_RADIUS_CAD, "sim": WHEEL_RADIUS_SIM, "scale": wheel_scale},
            "props": PROPS,
            "hideSites": ["prop_fl", "prop_bl", "prop_br", "prop_fr"],
        },
    }
    head = json.dumps(header, separators=(",", ":")).encode("utf-8")
    head += b" " * ((-len(head)) % 4)

    payload = MAGIC + struct.pack("<I", len(head)) + head + b"".join(blobs)
    total_tri = sum(p["triangles"] for p in parts.values())
    print(
        f"  bundle {len(payload) / 1024:.0f} KB  ({total_tri:,} triangles, header {len(head)} B)",
        file=sys.stderr,
    )
    if args.check:
        print("  --check: not written", file=sys.stderr)
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(payload)
    print(f"  wrote {OUT.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
