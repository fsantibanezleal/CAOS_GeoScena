"""Administrative sub-area boundaries (comunas / districts / states) for the AOI, via OSMnx (Overpass).

These are the official sub-areas you aggregate by: for a city AOI the finest level with >=2 distinct units
(municipality / comuna = admin_level 8, or borough / suburb = 9/10) is picked so the scene has real
sub-areas rather than one enclosing unit. Each unit's boundary is returned in the SAME local world frame as
the meshes (x = east metres, z = -north metres, from the AOI origin), so the frontend can point-in-polygon
building centroids against it directly and aggregate any attribute per unit (a choropleth + per-unit stats).

License: ODbL (OpenStreetMap). Optional dependency (OSMnx).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

# admin_level candidates from finest (most sub-areas) to coarsest; we pick the finest with >=2 units.
LEVELS = ["10", "9", "8", "7", "6", "5", "4"]


@dataclass
class AdminUnit:
    name: str
    admin_level: str
    # exterior rings in local world coords (x=east m, z=-north m), one list per polygon part.
    rings: list[list[tuple[float, float]]]


@dataclass
class AdminAreas:
    units: list[AdminUnit]
    level: str
    provenance: LayerProvenance
    extra: dict = field(default_factory=dict)


def _osmnx():
    import osmnx as ox

    ox.settings.requests_timeout = 40
    ox.settings.timeout = 40
    ox.settings.overpass_rate_limit = False
    return ox


def _to_world_rings(geom, aoi: AOI) -> list[list[tuple[float, float]]]:
    """Polygon/MultiPolygon exterior rings -> local world (x=east, z=-north) metre coords."""
    rings: list[list[tuple[float, float]]] = []
    polys = getattr(geom, "geoms", [geom])
    for p in polys:
        if not hasattr(p, "exterior") or p.exterior is None:
            continue
        lon, lat = np.asarray(p.exterior.coords.xy[0]), np.asarray(p.exterior.coords.xy[1])
        east, north = aoi.to_local(lon, lat)
        rings.append([(float(x), float(-z)) for x, z in zip(east, north)])
    return rings


def fetch_admin(aoi: AOI, fetched: str) -> AdminAreas:
    """Fetch admin sub-area boundaries for the AOI, finest level with >=2 units, in local world coords."""
    ox = _osmnx()
    w, s, e, n = aoi.bbox
    gdf = ox.features_from_bbox((w, s, e, n), {"boundary": "administrative"})
    gdf = gdf[gdf.geometry.notna()]
    if "admin_level" not in gdf.columns or gdf.empty:
        raise FileNotFoundError("no admin boundaries in AOI")
    # keep polygonal boundaries with a name + level
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if "name" in gdf.columns:
        gdf = gdf[gdf["name"].notna()]
    chosen = None
    for lvl in LEVELS:
        sub = gdf[gdf["admin_level"].astype(str) == lvl]
        names = sub["name"].astype(str).unique() if "name" in sub.columns else []
        if len(names) >= 2:
            chosen = (lvl, sub)
            break
    if chosen is None:
        raise FileNotFoundError("no admin level with >=2 sub-areas in AOI")
    lvl, sub = chosen
    units: list[AdminUnit] = []
    seen: set[str] = set()
    for _, row in sub.iterrows():
        name = str(row.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        rings = _to_world_rings(row.geometry, aoi)
        if rings:
            units.append(AdminUnit(name=name, admin_level=lvl, rings=rings))
    prov = LayerProvenance(
        source="OpenStreetMap administrative boundaries",
        url="https://www.openstreetmap.org/ (Overpass via OSMnx)",
        license="ODbL-1.0",
        fetched=fetched,
        method=f"OSMnx features_from_bbox boundary=administrative, finest level with >=2 units (admin_level {lvl})",
        extra={"admin_level": lvl, "n_units": len(units)},
    )
    return AdminAreas(units=units, level=lvl, provenance=prov, extra={"n_units": len(units)})
