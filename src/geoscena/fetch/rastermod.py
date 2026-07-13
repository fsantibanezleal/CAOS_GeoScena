"""Generic windowed-raster topic-modality fetcher.

Beyond the core scene layers (terrain, buildings, roads, land cover, ...), Maqueta fuses TOPIC
modalities the user reasons about: solar potential, wind, land function, seasonal temperature, soil,
seismic hazard. They all share one access shape: a georeferenced raster (a remote Cloud-Optimized
GeoTIFF read over ``/vsicurl``, or a local cached GeoTIFF), from which we read ONLY the AOI window and
resample it onto a WGS84 grid. Each becomes a per-building attribute (sampled at the footprint centroid,
the fusion join) and can also drive a tinted ground overlay.

This module provides one fetcher, :func:`fetch_raster_modality`, plus a registry of verified,
permissively licensed sources (:data:`MODALITIES`). A source is a :class:`ModalitySpec`; adding a new
topic layer is one entry, no new code. Sources with a non-WGS84 CRS (e.g. SoilGrids' Interrupted Goode
Homolosine) are handled transparently by a :class:`~rasterio.vrt.WarpedVRT`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

# Cap the AOI window grid so a modality read stays cheap regardless of native resolution.
_MAX_CELLS = 384


@dataclass(frozen=True)
class ModalitySpec:
    """A verified public raster modality that can be fused as a per-building/per-cell attribute."""

    key: str  # the per-building feature field + frontend attribute key (e.g. "solar_ghi")
    label: str
    unit: str
    source: str  # human-readable dataset name
    url: str  # a /vsicurl COG/VRT URL, or a local path template ("{cache}/...") for a cached download
    band: int = 1
    scale: float = 1.0  # value = raw * scale + offset
    offset: float = 0.0
    src_nodata: float | None = None
    resampling: Resampling = Resampling.bilinear
    license: str = "CC-BY-4.0"
    license_url: str = ""
    commercial_ok: bool = True
    method: str = "windowed raster read, resampled to a WGS84 AOI grid, sampled per building centroid"
    extra: dict = field(default_factory=dict)


@dataclass
class RasterModality:
    """A WGS84 value grid for one modality over the AOI, with a per-point sampler."""

    key: str
    grid: np.ndarray  # float32, np.nan where nodata
    west: float
    south: float
    east: float
    north: float
    provenance: LayerProvenance
    spec: ModalitySpec

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Nearest-cell value for each lon/lat (np.nan where outside the grid or nodata)."""
        rows, cols = self.grid.shape
        lon = np.asarray(lon, dtype="float64")
        lat = np.asarray(lat, dtype="float64")
        col = ((lon - self.west) / (self.east - self.west) * cols).astype(int)
        row = ((self.north - lat) / (self.north - self.south) * rows).astype(int)
        ok = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.full(lon.shape, np.nan, dtype="float32")
        out[ok] = self.grid[row[ok], col[ok]]
        return out


def _resolve_url(url: str, cache_dir: str | Path | None) -> str:
    if "{cache}" in url:
        if cache_dir is None:
            raise FileNotFoundError(f"modality needs a local cache but none given: {url}")
        return url.replace("{cache}", str(Path(cache_dir)))
    return url


def fetch_raster_modality(
    aoi: AOI,
    spec: ModalitySpec,
    *,
    fetched: str,
    cache_dir: str | Path | None = None,
    max_cells: int = _MAX_CELLS,
) -> RasterModality:
    """Read the AOI window of a modality raster and return a WGS84 value grid + sampler.

    Raises on access failure so the caller can record the gap and skip the layer (terrain-first policy).
    """
    w, s, e, n = aoi.bbox()
    aspect = (e - w) / max(n - s, 1e-9)
    if aspect >= 1:
        width = max_cells
        height = max(1, int(round(max_cells / aspect)))
    else:
        height = max_cells
        width = max(1, int(round(max_cells * aspect)))

    src_url = _resolve_url(spec.url, cache_dir)
    with rasterio.open(src_url) as ds:
        with WarpedVRT(ds, crs="EPSG:4326", resampling=spec.resampling) as vrt:
            win = from_bounds(w, s, e, n, transform=vrt.transform)
            raw = vrt.read(
                spec.band,
                window=win,
                out_shape=(height, width),
                resampling=spec.resampling,
                boundless=True,
                fill_value=(spec.src_nodata if spec.src_nodata is not None else 0),
            ).astype("float32")
            src_nodata = spec.src_nodata if spec.src_nodata is not None else ds.nodata

    grid = raw * spec.scale + spec.offset
    if src_nodata is not None:
        grid = np.where(raw == src_nodata, np.nan, grid)
    # SoilGrids and friends use a large sentinel for nodata; also drop non-finite.
    grid = np.where(np.isfinite(grid), grid, np.nan).astype("float32")

    prov = LayerProvenance(
        source=spec.source,
        url=spec.url,
        license=spec.license,
        license_name=spec.license,
        license_url=spec.license_url,
        commercial_ok=spec.commercial_ok,
        fetched=fetched,
        method=spec.method,
        extra={"modality": spec.key, "unit": spec.unit, **spec.extra},
    )
    return RasterModality(spec.key, grid, w, s, e, n, prov, spec)


# --- Verified, permissively licensed topic modalities (see wip/maqueta/research-modalities-2026-07-13.md) ---
# SoilGrids is a remote COG/VRT (no download). Download-based sources use a "{cache}" local path filled by
# the pipeline after it fetches the file (kept out of this module so a flaky host never blocks a fetcher).
MODALITIES: dict[str, ModalitySpec] = {
    # Soil organic carbon, 0-5 cm mean. ISRIC SoilGrids, Homolosine CRS, dg/kg -> g/kg via scale.
    "soil_soc": ModalitySpec(
        key="soil_soc",
        label="Soil organic carbon (0-5 cm)",
        unit="g/kg",
        source="ISRIC SoilGrids 2.0",
        url="/vsicurl/https://files.isric.org/soilgrids/latest/data/soc/soc_0-5cm_mean.vrt",
        scale=0.1,
        src_nodata=-32768,
        license="CC-BY-4.0",
        license_url="https://www.isric.org/about/data-policy",
    ),
    # Global Horizontal Irradiation, long-term average daily total. Global Solar Atlas (World Bank), 1 km,
    # EPSG:4326. Downloaded once to the cache (the api.globalsolaratlas.info ZIP), extracted to GHI.tif.
    "solar_ghi": ModalitySpec(
        key="solar_ghi",
        label="Solar irradiation (GHI)",
        unit="kWh/m2/day",
        source="Global Solar Atlas 2.0 (World Bank / Solargis)",
        url="{cache}/solar/GHI.tif",
        license="CC-BY-4.0",
        license_url="https://globalsolaratlas.info/about",
        method="windowed read of the Global Solar Atlas GHI GeoTIFF, sampled per building centroid",
    ),
}
