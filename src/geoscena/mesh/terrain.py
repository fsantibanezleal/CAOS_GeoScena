"""Terrain meshing: a DEM grid to an adaptive triangle mesh in AOI-local metres.

Implements a real greedy-refinement TIN (the Delatin idea) in pure Python over
``scipy.spatial.Delaunay`` -- no native compiler needed. Starting from the four grid
corners, it repeatedly inserts the grid point whose interpolated triangle height is
furthest from the true DEM value, re-triangulating until the worst vertical error drops
below ``max_error_m`` or a vertex budget is hit. The result is dense where terrain is
complex and sparse where it is flat, giving far fewer triangles than a full-grid mesh for
the same fidelity. Vertices are projected from WGS84 to the AOI local metric frame.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay

from geoscena.aoi import AOI
from geoscena.bundle import MeshLayer
from geoscena.fetch.dem import DemGrid


def _fill_nan(z: np.ndarray) -> np.ndarray:
    if not np.isnan(z).any():
        return z
    z = z.copy()
    m = np.nanmean(z)
    z[np.isnan(z)] = 0.0 if np.isnan(m) else m
    return z


def _interp_bary(tri: Delaunay, z_at_vertex: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Linear-interpolate a scalar defined at TIN vertices onto grid points ``pts``."""
    simplex = tri.find_simplex(pts)
    out = np.full(pts.shape[0], np.nan)
    valid = simplex >= 0
    if not valid.any():
        return out
    s = simplex[valid]
    X = tri.transform[s, :2]
    r = pts[valid] - tri.transform[s, 2]
    b01 = np.einsum("ijk,ik->ij", X, r)
    bary = np.column_stack([b01, 1.0 - b01.sum(axis=1)])
    vids = tri.simplices[s]
    out[valid] = np.einsum("ij,ij->i", bary, z_at_vertex[vids])
    return out


def _adaptive_tin(
    z: np.ndarray, max_error_m: float, max_vertices: int
) -> tuple[np.ndarray, np.ndarray]:
    """Batched greedy Delatin-style refinement. Returns (vertex_px[N,3], faces[M,3]).

    Each round re-triangulates the current vertex set, measures the vertical error at
    every grid point, and inserts a spatially-separated batch of the highest-error points
    (rather than one point per Delaunay rebuild). This keeps the adaptive-TIN quality while
    cutting the number of triangulations from thousands to a few dozen, so it scales to
    many AOIs. Points inserted per round grow geometrically until the budget or the error
    target is reached.
    """
    rows, cols = z.shape
    gx, gy = np.meshgrid(np.arange(cols), np.arange(rows))
    grid_xy = np.column_stack([gx.ravel(), gy.ravel()]).astype("float64")
    grid_z = z.ravel().astype("float64")

    chosen_idx = {
        0,
        cols - 1,
        (rows - 1) * cols,
        rows * cols - 1,
        # a few mid-edge + centre seeds to avoid a degenerate start
        cols // 2,
        (rows - 1) * cols + cols // 2,
        (rows // 2) * cols,
        (rows // 2) * cols + cols - 1,
        (rows // 2) * cols + cols // 2,
    }

    def sep_pick(cand_idx: np.ndarray, cand_err: np.ndarray, k: int, min_sep: float) -> list[int]:
        """Pick up to k highest-error candidates that are >= min_sep apart (px)."""
        order = np.argsort(-cand_err)
        picked: list[int] = []
        pxy: list[tuple[float, float]] = []
        for o in order:
            gi = int(cand_idx[o])
            x, y = grid_xy[gi]
            if all((x - px) ** 2 + (y - py) ** 2 >= min_sep * min_sep for px, py in pxy):
                picked.append(gi)
                pxy.append((x, y))
                if len(picked) >= k:
                    break
        return picked

    batch = 32
    min_sep = max(2.0, min(rows, cols) / 40.0)
    while len(chosen_idx) < max_vertices:
        idx = np.fromiter(chosen_idx, dtype="int64")
        pts = grid_xy[idx]
        zc = grid_z[idx]
        tri = Delaunay(pts)
        approx = _interp_bary(tri, zc, grid_xy)
        err = np.abs(approx - grid_z)
        err[np.isnan(err)] = 0.0
        if float(err.max()) <= max_error_m:
            break
        # candidates over the error threshold, minus already-chosen
        over = np.where(err > max_error_m)[0]
        over = np.setdiff1d(over, idx, assume_unique=False)
        if over.size == 0:
            break
        k = min(batch, max_vertices - len(chosen_idx))
        picks = sep_pick(over, err[over], k, min_sep)
        if not picks:
            picks = [int(over[np.argmax(err[over])])]
        chosen_idx.update(picks)
        batch = min(batch * 2, 512)

    idx = np.fromiter(chosen_idx, dtype="int64")
    pts = grid_xy[idx]
    tri = Delaunay(pts)
    verts_px = np.column_stack([pts[:, 0], pts[:, 1], grid_z[idx]])
    return verts_px, tri.simplices.astype("int64")


def terrain_mesh(
    aoi: AOI,
    dem: DemGrid,
    max_error_m: float = 1.5,
    max_vertices: int = 6000,
    base_color: tuple[int, int, int] = (70, 74, 82),
) -> MeshLayer:
    """Build an adaptive terrain MeshLayer from a DEM grid."""
    z = _fill_nan(np.asarray(dem.z, dtype="float64"))
    rows, cols = z.shape
    verts_px, faces = _adaptive_tin(z, float(max_error_m), int(max_vertices))

    px, py, elev = verts_px[:, 0], verts_px[:, 1], verts_px[:, 2]
    dx = (dem.east - dem.west) / cols
    dy = (dem.north - dem.south) / rows
    lon = dem.west + (px + 0.5) * dx
    lat = dem.north - (py + 0.5) * dy
    ex, ny = aoi.to_local(lon, lat)

    verts = np.column_stack([ex, ny, elev]).astype("float32")
    colors = np.tile(np.array(base_color, dtype="uint8"), (verts.shape[0], 1))
    return MeshLayer(name="terrain", vertices=verts, faces=faces, colors=colors)
