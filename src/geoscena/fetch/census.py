"""Census fetch: INE Chile Censo 2017 manzana (block) socio-economics, as per-building modalities.

Unlike the global raster modalities (rastermod), this is an AUTHORITATIVE national vector source: the
Instituto Nacional de Estadisticas (INE) publishes Censo 2017 aggregated to the manzana (city block) on
its official ArcGIS Hub feature service, carrying, per block, the resident population (TOTAL_PERSONAS),
the dwelling count (TOTAL_VIVIENDAS) and dwelling materiality (acceptable / recoverable / irrecoverable).
We query the AOI window and rasterise three block-level signals onto the AOI grid so they fuse exactly like
any other topic modality -- sampled at each building centroid into the feature table, aggregated per hex /
comuna downstream:

  * pop_density       people / km2      (the authoritative population denominator)
  * dwelling_density  dwellings / km2
  * housing_precarity % of dwellings of recoverable+irrecoverable materiality (a deprivation signal)

Densities use each block's area in the AOI-local equal-distance frame. This is the correct population source
for Chilean AOIs; the GHS-POP global grid mirror has un-documented units and mis-scales badly, so it is only
meshed as a relative layer, never used as an absolute metric.

Only meaningful inside Chile; elsewhere the service returns no features and the caller records the gap and
skips the layer (terrain-first policy), so this never sinks a non-Chilean build.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import numpy as np
import rasterio.features
from rasterio.transform import from_bounds

from geoscena.aoi import AOI
from geoscena.fetch.rastermod import RasterModality, ModalitySpec
from geoscena.provenance import LayerProvenance

# INE Chile "Microdatos Censo 2017: Manzana" official ArcGIS Hub feature service (layer 0), owner gisine1.
INE_MANZANA_URL = (
    "https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/"
    "Manzana_2017_2/FeatureServer/0/query"
)
_PAGE = 2000  # service maxRecordCount
_GRID_CELLS = 384  # rasterisation grid (matches rastermod._MAX_CELLS; ~28 m over an 11 km AOI)
_FIELDS = "TOTAL_PERSONAS,TOTAL_VIVIENDAS,VIV_MATERIAL_ACEPTABLE,VIV_MATERIAL_RECUPERABLE,VIV_MATERIAL_IRRECUPERABLE"

_SOURCE = "INE Chile - Censo 2017, manzana (block) level"


def _spec(key: str, label: str, unit: str, method: str) -> ModalitySpec:
    return ModalitySpec(
        key=key,
        label=label,
        unit=unit,
        source=_SOURCE,
        url=INE_MANZANA_URL,
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        method=method,
    )


# Public specs (also used by tests / registries).
POP_DENSITY_SPEC = _spec(
    "pop_density", "Population density (Censo 2017)", "people/km2",
    "INE Censo 2017 manzana TOTAL_PERSONAS / block area, rasterised to the AOI grid, sampled per building centroid",
)
DWELLING_DENSITY_SPEC = _spec(
    "dwelling_density", "Dwelling density (Censo 2017)", "dwellings/km2",
    "INE Censo 2017 manzana TOTAL_VIVIENDAS / block area, rasterised to the AOI grid, sampled per building centroid",
)
HOUSING_PRECARITY_SPEC = _spec(
    "housing_precarity", "Housing precarity (Censo 2017)", "%",
    "INE Censo 2017 manzana share of dwellings of recoverable+irrecoverable materiality, sampled per building centroid",
)
CENSUS_SPECS = [POP_DENSITY_SPEC, DWELLING_DENSITY_SPEC, HOUSING_PRECARITY_SPEC]


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _query_page(aoi: AOI, offset: int, timeout: float) -> list[dict]:
    w, s, e, n = aoi.bbox
    env = {"xmin": w, "ymin": s, "xmax": e, "ymax": n, "spatialReference": {"wkid": 4326}}
    params = {
        "where": "1=1",
        "geometry": json.dumps(env),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _FIELDS,
        "returnGeometry": "true",
        "resultOffset": str(offset),
        "resultRecordCount": str(_PAGE),
        "f": "geojson",
    }
    url = INE_MANZANA_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geoscena/maqueta (+census fetch)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("features", [])


def fetch_census(aoi: AOI, fetched: str, *, timeout: float = 60.0) -> list[RasterModality]:
    """Fetch INE Censo 2017 manzana data over the AOI and return per-building density/index modalities.

    Raises on access failure or when no census blocks intersect the AOI (non-Chile), so the caller can
    record the gap and skip the layer.
    """
    import geopandas as gpd
    from shapely.geometry import shape

    feats: list[dict] = []
    offset = 0
    while True:
        batch = _query_page(aoi, offset, timeout)
        feats.extend(batch)
        if len(batch) < _PAGE:
            break
        offset += _PAGE
    feats = [f for f in feats if f.get("geometry")]
    if not feats:
        raise ValueError("no INE census manzanas intersect the AOI (outside Chile?)")

    props = [f["properties"] for f in feats]
    gdf = gpd.GeoDataFrame(
        {
            "pers": [_num(p.get("TOTAL_PERSONAS")) for p in props],
            "viv": [_num(p.get("TOTAL_VIVIENDAS")) for p in props],
            "acc": [_num(p.get("VIV_MATERIAL_ACEPTABLE")) for p in props],
            "rec": [_num(p.get("VIV_MATERIAL_RECUPERABLE")) for p in props],
            "irr": [_num(p.get("VIV_MATERIAL_IRRECUPERABLE")) for p in props],
        },
        geometry=[shape(f["geometry"]) for f in feats],
        crs="EPSG:4326",
    )
    gdf["area_km2"] = gdf.to_crs(aoi.crs_local).area / 1e6
    gdf = gdf[(gdf["area_km2"] > 0) & gdf.geometry.notna()].copy()

    gdf["pop_density"] = gdf["pers"] / gdf["area_km2"]
    gdf["dwelling_density"] = gdf["viv"] / gdf["area_km2"]
    mat_total = gdf["acc"] + gdf["rec"] + gdf["irr"]
    gdf["housing_precarity"] = np.where(mat_total > 0, (gdf["rec"] + gdf["irr"]) / mat_total * 100.0, np.nan)

    # AOI WGS84 rasterisation grid (blocks don't overlap; all_touched fills edge/street gaps).
    w, s, e, n = aoi.bbox
    aspect = (e - w) / max(n - s, 1e-9)
    if aspect >= 1:
        width, height = _GRID_CELLS, max(1, int(round(_GRID_CELLS / aspect)))
    else:
        height, width = _GRID_CELLS, max(1, int(round(_GRID_CELLS * aspect)))
    transform = from_bounds(w, s, e, n, width, height)

    total_pop = int(gdf["pers"].sum())
    out: list[RasterModality] = []
    for spec in CENSUS_SPECS:
        col = gdf[spec.key]
        valid = gdf[np.isfinite(col)]
        shapes = ((geom, float(v)) for geom, v in zip(valid.geometry, valid[spec.key]))
        grid = rasterio.features.rasterize(
            shapes, out_shape=(height, width), transform=transform, fill=np.nan, dtype="float32", all_touched=True
        )
        prov = LayerProvenance(
            source=spec.source, url=spec.url, license=spec.license, fetched=fetched, method=spec.method,
            extra={"modality": spec.key, "unit": spec.unit, "manzanas": int(len(gdf)), "total_pop": total_pop},
        )
        out.append(RasterModality(spec.key, grid, w, s, e, n, prov, spec))
    return out
