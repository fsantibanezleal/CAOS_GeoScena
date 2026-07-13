# The SceneBundle contract (processing -> web)

A `SceneBundle` is the product-agnostic hand-off between geoscena and any renderer. On disk it is a
directory:

```
<place>/
  manifest.json      # this contract
  terrain.glb        # one .glb per layer, AOI-local metres, Y-up
  buildings.glb
  roads.glb
  water.glb  green.glb  rail.glb  ...
```

## `manifest.json` schema

```jsonc
{
  "schema_version": 1,
  "aoi": {
    "name": "Berlin Mitte",
    "bbox_wgs84": [w, s, e, n],
    "origin_wgs84": [lon0, lat0],   // the local frame origin (0,0 in metres)
    "crs_local": "+proj=aeqd ...",
    "size_m": [width_m, height_m]
  },
  "layers": [
    {
      "name": "buildings",
      "file": "buildings.glb",
      "stats": { "kind": "mesh", "vertices": N, "triangles": M, "features": F },
      "provenance": {
        "source": "Overture Maps buildings",
        "url": "s3://...",
        "license": "ODbL-1.0",
        "license_name": "Open Data Commons Open Database License v1.0",
        "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "commercial_ok": true,
        "fetched": "2026-07-12",
        "method": "DuckDB spatial bbox-filtered read of GeoParquet on S3",
        "extra": { "release": "...", "n_buildings": N }
      }
    }
  ],
  "stats": { "height_mix": { "measured": .., "floors": .., "raster": .., "prior": .. }, "budgets": {..}, "notes": [..] },
  "any_noncommercial": false,
  "credits": ["Overture Maps buildings (ODbL ...)", "Copernicus GLO-30 DSM (...)", ...]
}
```

## Rules

- **Every layer has provenance.** A layer without a `LayerProvenance` cannot be added.
- **Local metres, Y-up.** All geometry is in the AOI local frame; the glTF writer applies the single
  Y-up conversion. A renderer places layers directly with no projection.
- **Per-feature extras.** Building `features` (height, source, class) ride in the glTF node `extras`
  so the viewer resolves a picked triangle to its building attributes.
- **A TypeScript mirror** of this manifest lives in the consuming product (`contract.types.ts`); any
  drift fails the product's web build.
