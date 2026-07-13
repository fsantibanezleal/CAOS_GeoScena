"""Context-layer fetcher: OpenStreetMap water / green / rail via OSMnx (Overpass).

Overture covers buildings and roads; for the softer context layers (water bodies, green
areas, rail) OpenStreetMap through OSMnx is the most convenient AOI-scoped source. Small
areas are exactly OSMnx's sweet spot (flexible geometry queries over the Overpass API).

License: ODbL. Optional dependency (``pip install 'geoscena[osm]'``).
"""

from __future__ import annotations

import geopandas as gpd

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

# OSM tag selectors per context layer.
TAGS = {
    "water": {"natural": ["water"], "water": True, "waterway": ["riverbank", "dock"]},
    "green": {"leisure": ["park", "garden", "pitch"], "landuse": ["grass", "forest", "meadow"], "natural": ["wood", "scrub"]},
    "rail": {"railway": ["rail", "light_rail", "subway", "tram"]},
}


def _osmnx():
    try:
        import osmnx as ox
    except ImportError as exc:  # pragma: no cover - guarded by the 'osm' extra
        raise ImportError(
            "OSM context fetch needs OSMnx. Install:  pip install 'geoscena[osm]'"
        ) from exc
    return ox


def fetch_context(aoi: AOI, layer: str, fetched: str) -> gpd.GeoDataFrame:
    """Fetch one OSM context layer ('water'|'green'|'rail') for the AOI (WGS84)."""
    if layer not in TAGS:
        raise ValueError(f"unknown context layer {layer!r}; expected one of {list(TAGS)}")
    ox = _osmnx()
    w, s, e, n = aoi.bbox
    try:
        gdf = ox.features_from_bbox((w, s, e, n), TAGS[layer])
    except Exception:
        # Overpass returns nothing for empty selectors; hand back an empty layer.
        gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)
    gdf.attrs["provenance"] = LayerProvenance(
        source=f"OpenStreetMap ({layer})",
        url="https://www.openstreetmap.org/ (Overpass via OSMnx)",
        license="ODbL-1.0",
        fetched=fetched,
        method=f"OSMnx features_from_bbox with tags {TAGS[layer]}",
        extra={"n_features": int(len(gdf))},
    )
    return gdf
