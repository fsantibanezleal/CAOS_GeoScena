"""Population meshing: turn a GHS-POP grid into an extruded, colour-coded cell layer.

Each populated ~100 m cell becomes a low prism whose height and colour encode the residential
population there (log-scaled). This gives the scene a real demographic layer, toggle-able like the
others, that reads the density pattern of the area at a glance.
"""

from __future__ import annotations

import numpy as np

from geoscena.aoi import AOI
from geoscena.bundle import MeshLayer
from geoscena.fetch.ghsl import Population


def _viridis_like(t: np.ndarray) -> np.ndarray:
    """A compact blue->green->yellow->red density ramp (t in [0,1]) -> uint8 RGB."""
    t = np.clip(t, 0, 1)
    r = np.clip(1.4 * t - 0.2, 0, 1)
    g = np.clip(1.2 * np.sin(np.pi * t * 0.9), 0, 1)
    b = np.clip(1.0 - 1.3 * t, 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype("uint8")


def population_mesh(
    aoi: AOI,
    pop: Population,
    dem=None,
    max_height_m: float = 220.0,
    z_offset_m: float = 1.0,
) -> MeshLayer:
    """Build an extruded population-cell MeshLayer (only cells with people)."""
    counts = np.asarray(pop.counts, dtype="float64")
    rows, cols = counts.shape
    lon_g, lat_g = pop.lonlat_grid()

    mask = counts > 0.5
    if not mask.any():
        return MeshLayer("population", np.zeros((0, 3), "float32"), np.zeros((0, 3), "int64"))

    vals = counts[mask]
    lons = lon_g[mask]
    lats = lat_g[mask]
    # log-scaled height + colour
    lv = np.log1p(vals)
    t = (lv - lv.min()) / (float(np.ptp(lv)) + 1e-9)
    heights = z_offset_m + t * max_height_m
    colors_cell = _viridis_like(t)

    ex, ny = aoi.to_local(lons, lats)
    base = dem.sample(lons, lats) if dem is not None else np.zeros_like(ex)
    base = np.where(np.isfinite(base), base, float(np.nanmin(base)) if np.isfinite(base).any() else 0.0)

    # cell half-size in local metres
    dlon = (pop.east - pop.west) / cols
    dlat = (pop.north - pop.south) / rows
    hw = abs(aoi.to_local(np.array([pop.west + dlon]), np.array([lats[0]]))[0][0] - ex[0]) * 0.0
    # simpler: derive half-size from ~100 m cells directly
    hx = 50.0
    hy = 50.0

    all_v, all_f, all_c, voff = [], [], [], 0
    for i in range(ex.shape[0]):
        cx, cy = ex[i], ny[i]
        z0 = base[i] + z_offset_m
        z1 = z0 + heights[i]
        corners = np.array(
            [[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy]]
        )
        roof = np.column_stack([corners, np.full(4, z1)])
        floor = np.column_stack([corners, np.full(4, z0)])
        verts = np.vstack([roof, floor]).astype("float32")
        faces = [[0, 1, 2], [0, 2, 3]]  # roof
        for k in range(4):
            a, b = k, (k + 1) % 4
            faces += [[a, b + 4, b], [a, a + 4, b + 4]]
        all_v.append(verts)
        all_f.append(np.asarray(faces, dtype="int64") + voff)
        all_c.append(np.tile(colors_cell[i], (8, 1)))
        voff += 8

    return MeshLayer(
        name="population",
        vertices=np.vstack(all_v),
        faces=np.vstack(all_f),
        colors=np.vstack(all_c),
    )
