"""Convert vector and raster files to MBTiles with the ``gdal`` CLI."""

import math
from collections.abc import Sequence
from pathlib import Path

from ._gdal import run_gdal

# Web Mercator resolution (metres per pixel) of a 256 px tile at zoom 0.
_ZOOM_0_RESOLUTION = 2 * math.pi * 6378137 / 256
# Web Mercator extent in degrees; it stops at about 85.05 degrees of latitude.
_WEB_MERCATOR_BBOX = "-180,-85.0511287798066,180,85.0511287798066"


def vector_to_mbtiles(
    input_path: Path,
    output_path: Path,
    min_zoom: int = 0,
    max_zoom: int = 12,
    fields: Sequence[str] | None = None,
    open_options: Sequence[str] = (),
) -> Path:
    """Convert any OGR-readable vector file (GeoJSON, GPKG, SHP, ...) to MBTiles.

    Features are clipped to the Web Mercator latitude limits (vertices beyond them cannot be
    projected), invalid geometries are repaired, and tiles are kept under GDAL's default
    500 KB, which is also the Mapbox limit. The tile layer is named after ``output_path``.
    An existing ``output_path`` is replaced.

    Args:
        input_path: Vector file to convert.
        output_path: Destination ``.mbtiles`` file.
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.
        fields: Attributes to keep. ``None`` keeps all of them.
        open_options: GDAL open options for the input, e.g. ``"ENCODING=ISO-8859-1"``.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    steps = ["!", "read", str(input_path)]
    for option in open_options:
        steps += ["--oo", option]
    steps += [
        "!", "clip", "--bbox", _WEB_MERCATOR_BBOX, "--bbox-crs", "EPSG:4326",
        "!", "make-valid", "--method", "structure",
    ]  # fmt: skip
    if fields:
        # `select` drops the geometry unless it is listed; this alias works for any format.
        steps += ["!", "select", "--fields", ",".join([*fields, "_ogr_geometry_"])]
    steps += [
        "!", "write", str(output_path), "--of", "MBTiles", "--overwrite",
        "--output-layer", output_path.stem,
        "--co", f"MINZOOM={min_zoom}",
        "--co", f"MAXZOOM={max_zoom}",
    ]  # fmt: skip
    run_gdal("vector", "pipeline", "--quiet", *steps)
    return output_path


def raster_to_mbtiles(
    input_path: Path,
    output_path: Path,
    max_zoom: int,
    min_zoom: int = 0,
    color_map: Path | None = None,
    tile_format: str = "PNG",
    resampling: str = "average",
) -> Path:
    """Tile a raster into an MBTiles file ready to upload to Mapbox.

    The raster is reprojected to Web Mercator at the resolution of ``max_zoom``, optionally
    coloured, and written as image tiles. Lower zooms down to ``min_zoom`` are then built as
    overviews. Zooms below the level where the raster fits in a single tile are not created.

    Args:
        input_path: Raster to tile.
        output_path: Destination ``.mbtiles`` file. An existing file is replaced.
        max_zoom: Highest zoom level, which sets the output resolution.
        min_zoom: Lowest zoom level to build.
        color_map: GDAL color map text file (``value R G B [A]`` lines, ``nv`` for nodata).
            Required unless the input is already 8-bit gray, RGB(A) or paletted.
        tile_format: ``PNG``, ``PNG8``, ``WEBP`` or ``JPEG``.
        resampling: Resampling method for the reprojection and the overviews. Use
            ``nearest`` or ``mode`` for categorical data.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolution = _ZOOM_0_RESOLUTION / 2**max_zoom

    steps = [
        "!", "read", str(input_path),
        "!", "reproject", "--dst-crs", "EPSG:3857",
        "--resolution", f"{resolution},{resolution}", "-r", resampling,
    ]  # fmt: skip
    if color_map:
        steps += ["!", "color-map", "--color-map", str(color_map), "--add-alpha"]
    steps += [
        "!", "write", str(output_path), "--of", "MBTiles", "--overwrite",
        "--co", f"TILE_FORMAT={tile_format}",
    ]  # fmt: skip
    run_gdal("raster", "pipeline", "--quiet", *steps)

    levels = [arg for i in range(1, max_zoom - min_zoom + 1) for arg in ("--levels", str(2**i))]
    if levels:
        run_gdal(
            "raster", "overview", "add", "--quiet", str(output_path), "-r", resampling, *levels
        )
    return output_path
