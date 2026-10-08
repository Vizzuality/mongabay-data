"""Layers built by classifying tiled rasters into polygons, like Mapbox's landcover."""

import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from rich import get_console

from ..config import MBTILES_DIR
from ..config import POLYGONS_DIR
from ..converters.mbtiles import merge_mbtiles
from ..converters.mbtiles import vector_to_mbtiles
from ..converters.polygons import classify_to_polygons
from ..converters.polygons import resample
from ..converters.polygons import unset_nodata
from ..download import download_file
from .base import Layer
from .sources import TileIndex


@dataclass(frozen=True, kw_only=True)
class ZoomBand:
    """Zoom levels drawn from one generalisation of a classified raster.

    Attributes:
        min_zoom: Lowest zoom level of the band.
        max_zoom: Highest zoom level of the band.
        resolution: Cell size the raster is resampled to before classifying, in degrees.
        sieve: Merge patches smaller than this many cells into their neighbours.
    """

    min_zoom: int
    max_zoom: int
    resolution: float
    sieve: int = 0

    @property
    def name(self) -> str:
        """Zooms and settings, so polygons made with other settings are never reused."""
        return f"z{self.min_zoom}-{self.max_zoom}_{self.resolution:g}deg_sieve{self.sieve}"

    def needs_full_resolution(self, coarse_resolution: float) -> bool:
        """Whether the band is finer than the coarse copies, so needs the source tile."""
        return self.resolution < coarse_resolution


@dataclass(frozen=True, kw_only=True)
class PolygonStore:
    """Where a classified layer keeps its polygons and coarse tile copies between runs.

    Each band has a folder with one GeoPackage per source tile, or an ``.empty`` marker when
    the tile has no polygon in that band, such as open ocean.

    Attributes:
        root: Folder of the layer's files.
        coarse_resolution: Cell size of the coarse copies, in degrees.
    """

    root: Path
    coarse_resolution: float

    @property
    def coarse_dir(self) -> Path:
        return self.root / f"coarse_{self.coarse_resolution:g}deg"

    def coarse(self, tile: str) -> Path:
        return self.coarse_dir / f"{tile}.tif"

    def polygons(self, band: ZoomBand, tile: str) -> Path:
        return self.root / band.name / f"{tile}.gpkg"

    def is_done(self, band: ZoomBand, tile: str) -> bool:
        path = self.polygons(band, tile)
        return path.exists() or path.with_suffix(".empty").exists()

    def mark_empty(self, band: ZoomBand, tile: str) -> None:
        self.polygons(band, tile).with_suffix(".empty").touch()

    def band_files(self, band: ZoomBand) -> list[Path]:
        return sorted((self.root / band.name).glob("*.gpkg"))

    def clear_polygons(self) -> None:
        """Delete the polygons of every band, keeping the coarse copies."""
        for path in self.root.iterdir():
            if path != self.coarse_dir:
                shutil.rmtree(path)

    def clear(self) -> None:
        """Delete everything, coarse copies included."""
        shutil.rmtree(self.root, ignore_errors=True)


@dataclass(frozen=True, kw_only=True)
class ClassifiedRasterLayer(Layer):
    """A tiled raster classified into value bins and published as polygons.

    Each source tile is downloaded, polygonized once per zoom band and deleted, by
    ``workers`` tiles at a time, so the full raster is never on disk. Tiles already
    polygonized are skipped, so an interrupted run resumes where it stopped. Each polygon
    gets ``level``, the lower bound of its bin, and ``class``, the bin's label. The polygons
    are deleted once the MBTiles is built.

    A copy of each tile averaged to ``coarse_resolution`` is kept. Bands at that resolution
    or coarser are polygonized from it, so changing their settings needs no new download.

    Attributes:
        index: List of the raster's tiles.
        classes: ``(level, label)`` pairs in ascending order. Each bin runs from its level up
            to the next one; values below the first level are left out.
        max_value: Upper bound of the last bin.
        bands: Zoom bands, each with its own resampling and sieve, covering every zoom
            level once.
        workers: Number of tiles processed at the same time.
        coarse_resolution: Cell size of the kept copies, in degrees. Band resolutions from
            it up should be whole multiples of it.
    """

    index: TileIndex
    classes: tuple[tuple[int, str], ...]
    max_value: float
    bands: tuple[ZoomBand, ...]
    workers: int = 4
    coarse_resolution: float = 0.004

    @property
    def store(self) -> PolygonStore:
        return PolygonStore(root=POLYGONS_DIR / self.name, coarse_resolution=self.coarse_resolution)

    def build(self, refresh: bool = False) -> Path:
        if refresh:
            self.store.clear()
        self._polygonize_all(self.index.tile_urls())
        mbtiles = self._tile_bands()
        self.store.clear_polygons()
        return mbtiles

    def _polygonize_all(self, tiles: dict[str, str]) -> None:
        """Polygonize every tile in parallel, then report all the tiles that failed."""
        get_console().print(f"Polygonizing {len(tiles)} tiles, {self.workers} at a time")
        with ThreadPoolExecutor(self.workers) as pool:
            futures = {
                tile: pool.submit(self._polygonize_tile, tile, url) for tile, url in tiles.items()
            }
        errors = {tile: error for tile, future in futures.items() if (error := future.exception())}
        for tile, error in errors.items():
            get_console().print(f"[red]{tile} failed: {error}")
        if errors:
            raise RuntimeError(f"{len(errors)} tiles failed; run again to retry only those")

    def _polygonize_tile(self, tile: str, url: str) -> None:
        missing = [band for band in self.bands if not self.store.is_done(band, tile)]
        if not missing:
            return
        coarse = self.store.coarse(tile)
        needs_source = any(band.needs_full_resolution(self.coarse_resolution) for band in missing)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.raw_dir) as tmp:
            if needs_source or not coarse.exists():
                raster = download_file(url, Path(tmp) / f"{tile}.tif")
                # Nodata means no trees here: count it as 0 when averaging into coarse cells.
                unset_nodata(raster)
                if not coarse.exists():
                    # Moved into place only once complete, like the polygons.
                    resample(raster, Path(tmp) / "coarse.tif", self.coarse_resolution)
                    coarse.parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / "coarse.tif").replace(coarse)
            for band in missing:
                fine = band.needs_full_resolution(self.coarse_resolution)
                self._polygonize_band(raster if fine else coarse, band, tile)
        get_console().print(f"Polygonized {tile}")

    def _polygonize_band(self, raster: Path, band: ZoomBand, tile: str) -> None:
        polygons = classify_to_polygons(
            raster,
            self.store.polygons(band, tile),
            layer=self.name,
            classes=self.classes,
            max_value=self.max_value,
            resolution=band.resolution,
            sieve=band.sieve,
        )
        if polygons is None:
            self.store.mark_empty(band, tile)

    def _tile_bands(self) -> Path:
        """Tile every band in parallel and merge them into ``mbtiles_path``."""
        MBTILES_DIR.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory(dir=MBTILES_DIR) as tmp,
            ThreadPoolExecutor(len(self.bands)) as pool,
        ):
            bands = list(pool.map(lambda band: self._tile_band(band, Path(tmp)), self.bands))
            return merge_mbtiles(bands, self.mbtiles_path)

    def _tile_band(self, band: ZoomBand, dest: Path) -> Path:
        get_console().print(f"Tiling {band.name}")
        return vector_to_mbtiles(
            self.store.band_files(band),
            dest / f"{band.name}.mbtiles",
            min_zoom=band.min_zoom,
            max_zoom=band.max_zoom,
            layer_name=self.name,
        )
