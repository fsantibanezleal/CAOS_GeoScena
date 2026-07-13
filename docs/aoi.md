# The AOI and its local metric frame

An **Area of Interest (AOI)** is the unit geoscena reconstructs: a small patch of the world (a few
kilometres square) defined either by a WGS84 centre + half-size in metres, or by an explicit bbox.

```python
from geoscena.aoi import AOI
AOI.from_center("Santiago Centro", lon=-70.650, lat=-33.437, half_size_m=1400)
AOI("Custom", west=..., south=..., east=..., north=...)
```

## The local projection

Every AOI exposes a **local Azimuthal Equidistant (AEQD)** projection centred on the AOI centroid.
All downstream layers are expressed in this frame, in metres, with the origin (0, 0) at the centroid.

- **Why AEQD:** it preserves distance from the centre and, over the few-kilometre extents geoscena
  targets, distortion is well under a metre. The renderer works directly in metres, Y-up, with no
  geographic math.
- `aoi.to_local(lon, lat) -> (x_east, y_north)` projects arrays.
- `aoi.transformer_to_local()` gives a `pyproj.Transformer` (use `direction="INVERSE"` to go back).
- `aoi.crs_local` is a PROJ string suitable for `GeoDataFrame.to_crs`.
- `aoi.size_m()` returns the approximate (width, height) in metres.

## On export

The glTF writer converts the local frame once to glTF's right-handed Y-up convention
(`glTF = (east, up, -north)`), so every `.glb` in a bundle shares one consistent orientation and a
Three.js scene loads them without per-app fix-up.
