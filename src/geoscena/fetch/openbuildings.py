"""Height-raster fetcher: Google Open Buildings 2.5D Temporal (Global South).

Fills rung 3 of the height-provenance ladder where Overture carries no measured height or floor
count: many Global-South cities (incl. Latin America) have sparse OSM but are covered by Google's
Open Buildings 2.5D height raster (0.5 m, effective 4 m, CC-BY-4.0 + ODbL).

Access is direct from the public GCS bucket ``open-buildings-temporal-data/v1`` (no Earth Engine):
a per-region manifest (keyed by the level-2 S2 cell token + the AOI's UTM EPSG + year) lists 12.5 km
UTM-georeferenced 3-band tiles (``building_fractional_count``, ``building_height``,
``building_presence``). We locate the tile(s) covering the AOI, windowed-read band 2 (height), and
reproject onto a WGS84 grid the ladder samples per building. Regions outside coverage have no manifest
(HTTP 404) and are skipped gracefully.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

BUCKET = "https://storage.googleapis.com/open-buildings-temporal-data"
YEAR = "2023_06_30"
HEIGHT_BAND = 2  # descriptions: (fractional_count, building_height, building_presence)
TENM = 10.0 / 111_320.0


@dataclass
class HeightRaster:
    heights: np.ndarray  # (rows, cols) float32 metres, 0 where no building
    west: float
    south: float
    east: float
    north: float
    provenance: LayerProvenance

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        rows, cols = self.heights.shape
        lon = np.asarray(lon, dtype="float64")
        lat = np.asarray(lat, dtype="float64")
        col = ((lon - self.west) / (self.east - self.west) * cols).astype(int)
        row = ((self.north - lat) / (self.north - self.south) * rows).astype(int)
        ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.full(lon.shape, np.nan, dtype="float64")
        out[ok] = self.heights[row[ok], col[ok]]
        out[out <= 0] = np.nan
        return out


def _utm_epsg(lat: float, lon: float) -> int:
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _s2_l2_token(lat: float, lon: float) -> str:
    import s2sphere

    cid = s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(lat, lon))
    return cid.parent(2).to_token()


def _load_manifest(token: str, epsg: int) -> dict | None:
    url = f"{BUCKET}/v1/manifests/{token}_EPSG_{epsg}_{YEAR}.json"
    try:
        return json.loads(urllib.request.urlopen(url, timeout=30).read())
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def fetch_height_raster(aoi: AOI, fetched: str) -> HeightRaster | None:
    """Fetch the Open Buildings 2.5D height raster over the AOI, or None if not covered."""
    lat0, lon0 = aoi.lat0, aoi.lon0
    epsg = _utm_epsg(lat0, lon0)
    token = _s2_l2_token(lat0, lon0)
    man = _load_manifest(token, epsg)
    if not man:
        return None

    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    w, s, e, n = aoi.bbox
    corners_x, corners_y = tr.transform([w, e, w, e], [s, s, n, n])
    umin_x, umax_x = min(corners_x), max(corners_x)
    umin_y, umax_y = min(corners_y), max(corners_y)
    prefix = man["uriPrefix"].replace("gs://open-buildings-temporal-data/", "")

    tiles: list[str] = []
    for tset in man["tilesets"]:
        for src in tset["sources"]:
            a = src["affineTransform"]
            d = src["dimensions"]
            x0 = a["translateX"]
            y0 = a["translateY"]
            x1 = x0 + d["width"] * a["scaleX"]
            y1 = y0 + d["height"] * a["scaleY"]
            if max(umin_x, min(x0, x1)) <= min(umax_x, max(x0, x1)) and max(
                umin_y, min(y0, y1)
            ) <= min(umax_y, max(y0, y1)):
                tiles.append(prefix + src["uris"][0])
    if not tiles:
        return None

    # target WGS84 grid over the AOI at ~10 m
    cols = max(2, int(round((e - w) / TENM)))
    rows = max(2, int(round((n - s) / TENM)))
    dst = np.zeros((rows, cols), dtype="float32")
    dst_transform = from_bounds(w, s, e, n, cols, rows)
    filled = False
    # GDAL tuning for the /vsicurl reads (mirrors rastermod.py): without GDAL_DISABLE_READDIR_ON_OPEN,
    # opening a COG on GCS triggers a bucket directory listing (thousands of range requests) that can turn
    # a windowed read into a multi-minute stall. A real HTTP timeout + retries keep one slow tile from
    # hanging the whole bake; the ladder height fallback covers a tile that genuinely fails.
    env = rasterio.Env(
        GDAL_HTTP_TIMEOUT="30",
        GDAL_HTTP_MAX_RETRY="2",
        GDAL_HTTP_RETRY_DELAY="2",
        VSI_CACHE="TRUE",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".vrt,.tif,.tiff",
    )
    with env:
        for tile in tiles:
            url = f"/vsicurl/{BUCKET}/{tile}"
            try:
                with rasterio.open(url) as srcds:
                    tmp = np.zeros((rows, cols), dtype="float32")
                    reproject(
                        source=rasterio.band(srcds, HEIGHT_BAND),
                        destination=tmp,
                        src_transform=srcds.transform,
                        src_crs=srcds.crs,
                        dst_transform=dst_transform,
                        dst_crs="EPSG:4326",
                        resampling=Resampling.bilinear,
                    )
                    m = tmp > 0
                    dst[m] = tmp[m]
                    filled = filled or bool(m.any())
            except rasterio.errors.RasterioIOError:
                continue
    if not filled:
        return None

    prov = LayerProvenance(
        source="Google Open Buildings 2.5D Temporal (height)",
        url=f"{BUCKET}/v1/geotiffs/ (S2 {token}, EPSG {epsg}, {YEAR})",
        license="CC-BY-4.0",
        fetched=fetched,
        method="GCS manifest tile lookup + vsicurl band-2 read + reproject to ~10 m WGS84",
        extra={"tiles": tiles, "epsg": epsg},
    )
    return HeightRaster(dst, w, s, e, n, prov)
