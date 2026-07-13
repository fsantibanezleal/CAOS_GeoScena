# geoscena documentation

geoscena turns an Area of Interest into a fused, mesh-ready `SceneBundle` from open public
geodata, with per-layer provenance. This wiki documents the contracts, the sources, and the
fusion/meshing methods.

## Contents

- **[The SceneBundle contract](contract.md)** - the processing -> web hand-off (layers + manifest).
- **[The AOI + local projection](aoi.md)** - how areas are defined and projected to metres.
- **Sources** - one card per open dataset geoscena fetches:
  - [Overture buildings + roads](sources/overture.md) (ODbL)
  - [Copernicus GLO-30 terrain](sources/glo30.md) (Copernicus free)
  - [ESA WorldCover land cover](sources/worldcover.md) (CC-BY-4.0)
  - [OpenStreetMap context](sources/osm.md) (ODbL)
- **[The height-provenance ladder](methods/height-ladder.md)** - honest per-building heights.
- **[Meshing](methods/meshing.md)** - adaptive terrain TIN, extrusion, ribbons.

## Design principles

1. **Provenance is mandatory.** No layer without a source, URL, license and fetch date.
2. **Local metric frame.** Everything is expressed in AOI-local metres (Y-up on glTF export) so a
   renderer needs no geo-math.
3. **Layer tolerance.** A missing source (no buildings in a wilderness AOI) is recorded and skipped,
   never fatal; a city and a natural area build from the same call.
4. **No native compiler in the core.** The terrain TIN is pure-Python over SciPy; heavy engines
   (lidar) are optional extras.
5. **Determinism.** Fetch dates are inputs, not wall-clock, so a rebuild reproduces the manifest.
