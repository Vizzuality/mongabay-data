"""Shade elevation rasters into transparent hillshade tiles with the ``gdal`` CLI and numpy."""

import io
import math
import sqlite3
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from ._gdal import run_gdal

# Pixel size of the tiles; Mapbox serves them at 256 px and at 512 px for high-DPI screens.
TILE_SIZE = 512
# Earth radius of Web Mercator, and half the width of its square, in metres.
_RADIUS = 6378137
_WEB_MERCATOR_HALF = math.pi * _RADIUS
# Light from the north-west, 45 degrees above the horizon, as on most shaded relief maps.
_AZIMUTH = math.radians(315)
_ALTITUDE = math.radians(45)


def dem_to_hillshade(
    dem_paths: Sequence[Path],
    output_path: Path,
    max_zoom: int,
    min_zoom: int = 0,
    max_height: float | None = None,
    exaggeration: float = 1.0,
    workers: int = 4,
) -> Path:
    """Shade elevation rasters into an MBTiles of transparent PNGs ready to upload to Mapbox.

    Slopes facing away from the light are black and slopes facing it are white, each more
    opaque the steeper they are. Flat ground is transparent, so the tiles shade any colour
    below them. Each zoom is shaded from the source resampled to that zoom, so relief stays
    visible when zoomed out. ``output_path`` only appears once complete; an existing one is
    replaced.

    Args:
        dem_paths: Elevation rasters in metres, mosaicked together.
        output_path: Destination ``.mbtiles`` file.
        max_zoom: Highest zoom level to build, in 512 px tiles.
        min_zoom: Lowest zoom level to build.
        max_height: Heights above it are flattened and left transparent, such as 0 to shade
            only the seafloor. Tiles that are entirely above it are left out.
        exaggeration: Vertical exaggeration at ``max_zoom``. It doubles every two zooms out,
            because the same relief spans fewer, larger pixels there.
        workers: Number of tile rows processed at the same time.

    Returns:
        The path of the generated MBTiles file.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_path.parent) as tmp:
        dem = Path(tmp) / "dem.vrt"
        # Tiles of one grid can differ in resolution by rounding noise, which "same" rejects.
        run_gdal(
            "raster", "mosaic", "--quiet", "--resolution", "highest", "--absolute-path",
            *map(str, dem_paths), str(dem),
        )  # fmt: skip
        mbtiles = Path(tmp) / "hillshade.mbtiles"
        db = _create_mbtiles(mbtiles, output_path.stem, min_zoom, max_zoom)
        for zoom in range(min_zoom, max_zoom + 1):
            zoom_exaggeration = exaggeration * 2 ** ((max_zoom - zoom) / 2)
            with ThreadPoolExecutor(workers) as pool:
                for tiles in pool.map(
                    lambda row, zoom=zoom, z=zoom_exaggeration: _shade_row(
                        dem, zoom, row, max_height, z, Path(tmp)
                    ),
                    range(2**zoom),
                ):
                    db.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", tiles)
                    db.commit()
        db.close()
        # Moved into place only once complete, so a present file is always a finished one.
        mbtiles.replace(output_path)
    return output_path


def _shade_row(
    dem: Path, zoom: int, row: int, max_height: float | None, exaggeration: float, tmp: Path
) -> list[tuple[int, int, int, bytes]]:
    """Resample one row of tiles from ``dem`` and shade its tiles."""
    count = 2**zoom
    tile_metres = 2 * _WEB_MERCATOR_HALF / count
    pixel = tile_metres / TILE_SIZE
    top = _WEB_MERCATOR_HALF - row * tile_metres
    # One extra pixel above and below, so slopes at the tile edges match their neighbours.
    strip = tmp / f"z{zoom}_{row}.bin"
    run_gdal(
        "raster", "pipeline", "--quiet",
        "!", "read", str(dem),
        "!", "set-type", "--ot", "Float32",
        "!", "reproject", "--dst-crs", "EPSG:3857", "-r", "bilinear",
        "--bbox",
        f"{-_WEB_MERCATOR_HALF},{top - tile_metres - pixel},{_WEB_MERCATOR_HALF},{top + pixel}",
        "--size", f"{TILE_SIZE * count},{TILE_SIZE + 2}",
        "!", "write", str(strip), "--of", "ENVI", "--overwrite",
    )  # fmt: skip
    heights = np.fromfile(strip, dtype="<f4").reshape(TILE_SIZE + 2, TILE_SIZE * count)
    for path in tmp.glob(f"{strip.stem}.*"):
        path.unlink()

    flat = np.zeros_like(heights, dtype=bool)
    if max_height is not None:
        flat = heights >= max_height
        heights = np.minimum(heights, max_height)
    # Web Mercator stretches distances by 1 / cos(latitude); shade with true ground distances.
    y = top + pixel / 2 - pixel * np.arange(-1, TILE_SIZE + 1)
    ground = pixel * np.cos(np.arctan(np.sinh(y / _RADIUS)))[:, None]
    shading = _shade(heights, ground, exaggeration)[1:-1]
    flat = flat[1:-1]

    tiles = []
    for col in range(count):
        cols = slice(col * TILE_SIZE, (col + 1) * TILE_SIZE)
        if flat[:, cols].all():
            continue
        tile = np.where(flat[:, cols, None], 0, shading[:, cols])
        png = io.BytesIO()
        Image.fromarray(tile.astype(np.uint8), "RGBA").save(png, "PNG", optimize=True)
        # MBTiles numbers rows from the bottom.
        tiles.append((zoom, col, count - 1 - row, png.getvalue()))
    return tiles


def _shade(heights: np.ndarray, ground: np.ndarray, exaggeration: float) -> np.ndarray:
    """Shade heights into RGBA: black shadows and white highlights over transparency."""
    dz_south, dz_east = np.gradient(heights * exaggeration)
    dz_dx = dz_east / ground
    dz_dy = -dz_south / ground  # rows run south, so flip to get the slope towards the north
    # Lambertian reflectance: the cosine between the surface normal and the light.
    light = (
        math.sin(_ALTITUDE)
        - dz_dx * math.cos(_ALTITUDE) * math.sin(_AZIMUTH)
        - dz_dy * math.cos(_ALTITUDE) * math.cos(_AZIMUTH)
    ) / np.sqrt(1 + dz_dx**2 + dz_dy**2)
    light = np.clip(light, 0, 1)
    flat = math.sin(_ALTITUDE)
    shadow = np.clip((flat - light) / flat, 0, 1)
    highlight = np.clip((light - flat) / (1 - flat), 0, 1)
    white = highlight > shadow
    rgba = np.zeros((*heights.shape, 4))
    rgba[..., :3] = np.where(white, 255, 0)[..., None]
    rgba[..., 3] = np.rint(255 * np.maximum(shadow, highlight))
    return rgba


def _create_mbtiles(path: Path, name: str, min_zoom: int, max_zoom: int) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    db.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER,"
        " tile_data BLOB, PRIMARY KEY (zoom_level, tile_column, tile_row))"
    )
    metadata = {
        "name": name,
        "format": "png",
        "type": "overlay",
        "minzoom": str(min_zoom),
        "maxzoom": str(max_zoom),
        "bounds": "-180,-85.0511287798066,180,85.0511287798066",
    }
    db.executemany("INSERT INTO metadata VALUES (?, ?)", metadata.items())
    return db
