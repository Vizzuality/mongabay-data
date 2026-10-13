"""Encode raster values as grey levels in PNG tiles, for colour ramps in Mapbox Studio."""

import io
import math
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from ._gdal import run_gdal
from .mbtiles import TILE_SIZE
from .mbtiles import WEB_MERCATOR_HALF
from .mbtiles import create_mbtiles

# Tiles reprojected per gdal call, along each side: 16 x 16 tiles are 270 MB of Float32.
_BLOCK = 16


def raster_to_value_tiles(
    raster_paths: Sequence[Path],
    output_path: Path,
    min_zoom: int,
    max_zoom: int,
    scale: float = 1.0,
    workers: int = 4,
) -> Path:
    """Average rasters onto each zoom and store the values as grey levels in an MBTiles.

    Each pixel's grey level, from 1 to 255, is its value divided by ``scale``, rounded;
    values above ``255 * scale`` are capped. Pixels of value 0, or outside the rasters, are
    transparent, and tiles without any other pixel are left out. In Studio, a raster layer
    gets the values back with ``raster-color-mix`` and colours them with ``raster-color``.
    ``output_path`` only appears once complete; an existing one is replaced.

    Args:
        raster_paths: Single-band rasters in degrees (EPSG:4326), mosaicked together.
            Nodata is not skipped.
        output_path: Destination ``.mbtiles`` file.
        min_zoom: Lowest zoom level to build.
        max_zoom: Highest zoom level to build, in 512 px tiles.
        scale: Value of one grey level.
        workers: Number of blocks of tiles processed at the same time.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_path.parent) as tmp:
        raster = Path(tmp) / "raster.vrt"
        # Tiles of one grid can differ in resolution by rounding noise, which "same" rejects.
        run_gdal(
            "raster", "mosaic", "--quiet", "--resolution", "highest", "--absolute-path",
            *map(str, raster_paths), str(raster),
        )  # fmt: skip
        extents = _source_extents(raster)
        mbtiles = Path(tmp) / "values.mbtiles"
        db = create_mbtiles(mbtiles, output_path.stem, min_zoom, max_zoom)
        for zoom in range(min_zoom, max_zoom + 1):
            starts = range(0, 2**zoom, _BLOCK)
            # Blocks away from every raster would only be transparent: skip them.
            blocks = [
                (col, row)
                for row in starts
                for col in starts
                if _overlaps(_block_extent(zoom, col, row), extents)
            ]
            with ThreadPoolExecutor(workers) as pool:
                for tiles in pool.map(
                    lambda block, zoom=zoom: _encode_block(raster, zoom, *block, scale, Path(tmp)),
                    blocks,
                ):
                    db.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", tiles)
                    db.commit()
        db.close()
        # Moved into place only once complete, so a present file is always a finished one.
        mbtiles.replace(output_path)
    return output_path


def _source_extents(vrt: Path) -> list[tuple[float, float, float, float]]:
    """``(west, south, east, north)`` of each raster of a mosaic, from its VRT."""
    root = ET.parse(vrt).getroot()
    x0, dx, _, y0, _, dy = map(float, root.findtext("GeoTransform").split(","))
    extents = []
    for rect in root.iter("DstRect"):
        x, y, w, h = (float(rect.get(key)) for key in ("xOff", "yOff", "xSize", "ySize"))
        extents.append((x0 + x * dx, y0 + (y + h) * dy, x0 + (x + w) * dx, y0 + y * dy))
    return extents


def _block_extent(zoom: int, col: int, row: int) -> tuple[float, float, float, float]:
    """``(west, south, east, north)`` in degrees of the block of tiles at ``col``, ``row``."""
    count = 2**zoom
    size = min(_BLOCK, count)

    def lat(tile_row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * tile_row / count))))

    return (
        col / count * 360 - 180,
        lat(row + size),
        (col + size) / count * 360 - 180,
        lat(row),
    )


def _overlaps(
    extent: tuple[float, float, float, float], others: list[tuple[float, float, float, float]]
) -> bool:
    west, south, east, north = extent
    return any(w < east and e > west and s < north and n > south for w, s, e, n in others)


def _encode_block(
    raster: Path, zoom: int, col: int, row: int, scale: float, tmp: Path
) -> list[tuple[int, int, int, bytes]]:
    """Average one block of tiles from ``raster`` and encode its tiles."""
    count = 2**zoom
    size = min(_BLOCK, count)
    tile_metres = 2 * WEB_MERCATOR_HALF / count
    left = -WEB_MERCATOR_HALF + col * tile_metres
    top = WEB_MERCATOR_HALF - row * tile_metres
    grid = tmp / f"z{zoom}_{col}_{row}.bin"
    run_gdal(
        "raster", "pipeline", "--quiet",
        "!", "read", str(raster),
        "!", "set-type", "--ot", "Float32",
        "!", "reproject", "--dst-crs", "EPSG:3857", "-r", "average",
        "--bbox", f"{left},{top - size * tile_metres},{left + size * tile_metres},{top}",
        "--size", f"{TILE_SIZE * size},{TILE_SIZE * size}",
        "!", "write", str(grid), "--of", "ENVI", "--overwrite",
    )  # fmt: skip
    values = np.fromfile(grid, dtype="<f4").reshape(TILE_SIZE * size, TILE_SIZE * size)
    for path in tmp.glob(f"{grid.stem}.*"):
        path.unlink()

    # Any value above 0 stays visible, however small.
    grey = np.where(values > 0, np.clip(np.rint(values / scale), 1, 255), 0).astype(np.uint8)
    tiles = []
    for y in range(size):
        for x in range(size):
            tile = grey[y * TILE_SIZE : (y + 1) * TILE_SIZE, x * TILE_SIZE : (x + 1) * TILE_SIZE]
            if not tile.any():
                continue
            alpha = np.where(tile > 0, 255, 0).astype(np.uint8)
            png = io.BytesIO()
            Image.fromarray(np.dstack([tile, tile, tile, alpha]), "RGBA").save(
                png, "PNG", optimize=True
            )
            # MBTiles numbers rows from the bottom.
            tiles.append((zoom, col + x, count - 1 - (row + y), png.getvalue()))
    return tiles
