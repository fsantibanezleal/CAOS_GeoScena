# Method: meshing (terrain, buildings, roads, surfaces)

All meshing happens in the **AOI local metric frame** (x=east, y=north, z=up, metres). On glTF
export the writer converts once to Y-up (`glTF = (east, up, -north)`) so a renderer needs no geo-math.

## Terrain: adaptive TIN (Delatin-style)

The DEM grid is turned into an adaptive triangulated irregular network: dense where the terrain is
complex, sparse where it is flat. geoscena implements the Delatin idea (greedy error-driven
refinement) in **pure Python over `scipy.spatial.Delaunay`** so no native compiler is needed:

1. Seed with the grid corners + a few mid/centre points.
2. Re-triangulate; interpolate the current TIN onto every grid point; measure vertical error.
3. Insert a *spatially separated batch* of the highest-error points (not one per rebuild).
4. Repeat until the worst error drops below `max_error_m` or the vertex budget is hit.

Batching cuts the number of triangulations from thousands (naive one-point-per-rebuild) to a few
dozen, so it scales across many AOIs while keeping adaptive quality. Delatin-style meshes carry far
fewer triangles than a full-resolution grid for the same fidelity.

## Buildings: extruded prisms

Each footprint is projected to local metres, the roof polygon is triangulated with `mapbox_earcut`
(ear-cutting, handles concave footprints), and the polygon is extruded from a **terrain-sampled base
elevation** up to `base + height` to form a closed prism (roof cap + vertical walls). Per-vertex
colour encodes normalized height (a blue-to-amber ramp, the inspiration's height colouring); each
building's `{height_m, height_source, class}` is attached to the glTF node `extras` so the viewer can
show a value read-out on pick.

## Roads / rail: draped ribbons

Line segments are buffered by a class-dependent half-width into ribbon polygons, triangulated, and
placed at the terrain elevation plus a small offset so they read as lit surfaces on the ground (the
viewer applies the "neon" material). Rail is styled distinctly from roads.

## Water / green: flat draped surfaces

Polygon layers are triangulated and draped flat on the terrain with a small z-offset.

## Budgets

Every layer reports vertices/triangles/features in the manifest. The consuming product enforces a
per-place bundle-size budget after glTF compression (`gltfpack` meshopt / Draco), with the 3D Tiles
path documented as the escape hatch if a place outgrows single-GLB layers.
