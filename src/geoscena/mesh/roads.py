"""Road/rail meshing: buffer line segments into flat ribbons draped on the terrain.

Each transportation segment (a WGS84 line) is projected to AOI-local metres, buffered by a
class-dependent half-width into a ribbon polygon, triangulated, and placed at the terrain
elevation plus a small offset so the ribbon reads as a lit surface on the ground (the
"neon road" identity is applied by the viewer's material). Rail is styled distinctly.
"""

from __future__ import annotations

import numpy as np
from mapbox_earcut import triangulate_float64
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon

from geoscena.aoi import AOI
from geoscena.bundle import MeshLayer

# Approximate half-widths (metres) by Overture road class.
HALF_WIDTH = {
    "motorway": 8.0,
    "trunk": 7.0,
    "primary": 6.0,
    "secondary": 5.0,
    "tertiary": 4.0,
    "residential": 3.0,
    "living_street": 2.5,
    "service": 2.0,
    "footway": 1.2,
    "path": 1.0,
    "cycleway": 1.2,
}
DEFAULT_HALF_WIDTH = 3.0
ROAD_COLOR = (120, 200, 255)
RAIL_COLOR = (255, 160, 90)


def _lines(geom) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return []


def road_ribbons(
    aoi: AOI,
    roads,  # GeoDataFrame (WGS84) with geometry + optional 'class'
    dem=None,
    z_offset_m: float = 0.4,
    is_rail: bool = False,
) -> MeshLayer:
    """Buffer road/rail lines into a single ribbon MeshLayer draped on the terrain."""
    tr = aoi.transformer_to_local()
    color = RAIL_COLOR if is_rail else ROAD_COLOR

    all_v: list[np.ndarray] = []
    all_f: list[np.ndarray] = []
    voff = 0

    classes = roads["class"].to_numpy() if "class" in getattr(roads, "columns", []) else None
    for i, geom in enumerate(roads.geometry.to_numpy()):
        cls = classes[i] if classes is not None else None
        hw = HALF_WIDTH.get(str(cls), DEFAULT_HALF_WIDTH)
        for line in _lines(geom):
            if line.is_empty or line.length == 0:
                continue
            xs, ys = tr.transform(*line.xy)
            local = LineString(np.column_stack([xs, ys]))
            ribbon = local.buffer(hw, cap_style=2, join_style=1)
            if ribbon.is_empty:
                continue
            # buffer() may yield a Polygon or a MultiPolygon; handle both.
            polys = (
                [ribbon]
                if isinstance(ribbon, Polygon)
                else list(ribbon.geoms)
                if isinstance(ribbon, MultiPolygon)
                else []
            )
            for poly in polys:
                if poly.exterior is None:
                    continue
                ext = np.asarray(poly.exterior.coords)[:-1]
                if ext.shape[0] < 3:
                    continue
                rings = np.array([ext.shape[0]], dtype="uint32")
                tri = triangulate_float64(ext.astype("float64"), rings).reshape(-1, 3)
                if tri.shape[0] == 0:
                    continue
                if dem is not None:
                    lon, lat = tr.transform(ext[:, 0], ext[:, 1], direction="INVERSE")
                    z = dem.sample(lon, lat)
                    z = np.where(np.isfinite(z), z, np.nanmean(z) if np.isfinite(z).any() else 0.0)
                else:
                    z = np.zeros(ext.shape[0])
                verts = np.column_stack([ext, z + z_offset_m]).astype("float32")
                all_v.append(verts)
                all_f.append(tri.astype("int64") + voff)
                voff += verts.shape[0]

    if not all_v:
        return MeshLayer(
            "rail" if is_rail else "roads",
            np.zeros((0, 3), "float32"),
            np.zeros((0, 3), "int64"),
        )
    verts = np.vstack(all_v)
    return MeshLayer(
        name="rail" if is_rail else "roads",
        vertices=verts,
        faces=np.vstack(all_f),
        colors=np.tile(np.array(color, dtype="uint8"), (verts.shape[0], 1)),
    )
