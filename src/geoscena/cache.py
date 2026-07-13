"""On-disk cache for fetched raw data.

Downloads are expensive and the sources are large, so every fetcher caches its raw
result under a cache root (default ``$GEOSCENA_CACHE`` or ``./.geoscena-cache``). The
cache key is derived from the AOI bbox + a source tag so re-running a build reuses bytes
rather than re-hitting S3/Overpass. Heavy raw data never enters git; it lives here.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from geoscena.aoi import AOI


def cache_root() -> Path:
    root = os.environ.get("GEOSCENA_CACHE", ".geoscena-cache")
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def aoi_key(aoi: AOI, source: str, ext: str) -> Path:
    """A stable cache path for ``source`` data covering ``aoi``."""
    tag = f"{aoi.west:.6f},{aoi.south:.6f},{aoi.east:.6f},{aoi.north:.6f}"
    h = hashlib.sha1(f"{source}|{tag}".encode()).hexdigest()[:16]
    safe = "".join(c if c.isalnum() else "_" for c in aoi.name)[:40]
    return cache_root() / f"{safe}_{source}_{h}.{ext}"
