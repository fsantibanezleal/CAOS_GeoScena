# Contributing to geoscena

Thanks for your interest. geoscena is the fusion/meshing core behind Maqueta.

## Development

```bash
python -m venv .venv && . .venv/Scripts/activate   # or bin/activate
pip install -e '.[dev,overture,osm]'
pytest            # offline tests (no network) must pass
ruff check .
```

## Ground rules

- **English only** in code, comments, docs, commits. No em-dash, no emoji in content.
- **Provenance is mandatory.** Any new fetcher must return a `LayerProvenance` (source, URL,
  license key, fetch date, method). Add the license to `provenance.LICENSES` if new.
- **No native compiler dependency in the core.** Heavy/optional engines go under an extra.
- **Determinism.** Fetch dates are passed in, never auto-stamped, so builds are reproducible.
- Branch flow `task/<slug> -> develop -> main`; PR at each level; version `X.XX.XXX` + a tag per
  release; update `CHANGELOG.md`.

## Adding a source

1. Add `fetch/<source>.py` returning geometry/raster + a `LayerProvenance`.
2. Wire it into `build.build_scene` behind a config flag (layer-tolerant: skip, do not fail).
3. Add an offline unit test (mock or synthetic) and a `docs/sources/<source>.md` card.
