"""geoscena command-line interface.

Two subcommands:

    geoscena build --name "Berlin Mitte" --lon 13.405 --lat 52.517 --half 1200 \
        --fetched 2026-07-12 --out E:/_Datos/maqueta/bundles/berlin_mitte

    geoscena info    # print the known sources + licenses

The build command runs the full fetch -> fuse -> mesh pipeline and writes a SceneBundle
directory (per-layer .glb + manifest.json).
"""

from __future__ import annotations

import argparse
import json
import sys

from geoscena import __version__
from geoscena.aoi import AOI
from geoscena.build import BuildConfig, build_scene
from geoscena.provenance import LICENSES


def _cmd_build(args: argparse.Namespace) -> int:
    if args.bbox:
        w, s, e, n = args.bbox
        aoi = AOI(args.name, w, s, e, n)
    else:
        aoi = AOI.from_center(args.name, args.lon, args.lat, args.half)
    cfg = BuildConfig(
        fetched=args.fetched,
        terrain_max_error_m=args.terrain_error,
        terrain_max_vertices=args.terrain_vertices,
        include_buildings=not args.no_buildings,
        include_roads=not args.no_roads,
        include_context=not args.no_context,
        overture_release=args.release,
    )
    bundle = build_scene(aoi, cfg)
    out = bundle.write(args.out)
    print(f"wrote bundle -> {out}")
    print(json.dumps(bundle.stats, indent=2))
    return 0


def _cmd_info(_args: argparse.Namespace) -> int:
    print(f"geoscena {__version__}")
    print("Known licenses:")
    for key, rec in LICENSES.items():
        ok = rec.get("commercial_ok")
        print(f"  {key:20s} commercial_ok={ok}  {rec.get('url', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="geoscena", description=__doc__)
    p.add_argument("--version", action="version", version=f"geoscena {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a SceneBundle for an AOI")
    b.add_argument("--name", required=True)
    b.add_argument("--lon", type=float)
    b.add_argument("--lat", type=float)
    b.add_argument("--half", type=float, default=1200.0, help="half-size in metres")
    b.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    b.add_argument("--fetched", required=True, help="ISO date for provenance (e.g. 2026-07-12)")
    b.add_argument("--out", required=True)
    b.add_argument("--release", default=None, help="Overture release folder")
    b.add_argument("--terrain-error", type=float, default=1.5)
    b.add_argument("--terrain-vertices", type=int, default=6000)
    b.add_argument("--no-buildings", action="store_true")
    b.add_argument("--no-roads", action="store_true")
    b.add_argument("--no-context", action="store_true")
    b.set_defaults(func=_cmd_build)

    i = sub.add_parser("info", help="print known sources + licenses")
    i.set_defaults(func=_cmd_info)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
