"""Convert vector files to MBTiles with GDAL's ``ogr2ogr``."""

import subprocess
from pathlib import Path


def vector_to_mbtiles(
    input_path: Path,
    output_path: Path,
    min_zoom: int = 0,
    max_zoom: int = 12,
) -> Path:
    """Convert any OGR-readable vector file (GeoJSON, GPKG, SHP, ...) to MBTiles.

    An existing ``output_path`` is replaced, since the MBTiles driver refuses to overwrite.

    Args:
        input_path: Vector file to convert.
        output_path: Destination ``.mbtiles`` file.
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        RuntimeError: If ``ogr2ogr`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    command = [
        "ogr2ogr",
        "-f",
        "MBTiles",
        "-dsco",
        f"MINZOOM={min_zoom}",
        "-dsco",
        f"MAXZOOM={max_zoom}",
        "-dsco",
        "MAX_SIZE=10000000",
        "-makevalid",
        output_path.as_posix(),
        input_path.as_posix(),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ogr2ogr failed converting {input_path}: {e.stderr}") from e
    return output_path
