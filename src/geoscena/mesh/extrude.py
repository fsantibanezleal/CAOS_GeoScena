"""Building meshing: extrude footprint polygons into prisms in AOI-local metres.

Each building footprint (a shapely polygon in WGS84) is projected to the AOI local metric
frame, triangulated (roof via ear-cutting), and extruded from a base elevation up to
``base + height`` to form a closed prism: roof cap + vertical walls. Per-vertex colour can
encode height or land-use class; per-feature attributes (height, source, class, index) are
attached so the viewer can show a value read-out on pick.

The base elevation for each building is sampled from the terrain DEM so buildings sit on
the ground rather than at z=0.
"""

from __future__ import annotations

import numpy as np
from mapbox_earcut import triangulate_float64
from shapely.geometry import MultiPolygon, Polygon

from geoscena.aoi import AOI
from geoscena.bundle import MeshLayer


def _height_color(h: float, hmax: float) -> tuple[int, int, int]:
    """Blue-to-amber ramp by normalized height (the inspiration's height colouring)."""
    t = 0.0 if hmax <= 0 else min(1.0, h / hmax)
    r = int(40 + t * 215)
    g = int(90 + t * 90)
    b = int(200 - t * 150)
    return (r, g, b)


def _str_or_none(v) -> str | None:
    return None if v is None else str(v)


def _polys(geom) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return []


def extrude_buildings(
    aoi: AOI,
    buildings,  # GeoDataFrame (WGS84) with geometry
    heights: np.ndarray,
    height_source: np.ndarray,
    base_elev: np.ndarray | None = None,
    classes: np.ndarray | None = None,
    modalities: dict[str, np.ndarray] | None = None,
    name: str = "buildings",
) -> MeshLayer:
    """Extrude all footprints into one merged MeshLayer.

    Args:
        buildings: GeoDataFrame in WGS84.
        heights: per-building height in metres (from the ladder).
        height_source: per-building provenance tag.
        base_elev: per-building ground elevation in metres (0 if None).
        classes: optional per-building land-cover class code.
        modalities: optional {attr_name: per-building value array} fused topic attributes
            (solar, soil, ...) sampled at the footprint centroid; attached to each feature.
        name: layer name (use "buildings_lite" for a reduced-detail LoD proxy).
    """
    tr = aoi.transformer_to_local()
    hmax = float(np.nanpercentile(heights, 95)) if len(heights) else 1.0

    def col(name: str):
        return buildings[name].to_numpy() if name in getattr(buildings, "columns", []) else None

    c_floors = col("num_floors")
    c_minh = col("min_height")
    c_bclass = col("class")
    c_subtype = col("subtype")
    c_roof = col("roof_shape")

    def _attr(arr, i):
        if arr is None:
            return None
        v = arr[i]
        try:
            return None if v is None or (isinstance(v, float) and np.isnan(v)) else v
        except (TypeError, ValueError):
            return v

    all_v: list[np.ndarray] = []
    all_f: list[np.ndarray] = []
    all_c: list[np.ndarray] = []
    all_fid: list[np.ndarray] = []
    features: list[dict] = []
    voff = 0

    geoms = buildings.geometry.to_numpy()
    for i, geom in enumerate(geoms):
        h = float(heights[i])
        z0 = float(base_elev[i]) if base_elev is not None else 0.0
        color = _height_color(h, hmax)
        area_m2 = 0.0
        for poly in _polys(geom):
            if poly.is_empty or poly.exterior is None:
                continue
            ext = np.asarray(poly.exterior.coords)[:-1]  # drop closing dup
            if ext.shape[0] < 3:
                continue
            x, y = tr.transform(ext[:, 0], ext[:, 1])
            ring = np.column_stack([x, y]).astype("float64")
            # shoelace footprint area in local metres
            area_m2 += abs(
                float(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], -1)))
            ) / 2.0
            rings = np.array([ring.shape[0]], dtype="uint32")
            tri = triangulate_float64(ring, rings).reshape(-1, 3)
            if tri.shape[0] == 0:
                continue
            nring = ring.shape[0]

            roof = np.column_stack([ring, np.full(nring, z0 + h)]).astype("float32")
            base = np.column_stack([ring, np.full(nring, z0)]).astype("float32")
            verts = np.vstack([roof, base])

            faces = list(tri)  # roof cap
            for k in range(nring):  # walls
                a, b = k, (k + 1) % nring
                ra, rb = a, b
                ba, bb = a + nring, b + nring
                faces.append([ra, bb, rb])
                faces.append([ra, ba, bb])
            faces = np.asarray(faces, dtype="int64") + voff

            all_v.append(verts)
            all_f.append(faces)
            all_c.append(np.tile(np.array(color, dtype="uint8"), (verts.shape[0], 1)))
            all_fid.append(np.full(verts.shape[0], i, dtype="int32"))
            voff += verts.shape[0]

        floors = _attr(c_floors, i)
        feat = {
            "id": int(i),
            "height_m": round(h, 2),
            "height_source": str(height_source[i]),
            "class": int(classes[i]) if classes is not None else None,  # WorldCover land cover
            "area_m2": round(area_m2, 1),
            "num_floors": int(floors) if floors is not None else None,
            "min_height_m": (round(float(_attr(c_minh, i)), 1) if _attr(c_minh, i) is not None else None),
            "use": _str_or_none(_attr(c_bclass, i)),  # Overture building class (residential, commercial, ...)
            "subtype": _str_or_none(_attr(c_subtype, i)),
            "roof_shape": _str_or_none(_attr(c_roof, i)),
        }
        for mkey, marr in (modalities or {}).items():
            v = marr[i] if marr is not None and i < len(marr) else None
            feat[mkey] = (round(float(v), 2) if v is not None and np.isfinite(v) else None)
        features.append(feat)

    if not all_v:
        return MeshLayer(name, np.zeros((0, 3), "float32"), np.zeros((0, 3), "int64"))

    return MeshLayer(
        name=name,
        vertices=np.vstack(all_v),
        faces=np.vstack(all_f),
        colors=np.vstack(all_c),
        feature_ids=np.concatenate(all_fid),
        features=features,
    )
