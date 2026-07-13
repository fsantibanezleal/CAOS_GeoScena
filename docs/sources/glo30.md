# Source: Copernicus GLO-30 DSM (terrain)

**Role in geoscena:** the default global terrain source.

## What it is

The Copernicus GLO-30 Digital Surface Model is a global 30 m elevation model derived from the
TanDEM-X mission. It is a **DSM** (Digital Surface Model): it represents the top reflective surface,
so it *includes* buildings and vegetation canopy. In dense urban cores this means the "ground" sits
slightly high under buildings; geoscena documents this as a caveat and, for ground-truth places,
compares against a lidar DTM to show the delta. GLO-30 outperforms SRTM/NASADEM/AW3D30 in
independent vertical-accuracy studies; FABDEM removes the building/tree bias but is CC-BY-NC-SA
(non-commercial), so geoscena keeps GLO-30 as the open default.

## Access

Cloud-Optimized GeoTIFF (COG) tiles on AWS Open Data bucket `copernicus-dem-30m`, one tile per
1x1 degree, named by SW integer corner: `Copernicus_DSM_COG_10_{N|S}LL_00_{E|W}LLL_00_DEM`. geoscena
reads them keyless over HTTPS via GDAL `/vsicurl`, windowed and bilinearly reprojected onto a ~1
arc-second grid over the AOI (with a small pad for edge triangles).

## License

Copernicus DEM free-of-charge license (ESA/DLR): free for the general public, attribution required,
commercial use permitted.

## References

- AWS Open Data registry: https://registry.opendata.aws/copernicus-dem/
- Vertical-accuracy comparison (FABDEM/GLO-30/NASADEM/AW3D30/SRTM): https://doi.org/10.1080/17538947.2024.2308734
