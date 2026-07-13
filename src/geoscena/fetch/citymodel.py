"""Ground-truth fetcher: authoritative LoD2 building heights from 3DBAG (Netherlands).

For Tier-A places with an open LoD2 model, this fetches per-building heights from the authoritative
3D BAG (via its OGC API, native RD / EPSG:28992), so Maqueta's FUSED reconstruction can be benchmarked
against ground truth (height RMSE, coverage). Height above ground = roof height (b3_h_dak_50p) minus
ground level (b3_h_maaiveld).

License: CC-BY 4.0 (3D BAG / TU Delft 3D geoinformation).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer

from geoscena.aoi import AOI
from geoscena.provenance import LayerProvenance

API = "https://api.3dbag.nl/collections/pand/items"


@dataclass
class GroundTruth:
    lon: np.ndarray
    lat: np.ndarray
    height: np.ndarray  # metres above ground
    provenance: LayerProvenance


def _feature_centroid_height(feat: dict) -> tuple[float, float, float] | None:
    """Return (rd_x, rd_y, height_m) for a 3DBAG CityJSONFeature, or None."""
    transform = feat.get("transform")
    verts = feat.get("vertices")
    cos = feat.get("CityObjects", {})
    if not transform or not verts or not cos:
        return None
    sx, sy, sz = transform["scale"]
    tx, ty, tz = transform["translate"]
    v = np.asarray(verts, dtype="float64")
    xs = v[:, 0] * sx + tx
    ys = v[:, 1] * sy + ty
    cx, cy = float(xs.mean()), float(ys.mean())
    for o in cos.values():
        a = o.get("attributes", {})
        dak = a.get("b3_h_dak_50p")
        grd = a.get("b3_h_maaiveld")
        if dak is not None and grd is not None:
            return (cx, cy, float(dak) - float(grd))
    return None


def fetch_3dbag(aoi: AOI, fetched: str, max_pages: int = 8) -> GroundTruth | None:
    """Fetch authoritative LoD2 building heights over the AOI from 3DBAG. None if outside NL.

    Capped at ``max_pages`` x 1000 buildings: a representative sample is plenty for a height-RMSE
    benchmark and keeps the per-bake cost bounded (only NL Tier-A places hit this path).
    """
    tr = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
    w, s, e, n = aoi.bbox
    xs, ys = tr.transform([w, e, w, e], [s, s, n, n])
    bbox = f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"

    lon_l, lat_l, h_l = [], [], []
    url = f"{API}?bbox={bbox}&limit=1000"
    inv = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    for _ in range(max_pages):
        try:
            doc = json.loads(urllib.request.urlopen(url, timeout=40).read())
        except Exception:
            break
        feats = doc.get("features", [])
        if not feats:
            break
        for f in feats:
            ch = _feature_centroid_height(f)
            if ch is None or not (0 < ch[2] < 400):
                continue
            lon_i, lat_i = inv.transform(ch[0], ch[1])
            lon_l.append(lon_i)
            lat_l.append(lat_i)
            h_l.append(ch[2])
        nxt = [ln["href"] for ln in doc.get("links", []) if ln.get("rel") == "next"]
        if not nxt:
            break
        url = nxt[0]

    if not h_l:
        return None
    prov = LayerProvenance(
        source="3D BAG LoD2 (TU Delft)",
        url="https://api.3dbag.nl/collections/pand",
        license="CC-BY-4.0",
        fetched=fetched,
        method="OGC API items (RD/EPSG:28992 bbox); height = b3_h_dak_50p - b3_h_maaiveld",
        extra={"n_buildings": len(h_l)},
    )
    return GroundTruth(np.asarray(lon_l), np.asarray(lat_l), np.asarray(h_l), prov)


def compare_heights(
    fused_lon: np.ndarray,
    fused_lat: np.ndarray,
    fused_h: np.ndarray,
    truth: GroundTruth,
    aoi: AOI,
    match_radius_m: float = 25.0,
) -> dict:
    """Match fused buildings to nearest ground-truth building; report height RMSE + coverage."""
    fx, fy = aoi.to_local(fused_lon, fused_lat)
    tx, ty = aoi.to_local(truth.lon, truth.lat)
    from scipy.spatial import cKDTree

    tree = cKDTree(np.column_stack([tx, ty]))
    dist, idx = tree.query(np.column_stack([fx, fy]), k=1)
    matched = dist <= match_radius_m
    if matched.sum() < 5:
        return {"matched": int(matched.sum()), "note": "too few matches"}
    err = fused_h[matched] - truth.height[idx[matched]]
    return {
        "n_fused": int(len(fused_h)),
        "n_truth": int(len(truth.height)),
        "matched": int(matched.sum()),
        "coverage_pct": round(100 * matched.sum() / len(fused_h), 1),
        "height_rmse_m": round(float(np.sqrt(np.mean(err**2))), 2),
        "height_mae_m": round(float(np.mean(np.abs(err))), 2),
        "height_bias_m": round(float(np.mean(err)), 2),
        "truth_source": truth.provenance.source,
    }
