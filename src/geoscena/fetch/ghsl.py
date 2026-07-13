"""Population fetcher: GHS-POP (JRC Global Human Settlement population grid).

Reads the GHS-POP 100 m residential-population grid (people per cell) as a windowed COG over HTTPS.
We use the OpenLandMap cloud-optimized mirror of the JRC R2023A product (EPSG:4326), which supports
HTTP range requests, so only the AOI window is read.

License: CC-BY 4.0 (JRC / European Commission). Attribution required; commercial use permitted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

# OpenLandMap COG mirror of GHS-POP R2023A (people per 100 m cell), WGS84, range-request friendly.
GHS_POP_COG = (
    "https://s3.openlandmap.org/arco/"
    "pop.count_ghs.jrc_m_100m_s_20210101_20211231_go_epsg.4326_v20230620.tif"
)
HUNDRED_M = 100.0 / 111_320.0  # ~100 m in degrees


@dataclass
class Population:
    """A WGS84 population grid over the AOI (people per ~100 m cell; 0 where unpopulated)."""

    counts: np.ndarray  # (rows, cols) float32
    west: float
    south: float
    east: float
    north: float
    provenance: LayerProvenance

    def total(self) -> float:
        return float(np.nansum(self.counts))

    def lonlat_grid(self) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = self.counts.shape
        dx = (self.east - self.west) / cols
        dy = (self.north - self.south) / rows
        lon = self.west + (np.arange(cols) + 0.5) * dx
        lat = self.north - (np.arange(rows) + 0.5) * dy
        return np.meshgrid(lon, lat)


def fetch_population(aoi: AOI, fetched: str) -> Population:
    """Windowed read of GHS-POP over the AOI, reprojected onto a ~100 m grid."""
    w, s, e, n = aoi.bbox
    cols = max(2, int(round((e - w) / HUNDRED_M)))
    rows = max(2, int(round((n - s) / HUNDRED_M)))
    dst = np.zeros((rows, cols), dtype="float32")
    dst_transform = from_bounds(w, s, e, n, cols, rows)

    url = f"/vsicurl/{GHS_POP_COG}"
    with rasterio.open(url) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=0.0,
        )
    dst[dst < 0] = 0.0

    prov = LayerProvenance(
        source="GHS-POP R2023A (JRC), OpenLandMap COG mirror",
        url=GHS_POP_COG,
        license="CC-BY-4.0",
        fetched=fetched,
        method="vsicurl windowed read + bilinear reproject onto ~100 m grid (people per cell)",
        extra={"grid": [rows, cols]},
    )
    return Population(dst, w, s, e, n, prov)
