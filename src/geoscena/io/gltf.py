"""glTF/GLB writers for bundle layers.

Writes each MeshLayer / PointLayer to a valid binary glTF (.glb) with per-vertex colours.
Geometry arrives in the AOI local metric frame (x=east, y=north, z=up, metres); glTF is a
right-handed Y-up format, so the writer converts once here:

    glTF (x, y, z) = (east, up, -north)

giving a Y-up scene that three.js loads directly with no per-app fix-up. Per-feature
attributes (height, source, class) are attached to the glTF node ``extras`` so the viewer
can show a value read-out on pick.

geoscena emits *uncompressed but valid* GLB. Web-delivery compression (meshopt via
``gltfpack`` / Draco via ``gltf-transform``) is a delivery-layer optimization owned by the
consuming product's export stage; ``compress_glb`` wires it in when the CLI tool is present.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh

from geoscena.bundle import MeshLayer, PointLayer


def _to_gltf_frame(v: np.ndarray) -> np.ndarray:
    """(east, north, up) metres -> glTF Y-up (east, up, -north)."""
    out = np.empty_like(v, dtype="float32")
    out[:, 0] = v[:, 0]
    out[:, 1] = v[:, 2]
    out[:, 2] = -v[:, 1]
    return out


def write_mesh_glb(mesh: MeshLayer, path: str | Path) -> Path:
    verts = _to_gltf_frame(np.asarray(mesh.vertices, dtype="float32"))
    faces = np.asarray(mesh.faces, dtype="int64")
    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    if mesh.colors is not None:
        rgba = np.empty((mesh.colors.shape[0], 4), dtype="uint8")
        rgba[:, :3] = mesh.colors
        rgba[:, 3] = 255
        tm.visual = trimesh.visual.ColorVisuals(mesh=tm, vertex_colors=rgba)
    scene = trimesh.Scene()
    node_extras = {"layer": mesh.name}
    if mesh.features:
        node_extras["features"] = mesh.features
    if mesh.feature_ids is not None:
        node_extras["feature_ids"] = np.asarray(mesh.feature_ids, dtype="int32").tolist()
    scene.add_geometry(tm, node_name=mesh.name, geom_name=mesh.name)
    scene.metadata["extras"] = node_extras
    path = Path(path)
    path.write_bytes(scene.export(file_type="glb"))
    return path


def write_points_glb(pts: PointLayer, path: str | Path) -> Path:
    pos = _to_gltf_frame(np.asarray(pts.positions, dtype="float32"))
    colors = None
    if pts.colors is not None:
        colors = np.empty((pts.colors.shape[0], 4), dtype="uint8")
        colors[:, :3] = pts.colors
        colors[:, 3] = 255
    cloud = trimesh.PointCloud(vertices=pos, colors=colors)
    scene = trimesh.Scene()
    scene.add_geometry(cloud, node_name=pts.name, geom_name=pts.name)
    path = Path(path)
    path.write_bytes(scene.export(file_type="glb"))
    return path


def compress_glb(path: str | Path) -> bool:
    """meshopt-compress a GLB in place with ``gltfpack`` if it is on PATH.

    Returns True if compression ran. Silent no-op (returns False) when the tool is
    absent, so a build never fails for lack of an optional delivery optimizer.
    """
    exe = shutil.which("gltfpack")
    if not exe:
        return False
    path = Path(path)
    subprocess.run([exe, "-i", str(path), "-o", str(path), "-cc"], check=True)
    return True
