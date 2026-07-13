"""End-to-end AOI build: fetch -> fuse -> mesh -> SceneBundle.

``build_scene`` is the single entry point that turns an AOI into a written SceneBundle
directory (per-layer .glb + manifest.json). It is deliberately layer-tolerant: any source
that is unavailable for a given AOI (no buildings in a wilderness area, no OSM water) is
skipped with a recorded note rather than failing the whole build, so a terrain-first
natural area and a dense city both build from the same call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoscena.aoi import AOI
from geoscena.bundle import SceneBundle
from geoscena.fetch import dem as dem_mod
from geoscena.fetch import worldcover as wc_mod
from geoscena.fuse.heights import assign_heights
from geoscena.mesh.extrude import extrude_buildings
from geoscena.mesh.roads import road_ribbons
from geoscena.mesh.terrain import terrain_mesh


@dataclass
class BuildConfig:
    fetched: str  # ISO date recorded as provenance (kept explicit for determinism)
    terrain_max_error_m: float = 1.5
    terrain_max_vertices: int = 6000
    include_buildings: bool = True
    include_roads: bool = True
    include_context: bool = True
    include_population: bool = True
    include_ground_truth: bool = True
    overture_release: str | None = None
    notes: list[str] = field(default_factory=list)


def build_scene(aoi: AOI, cfg: BuildConfig) -> SceneBundle:
    """Fetch every available layer for the AOI and assemble a SceneBundle."""
    bundle = SceneBundle(aoi=aoi)
    notes: list[str] = list(cfg.notes)
    ground_truth: dict | None = None

    # --- terrain (always) ---
    dem = dem_mod.fetch_dem(aoi, fetched=cfg.fetched)
    terrain = terrain_mesh(
        aoi, dem, max_error_m=cfg.terrain_max_error_m, max_vertices=cfg.terrain_max_vertices
    )
    bundle.add_mesh(terrain, dem.provenance)

    # --- land cover (recolours terrain zones; sampled onto buildings) ---
    landcover = None
    try:
        landcover = wc_mod.fetch_landcover(aoi, fetched=cfg.fetched)
    except Exception as exc:  # noqa: BLE001 - record and continue
        notes.append(f"landcover skipped: {exc}")

    height_mix: dict[str, int] = {}
    # --- buildings ---
    if cfg.include_buildings:
        try:
            from geoscena.fetch import overture as ov

            release = cfg.overture_release or ov.DEFAULT_RELEASE
            gdf = ov.fetch_buildings(aoi, fetched=cfg.fetched, release=release)
            if len(gdf):
                cent = gdf.geometry.representative_point()
                base = dem.sample(cent.x.to_numpy(), cent.y.to_numpy())
                base = np.where(np.isfinite(base), base, float(np.nanmin(dem.z)))
                classes = (
                    landcover.sample(cent.x.to_numpy(), cent.y.to_numpy())
                    if landcover is not None
                    else None
                )
                # rung 3 of the ladder: Open Buildings 2.5D height raster (Global South only).
                raster_h = None
                try:
                    from geoscena.fetch.openbuildings import fetch_height_raster

                    hr = fetch_height_raster(aoi, fetched=cfg.fetched)
                    if hr is not None:
                        raster_h = hr.sample(cent.x.to_numpy(), cent.y.to_numpy())
                        notes.append(f"open-buildings 2.5D raster used ({hr.provenance.extra.get('epsg')})")
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"2.5D raster skipped: {exc}")
                hres = assign_heights(gdf, raster_heights=raster_h)
                height_mix = hres.mix
                # benchmark the fused heights against an authoritative LoD2 model where one exists.
                if cfg.include_ground_truth:
                    try:
                        from geoscena.fetch.citymodel import compare_heights, fetch_3dbag

                        gt = fetch_3dbag(aoi, fetched=cfg.fetched)
                        if gt is not None:
                            ground_truth = compare_heights(
                                cent.x.to_numpy(), cent.y.to_numpy(), hres.heights, gt, aoi
                            )
                            notes.append(f"ground-truth vs {gt.provenance.source}")
                    except Exception as exc:  # noqa: BLE001
                        notes.append(f"ground-truth skipped: {exc}")
                mesh = extrude_buildings(
                    aoi, gdf, hres.heights, hres.source, base_elev=base, classes=classes
                )
                bundle.add_mesh(mesh, gdf.attrs["provenance"])
            else:
                notes.append("no buildings in AOI")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"buildings skipped: {exc}")

    # --- roads ---
    if cfg.include_roads:
        try:
            from geoscena.fetch import overture as ov

            release = cfg.overture_release or ov.DEFAULT_RELEASE
            roads = ov.fetch_roads(aoi, fetched=cfg.fetched, release=release)
            if len(roads):
                mesh = road_ribbons(aoi, roads, dem=dem)
                bundle.add_mesh(mesh, roads.attrs["provenance"])
            else:
                notes.append("no roads in AOI")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"roads skipped: {exc}")

    # --- OSM context (water / green / rail) ---
    if cfg.include_context:
        try:
            from geoscena.fetch import osm

            for layer in ("water", "green", "rail"):
                try:
                    gdf = osm.fetch_context(aoi, layer, fetched=cfg.fetched)
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"context {layer} skipped: {exc}")
                    continue
                if not len(gdf):
                    continue
                if layer == "rail":
                    mesh = road_ribbons(aoi, gdf, dem=dem, is_rail=True)
                else:
                    mesh = _flat_polygons(aoi, gdf, dem, layer)
                if mesh.faces.shape[0]:
                    bundle.add_mesh(mesh, gdf.attrs["provenance"])
        except ImportError as exc:
            notes.append(f"OSM context unavailable: {exc}")

    # --- population (GHS-POP) ---
    if cfg.include_population:
        try:
            from geoscena.fetch.ghsl import fetch_population
            from geoscena.mesh.population import population_mesh

            pop = fetch_population(aoi, fetched=cfg.fetched)
            if pop.total() > 0:
                mesh = population_mesh(aoi, pop, dem=dem)
                if mesh.faces.shape[0]:
                    bundle.add_mesh(mesh, pop.provenance)
                    notes.append(f"population total ~{int(pop.total())}")
            else:
                notes.append("no population in AOI")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"population skipped: {exc}")

    bundle.stats = {
        "layers": bundle.layer_names(),
        "height_mix": height_mix,
        "budgets": {
            name: (bundle.meshes.get(name) or bundle.points[name]).stats()
            for name in bundle.layer_names()
        },
        "ground_truth": ground_truth,
        "notes": notes,
    }
    return bundle


def _flat_polygons(aoi: AOI, gdf, dem, layer: str):
    """Triangulate water/green polygons as flat surfaces draped on the terrain."""
    import numpy as np
    from mapbox_earcut import triangulate_float64
    from shapely.geometry import MultiPolygon, Polygon

    from geoscena.bundle import MeshLayer

    COLORS = {"water": (0, 95, 175), "green": (46, 120, 60)}
    tr = aoi.transformer_to_local()
    all_v, all_f, voff = [], [], 0
    for geom in gdf.geometry.to_numpy():
        polys = (
            [geom]
            if isinstance(geom, Polygon)
            else list(geom.geoms)
            if isinstance(geom, MultiPolygon)
            else []
        )
        for poly in polys:
            if poly.is_empty or poly.exterior is None:
                continue
            ext = np.asarray(poly.exterior.coords)[:-1]
            if ext.shape[0] < 3:
                continue
            x, y = tr.transform(ext[:, 0], ext[:, 1])
            ring = np.column_stack([x, y]).astype("float64")
            tri = triangulate_float64(ring, np.array([ring.shape[0]], dtype="uint32")).reshape(-1, 3)
            if tri.shape[0] == 0:
                continue
            z = dem.sample(ext[:, 0], ext[:, 1])
            z = np.where(np.isfinite(z), z, float(np.nanmin(dem.z))) + 0.2
            verts = np.column_stack([ring, z]).astype("float32")
            all_v.append(verts)
            all_f.append(tri.astype("int64") + voff)
            voff += verts.shape[0]
    if not all_v:
        return MeshLayer(layer, np.zeros((0, 3), "float32"), np.zeros((0, 3), "int64"))
    verts = np.vstack(all_v)
    return MeshLayer(
        layer,
        verts,
        np.vstack(all_f),
        colors=np.tile(np.array(COLORS[layer], "uint8"), (verts.shape[0], 1)),
    )
