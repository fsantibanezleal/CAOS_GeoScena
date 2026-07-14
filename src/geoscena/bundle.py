"""The SceneBundle contract: the canonical fused, mesh-ready representation of an AOI.

A SceneBundle is the product-agnostic hand-off between the fusion/meshing core and any
renderer. It holds, in the AOI local metric frame (metres, Y-up on export):

  * a set of named mesh layers (buildings, terrain, roads, water, ...), each a plain
    numpy triangle mesh with optional per-vertex colour and per-feature metadata;
  * optional point layers (e.g. decimated lidar);
  * one ``LayerProvenance`` per layer;
  * baked statistics (counts, budgets, height-provenance mix) for the Benchmark surface.

On export it becomes a directory of Draco-compressed glTF (.glb) files plus a single
``manifest.json`` (CONTRACT 2, the processing -> web contract). A TypeScript type mirrors
the manifest in the product so any drift fails the web build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoscena.aoi import AOI
from geoscena.provenance import LICENSES, LayerProvenance

BUNDLE_SCHEMA_VERSION = 1


@dataclass
class MeshLayer:
    """A triangle-mesh layer in AOI-local metres (x=east, y=north, z=up).

    ``vertices`` is (N, 3) float; ``faces`` is (M, 3) int; ``colors`` is optional (N, 3)
    uint8; ``feature_ids`` optionally maps each vertex to a feature index; ``features``
    is an optional per-feature attribute table (height, source, class, ...).
    """

    name: str
    vertices: np.ndarray
    faces: np.ndarray
    colors: np.ndarray | None = None
    feature_ids: np.ndarray | None = None
    features: list[dict] = field(default_factory=list)

    def stats(self) -> dict:
        return {
            "kind": "mesh",
            "vertices": int(self.vertices.shape[0]),
            "triangles": int(self.faces.shape[0]),
            "features": len(self.features),
        }


@dataclass
class PointLayer:
    """A point layer in AOI-local metres (e.g. decimated lidar returns)."""

    name: str
    positions: np.ndarray  # (N, 3) float
    colors: np.ndarray | None = None  # (N, 3) uint8

    def stats(self) -> dict:
        return {"kind": "points", "points": int(self.positions.shape[0])}


@dataclass
class SceneBundle:
    """The fused, mesh-ready representation of one AOI."""

    aoi: AOI
    schema_version: int = BUNDLE_SCHEMA_VERSION
    meshes: dict[str, MeshLayer] = field(default_factory=dict)
    points: dict[str, PointLayer] = field(default_factory=dict)
    provenance: dict[str, LayerProvenance] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    # Fused topic modalities (solar, soil, ...) sampled as per-building attributes rather than their own
    # layer; recorded here so the manifest still carries each one's source + license (honesty).
    modalities: list[dict] = field(default_factory=list)
    # Per-place scalar environment (solar-energy potential + climate normals): near-constant across the AOI,
    # so recorded once for the place (and, for multi-unit places, per admin unit in admin.json) rather than
    # per building. {"values": {key: float}, "meta": {key: {label, unit}}, "sources": [prov dicts]}.
    environment: dict = field(default_factory=dict)

    def add_mesh(self, layer: MeshLayer, prov: LayerProvenance) -> None:
        self.meshes[layer.name] = layer
        self.provenance[layer.name] = prov

    def add_points(self, layer: PointLayer, prov: LayerProvenance) -> None:
        self.points[layer.name] = layer
        self.provenance[layer.name] = prov

    def add_modality(self, key: str, label: str, unit: str, prov: LayerProvenance) -> None:
        rec = prov.as_dict()
        rec.update({"key": key, "label": label, "unit": unit})
        self.modalities.append(rec)

    def layer_names(self) -> list[str]:
        return list(self.meshes) + list(self.points)

    def any_noncommercial(self) -> bool:
        """True if any layer's license forbids commercial use (a product caveat)."""
        return any(
            LICENSES.get(p.license, {}).get("commercial_ok") is False
            for p in self.provenance.values()
        )

    def to_manifest(self) -> dict:
        """CONTRACT 2 manifest: the processing -> web hand-off for this AOI."""
        layers = []
        for name in self.layer_names():
            layer = self.meshes.get(name) or self.points[name]
            prov = self.provenance[name]
            layers.append(
                {
                    "name": name,
                    "file": f"{name}.glb",
                    "stats": layer.stats(),
                    "provenance": prov.as_dict(),
                }
            )
        return {
            "schema_version": self.schema_version,
            "aoi": self.aoi.as_dict(),
            "layers": layers,
            "stats": self.stats,
            "modalities": self.modalities,
            "environment": self.environment,
            "any_noncommercial": self.any_noncommercial()
            or any(m.get("commercial_ok") is False for m in self.modalities),
            "credits": sorted(
                {
                    f"{p.source} ({p.license_record().get('name', p.license)})"
                    for p in self.provenance.values()
                }
                | {f"{m['source']} ({m.get('license_name', m['license'])})" for m in self.modalities}
            ),
        }

    def write(self, out_dir: str | Path) -> Path:
        """Write every layer to a .glb and the manifest to ``manifest.json``.

        Import is deferred so the meshing/export deps are only needed at write time.
        """
        from geoscena.io.gltf import write_mesh_glb, write_points_glb

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, mesh in self.meshes.items():
            write_mesh_glb(mesh, out / f"{name}.glb")
        for name, pts in self.points.items():
            write_points_glb(pts, out / f"{name}.glb")
        manifest = self.to_manifest()
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return out
