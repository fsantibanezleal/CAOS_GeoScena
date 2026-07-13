"""geoscena: AOI public-geodata acquisition + SceneBundle fusion and meshing core.

The reusable, product-agnostic core behind Maqueta. It turns a geographic Area of
Interest (AOI) into a projected, fused, mesh-ready SceneBundle assembled from open
public datasets (Overture buildings/roads, Copernicus GLO-30 terrain, ESA WorldCover
land cover, OSM context, GHS-POP population, Google Open Buildings 2.5D heights, USGS
3DEP lidar), with per-layer provenance (source, URL, license, fetch date).

Every layer records where it came from and under which license; nothing is invented.
"""

from geoscena.aoi import AOI
from geoscena.bundle import SceneBundle
from geoscena.provenance import LICENSES, LayerProvenance

__all__ = ["AOI", "SceneBundle", "LayerProvenance", "LICENSES", "__version__"]

__version__ = "0.01.001"
