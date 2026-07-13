"""Vector fetcher: Overture Maps buildings + roads via the official ``overturemaps`` CLI.

Overture is the primary footprint source: it conflates OpenStreetMap (highest priority),
Esri, national mapping agencies and Google/Microsoft ML roofprints into one schema with
``height`` / ``num_floors`` where any source carries them. We extract the AOI's rows with the
reference ``overturemaps`` extractor (PyArrow, bbox-scoped GeoParquet), which reads only the
AOI's data from the public S3 bucket and writes a local GeoParquet that GeoPandas loads
directly. (We use the CLI rather than DuckDB because DuckDB's native extensions crash the GIL
on this platform.)

License: ODbL (attribution + share-alike on derived databases).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import geopandas as gpd

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

# Overture release. Bump to the latest release folder as they publish (monthly).
DEFAULT_RELEASE = "2026-06-17.0"


def _download(aoi: AOI, otype: str, release: str) -> gpd.GeoDataFrame:
    """Run the overturemaps extractor for one type over the AOI bbox; read the GeoParquet."""
    w, s, e, n = aoi.bbox
    tmp = Path(tempfile.gettempdir()) / f"geoscena_ov_{otype}_{abs(hash((w, s, e, n)))}.parquet"
    if tmp.exists():
        tmp.unlink()
    cmd = [
        sys.executable,
        "-m",
        "overturemaps",
        "download",
        f"--bbox={w},{s},{e},{n}",
        "-f",
        "geoparquet",
        f"--type={otype}",
        "-o",
        str(tmp),
    ]
    env = {"OVERTURE_RELEASE": release}
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**_os_environ(), **env})
    if proc.returncode != 0 or not tmp.exists():
        raise RuntimeError(
            f"overturemaps download ({otype}) failed: {proc.stderr.strip()[:400]}"
        )
    gdf = gpd.read_parquet(tmp)
    try:
        tmp.unlink()
        Path(str(tmp) + ".state").unlink(missing_ok=True)
    except OSError:
        pass
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    else:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def _os_environ() -> dict:
    import os

    return dict(os.environ)


def fetch_buildings(aoi: AOI, fetched: str, release: str = DEFAULT_RELEASE) -> gpd.GeoDataFrame:
    """Fetch Overture building footprints intersecting the AOI (WGS84).

    Keeps geometry + ``height`` / ``num_floors`` (the ladder's top rungs) and a provenance on
    ``.attrs``.
    """
    gdf = _download(aoi, "building", release)
    keep = [c for c in ("height", "num_floors", "geometry") if c in gdf.columns]
    gdf = gdf[keep].copy()
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.intersects(aoi_polygon(aoi))].reset_index(drop=True)
    gdf.attrs["provenance"] = LayerProvenance(
        source="Overture Maps buildings",
        url=f"s3://overturemaps-us-west-2/release/{release}/theme=buildings/type=building",
        license="ODbL-1.0",
        fetched=fetched,
        method="overturemaps CLI bbox extract of GeoParquet on S3",
        extra={"release": release, "n_buildings": int(len(gdf))},
    )
    return gdf


def fetch_roads(aoi: AOI, fetched: str, release: str = DEFAULT_RELEASE) -> gpd.GeoDataFrame:
    """Fetch Overture transportation segments (roads/rail) intersecting the AOI (WGS84)."""
    gdf = _download(aoi, "segment", release)
    keep = [c for c in ("class", "subtype", "geometry") if c in gdf.columns]
    gdf = gdf[keep].copy()
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.intersects(aoi_polygon(aoi))].reset_index(drop=True)
    gdf.attrs["provenance"] = LayerProvenance(
        source="Overture Maps transportation",
        url=f"s3://overturemaps-us-west-2/release/{release}/theme=transportation/type=segment",
        license="ODbL-1.0",
        fetched=fetched,
        method="overturemaps CLI bbox extract of GeoParquet on S3",
        extra={"release": release, "n_segments": int(len(gdf))},
    )
    return gdf


def aoi_polygon(aoi: AOI):
    from shapely.geometry import box

    return box(*aoi.bbox)
