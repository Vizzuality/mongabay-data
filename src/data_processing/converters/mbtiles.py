"""Convert vector and raster files to MBTiles with the ``gdal`` CLI."""

import json
import math
import shutil
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from ._gdal import run_gdal

# Web Mercator resolution (metres per pixel) of a 256 px tile at zoom 0.
_ZOOM_0_RESOLUTION = 2 * math.pi * 6378137 / 256
# Web Mercator extent in degrees; it stops at about 85.05 degrees of latitude.
_WEB_MERCATOR_BBOX = "-180,-85.0511287798066,180,85.0511287798066"


def vector_to_mbtiles(
    input_paths: Sequence[Path],
    output_path: Path,
    min_zoom: int = 0,
    max_zoom: int = 12,
    fields: Sequence[str] | None = None,
    where: str | None = None,
    labels: Sequence[str] | None = None,
    open_options: Sequence[str] = (),
    layer_name: str | None = None,
) -> Path:
    """Convert one or more OGR-readable vector files (GeoJSON, GPKG, SHP, ...) to MBTiles.

    Several inputs are merged into a single tile layer, named after ``output_path`` unless
    ``layer_name`` is given.
    Features are clipped to the Web Mercator latitude limits (vertices beyond them cannot be
    projected), invalid geometries are repaired, and tiles are kept under GDAL's default
    500 KB, which is also the Mapbox limit. An existing ``output_path`` is replaced.

    Args:
        input_paths: Vector files to convert.
        output_path: Destination ``.mbtiles`` file.
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.
        fields: Attributes to keep. ``None`` keeps all of them.
        where: Attribute filter, e.g. ``"STATUS = 'Designated'"``.
        labels: One value per input, written to a ``type`` attribute. List ``"type"`` in
            ``fields`` to keep it when selecting fields.
        open_options: GDAL open options, e.g. ``"ENCODING=ISO-8859-1"``. Only supported with
            a single input.
        layer_name: Name of the tile layer. Defaults to the stem of ``output_path``.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        ValueError: If ``labels`` does not match ``input_paths``, or ``open_options`` are
            given with several inputs.
        RuntimeError: If ``gdal`` fails.
    """
    if labels is not None and len(labels) != len(input_paths):
        raise ValueError("labels must have one value per input")
    if open_options and len(input_paths) > 1:
        raise ValueError("open_options are only supported with a single input")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    layer = layer_name or output_path.stem

    if len(input_paths) == 1 and labels is None:
        steps = ["!", "read", str(input_paths[0])]
        for option in open_options:
            steps += ["--oo", option]
    else:
        steps = ["!", "concat", "--mode", "single", "--output-layer", layer]
        if labels is not None:
            steps += [
                "--source-layer-field-name", "_source",
                "--source-layer-field-content", "{DS_INDEX}",
            ]  # fmt: skip
        steps += [str(path) for path in input_paths]
    if labels is not None:
        cases = " ".join(f"WHEN '{i}' THEN '{label}'" for i, label in enumerate(labels))
        statement = f'SELECT *, CASE _source {cases} END AS type FROM "{layer}"'
        steps += ["!", "sql", "--dialect", "SQLITE", statement]
    if where:
        steps += ["!", "filter", "--where", where]
    steps += [
        "!", "clip", "--bbox", _WEB_MERCATOR_BBOX, "--bbox-crs", "EPSG:4326",
        "!", "make-valid", "--method", "structure",
    ]  # fmt: skip
    if fields:
        # `select` drops the geometry unless it is listed; this alias works for any format.
        steps += ["!", "select", "--fields", ",".join([*fields, "_ogr_geometry_"])]
    steps += [
        "!", "write", str(output_path), "--of", "MBTiles", "--overwrite",
        "--output-layer", layer,
        "--co", f"MINZOOM={min_zoom}",
        "--co", f"MAXZOOM={max_zoom}",
    ]  # fmt: skip
    run_gdal("vector", "pipeline", "--quiet", *steps)
    return output_path


def merge_mbtiles(input_paths: Sequence[Path], output_path: Path) -> Path:
    """Merge MBTiles files that cover different zoom levels of the same layers into one.

    The first input is copied to ``output_path`` and the tiles of the others are added to it.
    The zoom range in the metadata is widened to cover all of them. An existing
    ``output_path`` is replaced.

    Args:
        input_paths: MBTiles files whose zoom levels do not overlap.
        output_path: Destination ``.mbtiles`` file.

    Returns:
        The path of the merged MBTiles file.

    Raises:
        sqlite3.IntegrityError: If two inputs have a tile at the same zoom, column and row.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_paths[0], output_path)
    with sqlite3.connect(output_path) as db:
        for path in input_paths[1:]:
            db.execute("ATTACH DATABASE ? AS other", (str(path),))
            db.execute("INSERT INTO tiles SELECT * FROM other.tiles")
            db.commit()
            db.execute("DETACH DATABASE other")
        min_zoom, max_zoom = db.execute(
            "SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles"
        ).fetchone()
        metadata = dict(db.execute("SELECT name, value FROM metadata"))
        updates = {"minzoom": str(min_zoom), "maxzoom": str(max_zoom)}
        if "json" in metadata:
            layers_json = json.loads(metadata["json"])
            for layer in layers_json.get("vector_layers", []):
                layer.update(minzoom=min_zoom, maxzoom=max_zoom)
            updates["json"] = json.dumps(layers_json)
        rows = [(value, name) for name, value in updates.items()]
        db.executemany("UPDATE metadata SET value = ? WHERE name = ?", rows)
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
