# Source: OpenStreetMap context (water / green / rail)

**Role in geoscena:** the softer context layers where Overture is not the best fit.

## What it is

OpenStreetMap is the community map database. geoscena pulls three AOI-scoped context layers via OSMnx
(the Overpass API), which is ideal for small areas with flexible geometry selectors:

- **water**: `natural=water`, `water=*`, `waterway=riverbank|dock` -> flat draped surfaces.
- **green**: `leisure=park|garden|pitch`, `landuse=grass|forest|meadow`, `natural=wood|scrub`.
- **rail**: `railway=rail|light_rail|subway|tram` -> distinct ribbons.

Buildings and roads come from Overture (which already conflates OSM at priority 1), so OSM here is
only for the context layers Overture does not model as cleanly.

## Access

`osmnx.features_from_bbox(bbox, tags)` over Overpass. Optional dependency
(`pip install 'geoscena[osm]'`). Empty results (no water in the AOI) yield an empty layer, not an
error.

## License

ODbL. Attribution required; derived databases stay share-alike.

## References

- OSMnx: https://osmnx.readthedocs.io/
- OSM: https://www.openstreetmap.org/copyright
