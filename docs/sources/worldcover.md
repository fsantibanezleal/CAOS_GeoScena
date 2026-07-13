# Source: ESA WorldCover 10 m (land cover)

**Role in geoscena:** land-cover classes to tint the scene and label terrain/building zones.

## What it is

ESA WorldCover is a global land-cover map at 10 m resolution derived from Copernicus Sentinel-1 and
Sentinel-2, with 11 classes (tree cover, shrubland, grassland, cropland, built-up, bare/sparse,
snow/ice, permanent water, herbaceous wetland, mangroves, moss/lichen). geoscena uses the v200 (2021)
product and its official legend colours.

## Access

Cloud-Optimized GeoTIFF on AWS Open Data bucket `esa-worldcover`, tiled 3x3 degrees on a
multiple-of-3 grid, named by SW corner: `v200/2021/map/ESA_WorldCover_10m_2021_v200_{N|S}LL{E|W}LLL_Map.tif`.
geoscena reads them keyless via GDAL `/vsicurl`, nearest-neighbour reprojected onto a ~10 m grid over
the AOI, then samples the class per building/terrain point.

## License

CC-BY 4.0, provided free of charge without restriction of use (commercial permitted, attribution).

## References

- Data access: https://esa-worldcover.org/en/data-access
- AWS registry: https://registry.opendata.aws/esa-worldcover-vito/
