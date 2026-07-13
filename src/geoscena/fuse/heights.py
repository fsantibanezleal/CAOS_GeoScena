"""The height-provenance ladder: assign a height to every building, honestly.

Buildings rarely all carry a measured height. This ladder resolves a height for each
footprint from the best source available, and records WHICH source was used per building
so the product can report the provenance mix instead of hiding inference behind a single
number. The ladder, best first:

  1. ``measured``   -- an explicit ``height`` attribute from Overture/OSM.
  2. ``floors``     -- ``num_floors`` x a per-region floor height (default 3.2 m).
  3. ``raster``     -- a sampled height raster (e.g. Google Open Buildings 2.5D), if given.
  4. ``prior``      -- a land-use / default fallback height.

Every returned building gets ``height_m`` and ``height_source`` (one of the tags above).
The per-source counts are returned as ``mix`` for the Benchmark surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FLOOR_HEIGHT_M = 3.2
PRIOR_HEIGHT_M = 8.0
MIN_HEIGHT_M = 2.5


@dataclass
class HeightResult:
    heights: np.ndarray  # (N,) float metres
    source: np.ndarray  # (N,) object, one of measured|floors|raster|prior
    mix: dict[str, int]


def assign_heights(
    buildings: pd.DataFrame,
    raster_heights: np.ndarray | None = None,
    floor_height_m: float = FLOOR_HEIGHT_M,
    prior_m: float = PRIOR_HEIGHT_M,
) -> HeightResult:
    """Resolve a height + a provenance tag for each building via the ladder.

    Args:
        buildings: frame with optional ``height`` and ``num_floors`` columns.
        raster_heights: optional (N,) array of raster-sampled heights aligned to rows
            (NaN where the raster has no coverage), e.g. Open Buildings 2.5D.
    """
    n = len(buildings)
    heights = np.full(n, np.nan, dtype="float64")
    source = np.array(["prior"] * n, dtype=object)

    h = pd.to_numeric(buildings.get("height", pd.Series([np.nan] * n)), errors="coerce").to_numpy()
    floors = pd.to_numeric(
        buildings.get("num_floors", pd.Series([np.nan] * n)), errors="coerce"
    ).to_numpy()

    # 1. measured
    m = np.isfinite(h) & (h > 0)
    heights[m] = h[m]
    source[m] = "measured"

    # 2. floors
    m2 = ~m & np.isfinite(floors) & (floors > 0)
    heights[m2] = floors[m2] * floor_height_m
    source[m2] = "floors"

    # 3. raster
    if raster_heights is not None:
        r = np.asarray(raster_heights, dtype="float64")
        m3 = (source == "prior") & np.isfinite(r) & (r > 0)
        heights[m3] = r[m3]
        source[m3] = "raster"

    # 4. prior
    m4 = source == "prior"
    heights[m4] = prior_m

    heights = np.clip(heights, MIN_HEIGHT_M, None)
    mix = {k: int((source == k).sum()) for k in ("measured", "floors", "raster", "prior")}
    return HeightResult(heights, source, mix)
