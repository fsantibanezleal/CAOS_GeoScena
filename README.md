# geoscena

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**AOI public-geodata acquisition + SceneBundle fusion and meshing core for 3D area
reconstruction.** `geoscena` turns a geographic Area of Interest into a projected, fused,
mesh-ready `SceneBundle` (Draco/meshopt-ready glTF layers + a provenance manifest) assembled
from open public datasets. It is the reusable, product-agnostic core behind
[Maqueta](https://github.com/fsantibanezleal/CAOS_RES_Maqueta); nothing enters a bundle
without recorded provenance (source, URL, license, fetch date).

## What it does

Given an AOI (a centre + half-size, or a bbox), geoscena:

1. **Fetches** each available open layer, AOI-scoped, from its authoritative source:
   - **Buildings + roads** from Overture Maps GeoParquet on S3 (DuckDB spatial pre-filter).
   - **Terrain** from Copernicus GLO-30 DSM (AWS Open Data, keyless COG windowed reads).
   - **Land cover** from ESA WorldCover 10 m (AWS Open Data).
   - **Water / green / rail** context from OpenStreetMap (OSMnx / Overpass).
   - (extendable: Google Open Buildings 2.5D height rasters, GHS-POP, USGS 3DEP lidar.)
2. **Fuses** them: the **height-provenance ladder** assigns every building a height from the
   best available source (measured -> floors x floor-height -> height raster -> prior) and
   records *which* source was used per building, so inference is reported, never hidden.
3. **Meshes** in the AOI local metric frame (metres, Y-up on export): adaptive terrain TIN
   (Delatin-style greedy refinement), extruded building prisms, buffered road/rail ribbons
   draped on the terrain, flat water/green surfaces.
4. **Writes** a `SceneBundle`: one `.glb` per layer + `manifest.json` (the processing->web
   contract), with per-layer stats, height-provenance mix, and a data-credits list.

## Install

```bash
pip install geoscena                 # core (numpy/scipy/shapely/geopandas/rasterio/trimesh)
pip install 'geoscena[overture]'     # + DuckDB (buildings/roads)
pip install 'geoscena[osm]'          # + OSMnx (water/green/rail)
pip install 'geoscena[all]'          # everything (incl. lidar, gltf compression helpers)
```

Python >= 3.11. No native compiler required (the terrain TIN is pure-Python over SciPy).

## Use

```python
from geoscena.aoi import AOI
from geoscena.build import BuildConfig, build_scene

aoi = AOI.from_center("Berlin Mitte", lon=13.405, lat=52.517, half_size_m=1200)
bundle = build_scene(aoi, BuildConfig(fetched="2026-07-12"))
bundle.write("out/berlin_mitte")   # -> terrain.glb, buildings.glb, roads.glb, manifest.json
```

or from the CLI:

```bash
geoscena build --name "Berlin Mitte" --lon 13.405 --lat 52.517 --half 1200 \
    --fetched 2026-07-12 --out out/berlin_mitte
geoscena info    # list known sources + licenses
```

## Provenance and licensing

Every layer carries a `LayerProvenance` (source, URL, license key, fetch date, method).
`bundle.any_noncommercial()` flags AOIs that pulled a non-commercial source. Default sources
are all commercial-OK: Overture/OSM (ODbL), GLO-30 (Copernicus free), WorldCover (CC-BY-4.0).
See [`docs/`](docs/) for the data contracts and per-source cards.

## Status

`0.x` while the SceneBundle contract stabilizes. Consumed by Maqueta via git tag ref until the
first PyPI release (ADR-0061 trusted publishing).

Owner: Felipe Santibanez-Leal · fsantibanez@gmail.com · [@fsantibanezleal](https://github.com/fsantibanezleal)
