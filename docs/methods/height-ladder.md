# Method: the height-provenance ladder

**Problem.** Not every building carries a measured height. If we silently guessed one number per
building, the scene would look confident and be partly fiction. Instead geoscena resolves each
building's height from the best available source and *records which source was used*, so the product
can report the provenance mix honestly.

## The ladder (best first)

For each footprint, the first rung that yields a positive value wins:

| Rung | Tag | Source | Rule |
|---|---|---|---|
| 1 | `measured` | Overture/OSM `height` | use it directly |
| 2 | `floors` | Overture/OSM `num_floors` | `num_floors x floor_height` (default 3.2 m) |
| 3 | `raster` | Google Open Buildings 2.5D height raster (where covered) | sampled at the footprint |
| 4 | `prior` | land-use / default | a documented fallback (default 8 m) |

Heights are clipped to a minimum (2.5 m). The function returns, per building, `height_m` and
`height_source`, plus a `mix` count `{measured, floors, raster, prior}` baked into the bundle stats.

## Why this matters

- **Honesty.** The Benchmark surface shows the mix per place, so a viewer sees that (say) Santiago is
  60% raster-inferred while Berlin is 85% measured. The two are not presented as equally certain.
- **Regional reality.** In OSM-rich cities rung 1-2 dominate; in much of the Global South rungs 1-2
  are sparse and rung 3 (Open Buildings 2.5D, which covers Latin America, Africa, South/SE Asia)
  carries the scene. The ladder degrades gracefully rather than failing.
- **Auditability.** Every building's height traces to a named rung; nothing is an unlabeled guess.

## Parameters

`assign_heights(buildings, raster_heights=None, floor_height_m=3.2, prior_m=8.0)` in
`geoscena.fuse.heights`. Floor height and prior can be tuned per region (a per-country floor-height
table is a natural extension).

## References

- Google Open Buildings 2.5D Temporal (height raster, CC-BY-4.0 + ODbL, Global South):
  https://sites.research.google/gr/open-buildings/temporal/
- GHS-OBAT modelled heights (fallback candidate): https://gee-community-catalog.org/projects/ghs_obat/
