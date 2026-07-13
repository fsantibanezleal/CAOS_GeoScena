# Changelog

All notable changes to `geoscena` are documented here. Format: [Keep a Changelog](https://keepachangelog.com/);
versions use `X.XX.XXX` (display) / dropped-zero semver in the manifest. `0.x` while the SceneBundle
contract is unstable.

## [0.03.000] - 2026-07-13

### Added
- **Open Buildings 2.5D Temporal height-raster fetcher** (`fetch.openbuildings`): fills rung 3 of the
  height-provenance ladder for the Global South. Locates the covering GCS tile via the level-2 S2 cell
  manifest + the AOI's UTM EPSG, windowed-reads band 2 (building_height) over `/vsicurl`, reprojects to
  a WGS84 grid, samples per building. Regions outside coverage return None (skipped). Verified on
  Santiago: 94% default-prior heights become 93% real satellite-derived heights.
- Wired the raster into `build_scene`'s height ladder (rung 3) automatically.

## [0.02.000] - 2026-07-13

### Added
- **GHS-POP population fetcher** (`fetch.ghsl`): windowed COG read of the JRC GHS-POP 100 m residential
  population grid (OpenLandMap mirror, CC-BY-4.0), plus `mesh.population` (extruded, density-coloured
  cell layer). Wired into `build_scene` as an optional `population` layer.

## [0.01.000] - 2026-07-12

### Added
- Initial core: `AOI` (WGS84 extent + local AEQD metric projection), `LayerProvenance` + license
  registry, `SceneBundle` contract (mesh/point layers + manifest, CONTRACT 2), on-disk cache.
- Fetchers: Copernicus GLO-30 terrain (AWS COG windowed reads), ESA WorldCover 10 m land cover,
  Overture Maps buildings + roads (official `overturemaps` CLI bbox extract of S3 GeoParquet),
  OpenStreetMap context (water/green/rail via OSMnx).
- Fusion: the height-provenance ladder (`fuse.heights`) with per-building source tagging + mix.
- Meshing: pure-Python adaptive terrain TIN (Delatin-style batched greedy refinement over SciPy,
  no native compiler), building extrusion, road/rail ribbons, flat water/green surfaces.
- Export: valid uncompressed GLB per layer (trimesh) with a Y-up axis convention and per-feature
  `extras`; optional `gltfpack` meshopt compression hook.
- `build.build_scene` end-to-end orchestrator (layer-tolerant) + `geoscena` CLI (`build`, `info`).

[0.01.000]: https://github.com/fsantibanezleal/CAOS_GeoScena/releases/tag/v0.01.000
