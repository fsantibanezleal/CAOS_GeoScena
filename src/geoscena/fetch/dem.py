"""Terrain fetcher: Copernicus GLO-30 global DSM (AWS Open Data, keyless).

Reads the Copernicus GLO-30 Digital Surface Model directly from the public S3 bucket
``copernicus-dem-30m`` over HTTPS (GDAL ``/vsicurl``), windowed and reprojected onto a
target ~1 arc-second grid covering the AOI bounding box. Tiles are named by their SW
integer-degree corner: ``Copernicus_DSM_COG_10_{N|S}LL_00_{E|W}LLL_00_DEM``.

License: Copernicus DEM free-of-charge license (attribution required); commercial use
permitted. GLO-30 is a DSM (includes buildings and canopy) which is why dense-core
terrain sits slightly high; documented as a product caveat.
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

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
ARCSEC = 1.0 / 3600.0  # ~30 m at the equator


@dataclass
class DemGrid:
    """A regular WGS84 elevation grid covering the AOI (metres above ellipsoid)."""

    z: np.ndarray  # (rows, cols) float32, NaN where no data
    west: float
    south: float
    east: float
    north: float
    provenance: LayerProvenance

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Nearest-pixel elevation (metres) at each lon/lat; NaN outside coverage."""
        rows, cols = self.z.shape
        lon = np.asarray(lon, dtype="float64")
        lat = np.asarray(lat, dtype="float64")
        col = ((lon - self.west) / (self.east - self.west) * cols).astype(int)
        row = ((self.north - lat) / (self.north - self.south) * rows).astype(int)
        ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.full(lon.shape, np.nan, dtype="float64")
        out[ok] = self.z[row[ok], col[ok]]
        return out

    def lonlat_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Pixel-centre lon/lat coordinate grids matching ``z``."""
        rows, cols = self.z.shape
        dx = (self.east - self.west) / cols
        dy = (self.north - self.south) / rows
        lon = self.west + (np.arange(cols) + 0.5) * dx
        lat = self.north - (np.arange(rows) + 0.5) * dy
        return np.meshgrid(lon, lat)


def _tile_name(lat_sw: int, lon_sw: int) -> str:
    ns = "N" if lat_sw >= 0 else "S"
    ew = "E" if lon_sw >= 0 else "W"
    return (
        f"Copernicus_DSM_COG_10_{ns}{abs(lat_sw):02d}_00_"
        f"{ew}{abs(lon_sw):03d}_00_DEM"
    )


def _tiles_for_bbox(west: float, south: float, east: float, north: float) -> list[str]:
    tiles = []
    for lat_sw in range(math.floor(south), math.ceil(north)):
        for lon_sw in range(math.floor(west), math.ceil(east)):
            tiles.append(_tile_name(lat_sw, lon_sw))
    return tiles


def fetch_dem(aoi: AOI, fetched: str, pad_frac: float = 0.05) -> DemGrid:
    """Fetch and mosaic GLO-30 over the AOI (with a small pad for edge triangles)."""
    w, s, e, n = aoi.bbox
    pw = (e - w) * pad_frac
    ph = (n - s) * pad_frac
    w, s, e, n = w - pw, s - ph, e + pw, n + ph

    cols = max(2, int(round((e - w) / ARCSEC)))
    rows = max(2, int(round((n - s) / ARCSEC)))
    dst = np.full((rows, cols), np.nan, dtype="float32")
    dst_transform = from_bounds(w, s, e, n, cols, rows)

    filled = False
    for tile in _tiles_for_bbox(w, s, e, n):
        url = f"/vsicurl/{BUCKET}/{tile}/{tile}.tif"
        try:
            with rasterio.open(url) as src:
                tmp = np.full((rows, cols), np.nan, dtype="float32")
                reproject(
                    source=rasterio.band(src, 1),
                    destination=tmp,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs="EPSG:4326",
                    resampling=Resampling.bilinear,
                    dst_nodata=np.nan,
                )
                mask = ~np.isnan(tmp)
                dst[mask] = tmp[mask]
                filled = filled or bool(mask.any())
        except rasterio.errors.RasterioIOError:
            # Tile absent (ocean) or transient network error: skip; other tiles fill in.
            continue

    if not filled:
        raise RuntimeError(f"no Copernicus GLO-30 tiles returned data for AOI {aoi.name!r}")

    prov = LayerProvenance(
        source="Copernicus GLO-30 DSM",
        url=f"{BUCKET}/ (AWS Open Data)",
        license="Copernicus-free",
        fetched=fetched,
        method="vsicurl windowed read + bilinear reproject onto ~1 arcsec grid",
        extra={"tiles": _tiles_for_bbox(w, s, e, n), "grid": [rows, cols]},
    )
    return DemGrid(dst, w, s, e, n, prov)
