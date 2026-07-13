"""Area of Interest: a geographic extent plus a local metric projection.

An AOI is defined by a WGS84 centre (lon, lat) and a half-size in metres, or by an
explicit WGS84 bounding box. It exposes a local East-North-Up (ENU) projection centred
on the AOI so that every downstream layer can be expressed in metres relative to the
same origin. That local metric frame is what the 3D viewer consumes (Three.js works in
metres, Y-up), and it keeps small-area distortion negligible.

The projection is a local Azimuthal Equidistant (AEQD) centred on the AOI centroid,
which preserves distance from the centre and is accurate to well under a metre across
the few-kilometre AOIs this package targets.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import Transformer


@dataclass(frozen=True)
class AOI:
    """A named area of interest with a local metric projection.

    Attributes:
        name: human-readable identifier (also used as a slug component).
        west/south/east/north: WGS84 bounding box in degrees.
        lat0/lon0: projection origin (AOI centroid) in degrees.
    """

    name: str
    west: float
    south: float
    east: float
    north: float

    @property
    def lon0(self) -> float:
        return (self.west + self.east) / 2.0

    @property
    def lat0(self) -> float:
        return (self.south + self.north) / 2.0

    @classmethod
    def from_center(cls, name: str, lon: float, lat: float, half_size_m: float) -> AOI:
        """Build a square AOI of side ``2 * half_size_m`` metres around a centre."""
        # metres-per-degree at this latitude (WGS84 spherical approximation).
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * float(np.cos(np.radians(lat)))
        dlat = half_size_m / m_per_deg_lat
        dlon = half_size_m / m_per_deg_lon
        return cls(name, lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """WGS84 bounding box as (west, south, east, north)."""
        return (self.west, self.south, self.east, self.north)

    def _proj4(self) -> str:
        return (
            f"+proj=aeqd +lat_0={self.lat0} +lon_0={self.lon0} "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )

    def transformer_to_local(self) -> Transformer:
        """Transformer from WGS84 (EPSG:4326) to the AOI local metric frame."""
        return Transformer.from_crs("EPSG:4326", self._proj4(), always_xy=True)

    def to_local(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Project WGS84 lon/lat arrays to local metres (x=east, y=north)."""
        tr = self.transformer_to_local()
        x, y = tr.transform(np.asarray(lon), np.asarray(lat))
        return np.asarray(x), np.asarray(y)

    @property
    def crs_local(self) -> str:
        """PROJ string of the local metric frame (for GeoPandas ``to_crs``)."""
        return self._proj4()

    def size_m(self) -> tuple[float, float]:
        """Approximate AOI extent (width, height) in metres."""
        w = (self.east - self.west) * 111_320.0 * float(np.cos(np.radians(self.lat0)))
        h = (self.north - self.south) * 111_320.0
        return (w, h)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "bbox_wgs84": [self.west, self.south, self.east, self.north],
            "origin_wgs84": [self.lon0, self.lat0],
            "crs_local": self.crs_local,
            "size_m": list(self.size_m()),
        }
