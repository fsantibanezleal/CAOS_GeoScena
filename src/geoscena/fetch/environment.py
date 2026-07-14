"""Environment fetch: solar-energy potential + climate normals for an AOI, from no-auth open APIs.

This is the non-imagery half of the fusion: the scalar geophysical context of a place. Unlike the
Sentinel-2 indices (which vary building-to-building inside one AOI), solar and climate are near-constant
across a few-km AOI, so they are recorded as a per-place ``environment`` block on the manifest and, for
multi-unit places, sampled again at each admin-unit centroid so they can be aggregated/choropleth-ed by
comuna/district. Two open, no-auth, permissively-usable sources:

  * Solar    - PVGIS v5.3 (European Commission JRC): grid-connected PV yearly yield E_y (kWh/kWp) and the
               annual global horizontal irradiation H(h) (kWh/m2). Global coverage via PVGIS-SARAH3/ERA5.
  * Climate  - Open-Meteo ERA5 archive: 2023 daily 2 m mean temperature, 10 m max wind, precipitation sum,
               reduced to annual mean temperature (+ coldest/warmest day), mean daily-max wind, and annual
               precipitation total.

Everything here is a small JSON GET; there is no COG/raster read, so it is cheap enough to also call per
admin-unit centroid during ``gen_admin``. Values carry a :class:`LayerProvenance` each.
"""

from __future__ import annotations

import json
import statistics
import urllib.request
from dataclasses import dataclass, field

from geoscena.provenance import LayerProvenance

PVGIS = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_YEAR = 2023  # a full recent year of ERA5 archive; kept explicit for determinism/provenance


def _get_json(url: str, timeout: float = 45.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "geoscena/maqueta (+environment fetch)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


@dataclass
class EnvironmentResult:
    """Per-place solar + climate scalars, each keyed for the frontend attribute registry.

    ``values`` maps a stable key (solar_pvout, solar_ghi, temp_mean, temp_min, temp_max, wind_max_mean,
    precip_annual) to a float in the unit given by ``UNITS``; missing sources are simply absent.
    """

    values: dict[str, float]
    provenance: list[LayerProvenance] = field(default_factory=list)


# key -> (english label, unit) for the frontend attribute registry + manifest.
ENV_META: dict[str, tuple[str, str]] = {
    "solar_pvout": ("Solar PV yield", "kWh/kWp/yr"),
    "solar_ghi": ("Solar irradiation (GHI)", "kWh/m2/yr"),
    "temp_mean": ("Air temperature (mean)", "degC"),
    "temp_min": ("Air temperature (coldest day)", "degC"),
    "temp_max": ("Air temperature (warmest day)", "degC"),
    "wind_max_mean": ("Wind (mean daily max)", "km/h"),
    "precip_annual": ("Precipitation (annual)", "mm/yr"),
}


def fetch_solar(lat: float, lon: float, fetched: str, loss: float = 14.0) -> tuple[dict[str, float], LayerProvenance | None]:
    """Grid-connected PV yearly yield (E_y) + annual GHI at a point, from PVGIS v5.3 (no auth)."""
    try:
        url = f"{PVGIS}?lat={lat:.5f}&lon={lon:.5f}&peakpower=1&loss={loss}&outputformat=json"
        js = _get_json(url)
        fixed = js["outputs"]["totals"]["fixed"]
        vals: dict[str, float] = {}
        if fixed.get("E_y") is not None:
            vals["solar_pvout"] = round(float(fixed["E_y"]), 0)  # kWh/kWp/yr
        # H(i)_y is plane-of-array; H(h)_y (global horizontal) is what "irradiation" means generically.
        ghi = fixed.get("H(h)_y") or fixed.get("H(i)_y")
        if ghi is not None:
            vals["solar_ghi"] = round(float(ghi), 0)  # kWh/m2/yr
        if not vals:
            return {}, None
        db = js.get("inputs", {}).get("meteo_data", {}).get("radiation_db", "PVGIS")
        prov = LayerProvenance(
            source=f"PVGIS v5.3 PV yield + irradiation ({db})",
            url="https://re.jrc.ec.europa.eu/api/v5_3/PVcalc (European Commission JRC)",
            license="proprietary",  # PVGIS data free to use with attribution to EC JRC
            fetched=fetched,
            method="grid-connected 1 kWp fixed-mount PVcalc, 14% system loss; yearly E_y + annual GHI at the AOI centre",
            extra={"radiation_db": db, "loss_pct": loss},
        )
        return vals, prov
    except Exception:
        return {}, None


def fetch_climate(lat: float, lon: float, fetched: str, year: int = CLIMATE_YEAR) -> tuple[dict[str, float], LayerProvenance | None]:
    """Annual temperature/wind/precipitation normals at a point, from the Open-Meteo ERA5 archive (no auth)."""
    try:
        url = (
            f"{OPEN_METEO}?latitude={lat:.5f}&longitude={lon:.5f}"
            f"&start_date={year}-01-01&end_date={year}-12-31"
            "&daily=temperature_2m_mean,wind_speed_10m_max,precipitation_sum&timezone=auto"
        )
        d = _get_json(url).get("daily", {})
        temps = [x for x in d.get("temperature_2m_mean", []) if x is not None]
        winds = [x for x in d.get("wind_speed_10m_max", []) if x is not None]
        precs = [x for x in d.get("precipitation_sum", []) if x is not None]
        vals: dict[str, float] = {}
        if temps:
            vals["temp_mean"] = round(statistics.mean(temps), 1)
            vals["temp_min"] = round(min(temps), 1)
            vals["temp_max"] = round(max(temps), 1)
        if winds:
            vals["wind_max_mean"] = round(statistics.mean(winds), 1)
        if precs:
            vals["precip_annual"] = round(sum(precs), 0)
        if not vals:
            return {}, None
        prov = LayerProvenance(
            source=f"Open-Meteo ERA5 archive ({year} daily normals)",
            url="https://archive-api.open-meteo.com/v1/archive (ERA5 reanalysis, ~25 km)",
            license="cc-by-4.0",  # Open-Meteo data CC-BY-4.0; ERA5 via Copernicus
            fetched=fetched,
            method=f"{year} daily 2 m mean temp / 10 m max wind / precip sum, reduced to annual mean+extremes at the AOI centre",
            extra={"year": year, "days": len(temps)},
        )
        return vals, prov
    except Exception:
        return {}, None


def fetch_environment(lat: float, lon: float, fetched: str) -> EnvironmentResult:
    """Solar + climate scalars at a point (the AOI centre, or an admin-unit centroid for aggregation)."""
    values: dict[str, float] = {}
    prov: list[LayerProvenance] = []
    sv, sp = fetch_solar(lat, lon, fetched)
    values.update(sv)
    if sp is not None:
        prov.append(sp)
    cv, cp = fetch_climate(lat, lon, fetched)
    values.update(cv)
    if cp is not None:
        prov.append(cp)
    return EnvironmentResult(values=values, provenance=prov)
