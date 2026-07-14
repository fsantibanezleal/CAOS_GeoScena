"""Sentinel-2 L2A multispectral fetch + spectral indices, for the fusion.

This is the analytical satellite layer: it finds the least-cloudy recent Sentinel-2 L2A scene over the AOI
(AWS Open Data via the Earth Search STAC, no auth), windowed-reads the visible + red-edge + NIR + SWIR bands,
reprojects them to a WGS84 grid over the AOI, and derives:

  * a true-colour RGB texture (B04, B03, B02) and a false-colour texture (B08, B04, B03) to drape on terrain,
  * NDVI (vegetation), NDWI (water), NDBI (built-up) index grids, each samplable per building centroid.

Bands (10 m unless noted): B02 blue, B03 green, B04 red, B05 red-edge (20 m), B08 NIR, B11 SWIR (20 m).
Everything is windowed via /vsicurl with the same GDAL tuning used across geoscena, so only the AOI is read.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds
from rasterio.transform import from_bounds as transform_from_bounds

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
# Earth Search asset keys for the bands we need.
ASSETS = {"blue": "blue", "green": "green", "red": "red", "rededge": "rededge1", "nir": "nir", "swir": "swir16"}


@dataclass
class IndexGrid:
    """A WGS84 index grid over the AOI with a nearest-cell sampler (mirrors RasterModality)."""

    key: str
    grid: np.ndarray  # float32
    west: float
    south: float
    east: float
    north: float

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        rows, cols = self.grid.shape
        lon = np.asarray(lon, dtype="float64")
        lat = np.asarray(lat, dtype="float64")
        col = ((lon - self.west) / (self.east - self.west) * cols).astype(int)
        row = ((self.north - lat) / (self.north - self.south) * rows).astype(int)
        ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.full(lon.shape, np.nan, dtype="float32")
        out[ok] = self.grid[row[ok], col[ok]]
        return out


@dataclass
class Sentinel2Result:
    rgb: np.ndarray  # (H, W, 3) uint8 true colour
    false_color: np.ndarray  # (H, W, 3) uint8 NIR-R-G (vegetation bright red)
    indices: dict[str, IndexGrid]  # ndvi, ndwi, ndbi
    west: float
    south: float
    east: float
    north: float
    scene_id: str
    date: str
    cloud: float
    provenance: LayerProvenance


def _search_scene(aoi: AOI, max_cloud: float = 12.0) -> dict:
    """Least-cloudy recent L2A scene intersecting the AOI."""
    w, s, e, n = aoi.bbox
    body = {
        "collections": [COLLECTION],
        "bbox": [w, s, e, n],
        "datetime": "2023-01-01T00:00:00Z/2025-12-31T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        "limit": 1,
    }
    req = urllib.request.Request(STAC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=60).read())
    feats = res.get("features", [])
    if not feats:
        raise FileNotFoundError(f"no Sentinel-2 L2A scene < {max_cloud}% cloud over {aoi.name}")
    return feats[0]


def _read_band(url: str, aoi: AOI, dst: np.ndarray, dst_transform, resampling=Resampling.bilinear) -> None:
    """Windowed-read one band COG and reproject into the WGS84 dst grid over the AOI."""
    w, s, e, n = aoi.bbox
    with rasterio.open(url) as src:
        wb = transform_bounds("EPSG:4326", src.crs, w, s, e, n)
        win = from_bounds(*wb, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win).astype("float32")
        src_win_transform = src.window_transform(win)
        reproject(
            source=arr,
            destination=dst,
            src_transform=src_win_transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=resampling,
        )


def _stretch(band: np.ndarray, lo_pct: float = 2.0, hi_pct: float = 98.0) -> np.ndarray:
    """Percentile stretch a reflectance band to 0..255 uint8."""
    valid = band[np.isfinite(band) & (band > 0)]
    if valid.size == 0:
        return np.zeros(band.shape, dtype="uint8")
    lo, hi = np.percentile(valid, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1.0
    out = np.clip((band - lo) / (hi - lo), 0, 1) * 255.0
    return out.astype("uint8")


def fetch_sentinel2(aoi: AOI, fetched: str, target_m: float = 10.0) -> Sentinel2Result:
    """Fetch a Sentinel-2 L2A scene over the AOI and derive textures + NDVI/NDWI/NDBI."""
    feat = _search_scene(aoi)
    assets = feat["assets"]
    w, s, e, n = aoi.bbox
    sw, sh = aoi.size_m()
    cols = max(16, int(round(sw / target_m)))
    rows = max(16, int(round(sh / target_m)))
    dst_transform = transform_from_bounds(w, s, e, n, cols, rows)

    env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        VSI_CACHE="TRUE",
        GDAL_HTTP_TIMEOUT="30",
        GDAL_HTTP_MAX_RETRY="2",
        GDAL_HTTP_RETRY_DELAY="2",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        AWS_NO_SIGN_REQUEST="YES",
    )
    bands: dict[str, np.ndarray] = {}
    with env:
        for name, key in ASSETS.items():
            if key not in assets:
                continue
            g = np.zeros((rows, cols), dtype="float32")
            _read_band(assets[key]["href"], aoi, g, dst_transform)
            bands[name] = g

    def idx(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        out = (a - b) / (a + b + 1e-6)
        out[(a + b) <= 0] = np.nan
        return out.astype("float32")

    red, green, blue, nir = bands["red"], bands["green"], bands["blue"], bands["nir"]
    swir = bands.get("swir", nir)
    ndvi = idx(nir, red)
    ndwi = idx(green, nir)
    ndbi = idx(swir, nir)

    rgb = np.dstack([_stretch(red), _stretch(green), _stretch(blue)])
    false_color = np.dstack([_stretch(nir), _stretch(red), _stretch(green)])

    prov = LayerProvenance(
        source=f"Sentinel-2 L2A ({feat['id']}, {feat['properties']['datetime'][:10]}, "
        f"{feat['properties'].get('eo:cloud_cover', 0):.0f}% cloud)",
        url="https://earth-search.aws.element84.com/v1 (collection sentinel-2-l2a, AWS sentinel-cogs)",
        license="proprietary",  # Copernicus Sentinel data: free + open, attribution "contains modified Copernicus Sentinel data"
        fetched=fetched,
        method="STAC scene pick (least cloud) + windowed /vsicurl band read + reproject to a WGS84 AOI grid; "
        "NDVI/NDWI/NDBI derived; RGB + false-colour composited",
        extra={"scene": feat["id"], "date": feat["properties"]["datetime"][:10]},
    )
    mk = lambda key, grid: IndexGrid(key, grid, w, s, e, n)  # noqa: E731
    return Sentinel2Result(
        rgb=rgb,
        false_color=false_color,
        indices={"ndvi": mk("ndvi", ndvi), "ndwi": mk("ndwi", ndwi), "ndbi": mk("ndbi", ndbi)},
        west=w, south=s, east=e, north=n,
        scene_id=feat["id"], date=feat["properties"]["datetime"][:10],
        cloud=float(feat["properties"].get("eo:cloud_cover", 0)),
        provenance=prov,
    )


# Frontend attribute metadata for the three indices (unit + label), used when adding them as modalities.
INDEX_META = {
    "ndvi": ("NDVI (vegetation)", "index"),
    "ndwi": ("NDWI (water)", "index"),
    "ndbi": ("NDBI (built-up)", "index"),
}
