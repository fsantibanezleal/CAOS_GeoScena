"""Per-layer provenance and the license registry.

Every layer in a SceneBundle carries a ``LayerProvenance`` recording exactly where the
data came from, under which license, and when it was fetched. This is not decoration:
it is what lets the product show honest data credits and lets a reviewer audit any
number back to its source. Nothing enters a bundle without provenance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Canonical license records for the open sources geoscena knows how to fetch. Each entry
# is (spdx-or-name, url, commercial_ok). Verified 2026-07-12 against each source's
# official terms; see CAOS_MANAGE/wip/maqueta/research-data-sources-2026-07-12.md.
LICENSES: dict[str, dict] = {
    "ODbL-1.0": {
        "name": "Open Data Commons Open Database License v1.0",
        "url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "commercial_ok": True,
        "attribution": True,
        "share_alike": True,
    },
    "CC-BY-4.0": {
        "name": "Creative Commons Attribution 4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "commercial_ok": True,
        "attribution": True,
        "share_alike": False,
    },
    "CC-BY-NC-SA-4.0": {
        "name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0",
        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "commercial_ok": False,
        "attribution": True,
        "share_alike": True,
    },
    "PDDL-public-domain": {
        "name": "Public Domain (US Government work)",
        "url": "https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map",
        "commercial_ok": True,
        "attribution": False,
        "share_alike": False,
    },
    "Copernicus-free": {
        "name": "Copernicus DEM free-of-charge license (ESA/DLR)",
        "url": "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model",
        "commercial_ok": True,
        "attribution": True,
        "share_alike": False,
    },
}


@dataclass
class LayerProvenance:
    """Where a single bundle layer came from.

    Attributes:
        source: dataset name (e.g. "Overture Maps buildings").
        url: canonical source URL or bucket path.
        license: a key into ``LICENSES``.
        fetched: ISO date the data was fetched/derived (passed in; never auto-stamped
            so builds stay deterministic).
        method: short note on how the layer was derived (e.g. the height ladder mix).
        extra: free-form counts/metrics recorded per layer.
    """

    source: str
    url: str
    license: str
    fetched: str
    method: str = ""
    extra: dict = field(default_factory=dict)

    def license_record(self) -> dict:
        return LICENSES.get(self.license, {"name": self.license, "url": "", "commercial_ok": None})

    def commercial_ok(self) -> bool | None:
        return self.license_record().get("commercial_ok")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["license_name"] = self.license_record().get("name", self.license)
        d["license_url"] = self.license_record().get("url", "")
        d["commercial_ok"] = self.commercial_ok()
        return d
