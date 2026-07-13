# Source: Overture Maps buildings + roads

**Role in geoscena:** the primary building-footprint and road source.

## What it is

Overture Maps is a conflated, schema-harmonized map dataset. Its **buildings** theme merges eight
sources by priority: OpenStreetMap (priority 1, ~703M buildings), Esri Community Maps, national
mapping agencies (e.g. Spanish IGN), municipal data, and Google + Microsoft ML roofprints (~1.58B
combined), for ~2.5B+ features. Community-contributed data outranks ML data in the conflation. The
schema carries `height` (m, lowest to highest point), `num_floors`, `min_height`, `roof_height`
where any contributing source provides them. The **transportation** theme carries road/rail segments
with a `class` (motorway/primary/residential/...) and `subtype`.

## Access

GeoParquet on the public S3 bucket `overturemaps-us-west-2`, partitioned by theme/type:
`s3://overturemaps-us-west-2/release/<RELEASE>/theme=buildings/type=building/*`. geoscena queries it
in place with DuckDB's `spatial` + `httpfs` extensions, filtering on the parquet `bbox` struct
(`bbox.xmin <= east AND bbox.xmax >= west AND ...`) so only the AOI's rows are materialized. Releases
are published roughly monthly; bump `geoscena.fetch.overture.DEFAULT_RELEASE` to the latest folder.

## License

**ODbL** (Open Database License), inherited from OpenStreetMap's primary contribution. Derived
databases (our baked bundles) stay ODbL-attributed; produced renderings need attribution. Commercial
use is permitted under ODbL terms.

## Height provenance

Overture's `height`/`num_floors` feed the top rungs of the geoscena height-provenance ladder (see
[methods/height-ladder.md](../methods/height-ladder.md)). Where both are null, lower rungs (height
raster, prior) take over, and the ladder records which rung was used per building.

## References

- Overture buildings guide: https://docs.overturemaps.org/guides/buildings/
- Getting data (CLI + S3): https://docs.overturemaps.org/getting-data/
