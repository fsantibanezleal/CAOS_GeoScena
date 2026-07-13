"""Land-cover fetcher: ESA WorldCover 10 m (AWS Open Data, keyless).

Reads the ESA WorldCover v200 (2021) 11-class land-cover map from the public S3 bucket
``esa-worldcover`` over HTTPS. Tiles are 3x3 degrees, named by their SW corner on a
multiple-of-3 grid: ``v200/2021/map/ESA_WorldCover_10m_2021_v200_{N|S}LL{E|W}LLL_Map.tif``.
The class raster is sampled per building/terrain point to tint the scene by land use.

License: CC-BY 4.0, free of charge without restriction of use.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

BUCKET = "https://esa-worldcover.s3.amazonaws.com"
TENM = 10.0 / 111_320.0  # ~10 m in degrees

# WorldCover class codes -> (label, RGB) per the official legend.
CLASSES: dict[int, tuple[str, tuple[int, int, int]]] = {
    10: ("Tree cover", (0, 100, 0)),
    20: ("Shrubland", (255, 187, 34)),
    30: ("Grassland", (255, 255, 76)),
    40: ("Cropland", (240, 150, 255)),
    50: ("Built-up", (250, 0, 0)),
    60: ("Bare / sparse", (180, 180, 180)),
    70: ("Snow and ice", (240, 240, 240)),
    80: ("Permanent water", (0, 100, 200)),
    90: ("Herbaceous wetland", (0, 150, 160)),
    95: ("Mangroves", (0, 207, 117)),
    100: ("Moss and lichen", (250, 230, 160)),
}


@dataclass
class LandCover:
    """A WGS84 land-cover class grid covering the AOI (uint8 class codes; 0 = nodata)."""

    classes: np.ndarray
    west: float
    south: float
    east: float
    north: float
    provenance: LayerProvenance

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Nearest-pixel class code for each lon/lat (0 where outside)."""
        rows, cols = self.classes.shape
        col = ((np.asarray(lon) - self.west) / (self.east - self.west) * cols).astype(int)
        row = ((self.north - np.asarray(lat)) / (self.north - self.south) * rows).astype(int)
        ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.zeros(np.asarray(lon).shape, dtype="uint8")
        out[ok] = self.classes[row[ok], col[ok]]
        return out


def _tile_name(lat_sw: int, lon_sw: int) -> str:
    ns = "N" if lat_sw >= 0 else "S"
    ew = "E" if lon_sw >= 0 else "W"
    return f"ESA_WorldCover_10m_2021_v200_{ns}{abs(lat_sw):02d}{ew}{abs(lon_sw):03d}_Map"


def _tiles_for_bbox(w, s, e, n) -> list[str]:
    out = []
    for lat_sw in range(int(math.floor(s / 3) * 3), int(math.ceil(n / 3) * 3), 3):
        for lon_sw in range(int(math.floor(w / 3) * 3), int(math.ceil(e / 3) * 3), 3):
            out.append(_tile_name(lat_sw, lon_sw))
    return out


def fetch_landcover(aoi: AOI, fetched: str) -> LandCover:
    """Fetch and mosaic ESA WorldCover over the AOI."""
    w, s, e, n = aoi.bbox
    cols = max(2, int(round((e - w) / TENM)))
    rows = max(2, int(round((n - s) / TENM)))
    dst = np.zeros((rows, cols), dtype="uint8")
    dst_transform = from_bounds(w, s, e, n, cols, rows)

    filled = False
    for tile in _tiles_for_bbox(w, s, e, n):
        url = f"/vsicurl/{BUCKET}/v200/2021/map/{tile}.tif"
        try:
            with rasterio.open(url) as src:
                tmp = np.zeros((rows, cols), dtype="uint8")
                reproject(
                    source=rasterio.band(src, 1),
                    destination=tmp,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs="EPSG:4326",
                    resampling=Resampling.nearest,
                )
                mask = tmp > 0
                dst[mask] = tmp[mask]
                filled = filled or bool(mask.any())
        except rasterio.errors.RasterioIOError:
            continue

    if not filled:
        raise RuntimeError(f"no ESA WorldCover tiles returned data for AOI {aoi.name!r}")

    prov = LayerProvenance(
        source="ESA WorldCover 10 m v200 (2021)",
        url=f"{BUCKET}/v200/2021/map/ (AWS Open Data)",
        license="CC-BY-4.0",
        fetched=fetched,
        method="vsicurl nearest-neighbour reproject onto ~10 m grid; 11-class legend",
        extra={"tiles": _tiles_for_bbox(w, s, e, n), "grid": [rows, cols]},
    )
    return LandCover(dst, w, s, e, n, prov)
