# Security Policy

`geoscena` is a data-processing library: it reads public open geodata and writes local mesh
files. It stores no secrets and opens no network listeners.

## Reporting a vulnerability

Email **fsantibanez@gmail.com** with details and reproduction steps. Please do not open a public
issue for a security report. You can expect an acknowledgement within a few days.

## Scope notes

- geoscena fetches from third-party public buckets/APIs (AWS Open Data, Overture S3, Overpass).
  It performs read-only requests and validates that returned rasters/vectors intersect the AOI.
- No credentials are required for the default sources; optional lidar/authenticated sources are
  configured by the caller and are out of this project's secret-handling scope.
