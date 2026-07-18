"""Offline unit tests for the geoscena core (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from geoscena.aoi import AOI
from geoscena.bundle import MeshLayer, SceneBundle
from geoscena.fuse.heights import assign_heights
from geoscena.provenance import LICENSES, LayerProvenance


def test_aoi_from_center_size():
    aoi = AOI.from_center("X", lon=13.4, lat=52.5, half_size_m=1000)
    w, h = aoi.size_m()
    assert abs(w - 2000) < 5 and abs(h - 2000) < 5
    assert abs(aoi.lon0 - 13.4) < 1e-9 and abs(aoi.lat0 - 52.5) < 1e-9


def test_aoi_projection_roundtrip():
    aoi = AOI.from_center("X", lon=13.4, lat=52.5, half_size_m=1500)
    lon = np.array([13.40, 13.41, 13.39])
    lat = np.array([52.50, 52.51, 52.49])
    x, y = aoi.to_local(lon, lat)
    inv = aoi.transformer_to_local()
    lon2, lat2 = inv.transform(x, y, direction="INVERSE")
    assert np.allclose(lon, lon2, atol=1e-7)
    assert np.allclose(lat, lat2, atol=1e-7)
    # origin projects to (0, 0)
    ox, oy = aoi.to_local(np.array([aoi.lon0]), np.array([aoi.lat0]))
    assert abs(float(ox[0])) < 1e-6 and abs(float(oy[0])) < 1e-6


def test_provenance_license_lookup():
    p = LayerProvenance("Overture", "s3://x", "ODbL-1.0", "2026-07-12")
    assert p.commercial_ok() is True
    p2 = LayerProvenance("FABDEM", "http://x", "CC-BY-NC-SA-4.0", "2026-07-12")
    assert p2.commercial_ok() is False
    assert "license_name" in p.as_dict()
    assert set(["ODbL-1.0", "CC-BY-4.0", "Copernicus-free"]).issubset(LICENSES)


def test_height_ladder_precedence():
    df = pd.DataFrame(
        {
            "height": [30.0, np.nan, np.nan, np.nan],
            "num_floors": [np.nan, 5, np.nan, np.nan],
        }
    )
    raster = np.array([np.nan, np.nan, 12.0, np.nan])
    res = assign_heights(df, raster_heights=raster, floor_height_m=3.0, prior_m=8.0)
    assert list(res.source) == ["measured", "floors", "raster", "prior"]
    assert res.heights[0] == 30.0
    assert res.heights[1] == 15.0
    assert res.heights[2] == 12.0
    assert res.heights[3] == 8.0
    assert res.mix == {"measured": 1, "floors": 1, "raster": 1, "prior": 1}


def test_height_min_clip():
    df = pd.DataFrame({"height": [1.0], "num_floors": [np.nan]})
    res = assign_heights(df)
    assert res.heights[0] >= 2.5


def test_bundle_manifest_and_noncommercial():
    aoi = AOI.from_center("X", 13.4, 52.5, 500)
    verts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 5]], dtype="float32")
    faces = np.array([[0, 1, 2]], dtype="int64")
    b = SceneBundle(aoi=aoi)
    b.add_mesh(
        MeshLayer("terrain", verts, faces),
        LayerProvenance("GLO-30", "s3://x", "Copernicus-free", "2026-07-12"),
    )
    man = b.to_manifest()
    assert man["schema_version"] == 1
    assert man["layers"][0]["name"] == "terrain"
    assert man["layers"][0]["stats"]["triangles"] == 1
    assert man["any_noncommercial"] is False
    b.add_mesh(
        MeshLayer("drape", verts, faces),
        LayerProvenance("EOX", "http://x", "CC-BY-NC-SA-4.0", "2026-07-12"),
    )
    assert b.to_manifest()["any_noncommercial"] is True


def test_gltf_roundtrip(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from geoscena.io.gltf import write_mesh_glb

    verts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 5]], dtype="float32")
    faces = np.array([[0, 1, 2]], dtype="int64")
    colors = np.array([[200, 100, 50]] * 3, dtype="uint8")
    layer = MeshLayer("buildings", verts, faces, colors=colors, features=[{"id": 0, "height_m": 5}])
    p = write_mesh_glb(layer, tmp_path / "b.glb")
    assert p.exists() and p.stat().st_size > 0
    sc = trimesh.load(str(p))
    geoms = list(sc.geometry.values()) if hasattr(sc, "geometry") else [sc]
    assert sum(len(g.faces) for g in geoms) == 1


def test_terrain_tin_synthetic():
    from geoscena.fetch.dem import DemGrid
    from geoscena.mesh.terrain import terrain_mesh

    aoi = AOI.from_center("X", 13.4, 52.5, 1000)
    xs = np.linspace(0, 1, 40)
    z = (np.outer(np.sin(xs * 6), np.cos(xs * 6)) * 20 + 30).astype("float32")
    prov = LayerProvenance("GLO-30", "s3://x", "Copernicus-free", "2026-07-12")
    dem = DemGrid(z, aoi.west, aoi.south, aoi.east, aoi.north, prov)
    mesh = terrain_mesh(aoi, dem, max_error_m=1.0, max_vertices=1500)
    assert mesh.vertices.shape[0] >= 9
    assert mesh.faces.shape[0] > 0
    assert mesh.faces.max() < mesh.vertices.shape[0]


def test_census_specs_wellformed():
    """INE Censo manzana modalities are registered with documented units + a valid license."""
    from geoscena.fetch.census import CENSUS_SPECS, POP_DENSITY_SPEC

    assert POP_DENSITY_SPEC.key == "pop_density" and POP_DENSITY_SPEC.unit == "people/km2"
    keys = {s.key for s in CENSUS_SPECS}
    assert keys == {"pop_density", "dwelling_density", "housing_precarity"}
    for s in CENSUS_SPECS:
        assert s.license in LICENSES
        assert "arcgis" in s.url.lower()
