"""Run layer pipelines: ``python -m data_processing.pipelines <layer>... [--no-upload]``.

``--upload-only`` uploads the MBTiles built by an earlier run without tiling again.
"""

import argparse

from dotenv import load_dotenv

from .layers import LAYERS


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m data_processing.pipelines",
        description="Download, tile and upload layers to Mapbox.",
    )
    parser.add_argument("layers", nargs="*", choices=sorted(LAYERS), metavar="layer")
    parser.add_argument("--list", action="store_true", help="list the available layers")
    parser.add_argument("--no-upload", action="store_true", help="tile only, skip Mapbox")
    parser.add_argument("--refresh", action="store_true", help="download the source again")
    parser.add_argument(
        "--upload-only", action="store_true", help="upload the existing MBTiles, skip tiling"
    )
    args = parser.parse_args()

    if args.list or not args.layers:
        for name, layer in sorted(LAYERS.items()):
            print(f"{name}: {layer.title}")
        return

    load_dotenv()
    for name in args.layers:
        if args.upload_only:
            LAYERS[name].upload()
        else:
            LAYERS[name].run(upload=not args.no_upload, refresh=args.refresh)


if __name__ == "__main__":
    main()
