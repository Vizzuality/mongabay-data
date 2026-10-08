"""Layer configs that know how to fetch, tile and upload themselves to Mapbox."""

import os
import shutil
import tempfile
import zipfile
from abc import ABC
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich.console import Console

from ..config import MBTILES_DIR
from ..config import POLYGONS_DIR
from ..config import RAW_DATA_DIR
from ..converters.mbtiles import merge_mbtiles
from ..converters.mbtiles import vector_to_mbtiles
from ..converters.polygons import classify_to_polygons
from ..converters.polygons import resample
from ..converters.polygons import unset_nodata
from ..download import download_file
from ..download import unzip
from ..mapbox import upload_tileset
from ..mapbox import validate_tileset_name

console = Console()


@dataclass(frozen=True, kw_only=True)
class Source:
    """A downloadable dataset and the files to read from it.

    Attributes:
        url: Where to download the data. Zip archives, and zips nested one level inside
            them, are extracted. Any other download is saved as ``files[0]``.
        files: Glob patterns of the files to read, relative to the extracted download.
        label: Value that identifies this source's features when a layer merges sources.
    """

    url: str
    files: tuple[str, ...]
    label: str | None = None

    def fetch(self, dest: Path, refresh: bool = False) -> list[Path]:
        """Download into ``dest`` unless already cached, and return the matching files."""
        if not refresh and all(any(dest.glob(pattern)) for pattern in self.files):
            console.print(f"Using cached {dest}")
            return self._match(dest)

        console.print(f"Downloading {self.url}")
        download = download_file(self.url, dest / "download")
        if zipfile.is_zipfile(download):
            unzip(download, dest)
            download.unlink()
            for nested in list(dest.rglob("*.zip")):
                unzip(nested)
                nested.unlink()
        else:
            download.replace(dest / self.files[0])
        return self._match(dest)

    def _match(self, dest: Path) -> list[Path]:
        paths = []
        for pattern in self.files:
            matches = sorted(dest.glob(pattern))
            if not matches:
                raise FileNotFoundError(f"{pattern} not found in the download from {self.url}")
            paths += matches
        return paths


@dataclass(frozen=True, kw_only=True)
class TileListSource(Source):
    """A dataset split into tiles, with the download URL of each tile listed at ``url``.

    ``url`` is a text file with one tile URL per line. The tiles are downloaded one at a time
    by ``ClassifiedRasterLayer``, so ``files`` is not used.
    """

    files: tuple[str, ...] = ()

    def tile_urls(self) -> dict[str, str]:
        """Return the download URL of each tile, by tile id."""
        response = requests.get(self.url, timeout=60)
        response.raise_for_status()
        return {Path(urlparse(url).path).stem: url for url in response.text.split()}


@dataclass(frozen=True, kw_only=True)
class ArcGISTileListSource(TileListSource):
    """A tile list kept as an ArcGIS feature layer, with one feature per tile.

    Attributes:
        name_field: Field with the tile id.
        url_field: Field with the tile's download URL.
    """

    name_field: str
    url_field: str

    def tile_urls(self) -> dict[str, str]:
        params = {
            "where": "1=1",
            "outFields": f"{self.name_field},{self.url_field}",
            "returnGeometry": "false",
            "f": "json",
        }
        response = requests.get(f"{self.url}/query", params=params, timeout=60)
        response.raise_for_status()
        result = response.json()
        # ArcGIS reports errors, and results cut at the server's record limit, with a 200.
        if "error" in result or result.get("exceededTransferLimit"):
            raise RuntimeError(f"Incomplete tile list from {self.url}: {result.get('error')}")
        return {
            feature["attributes"][self.name_field]: feature["attributes"][self.url_field]
            for feature in result["features"]
        }


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


@dataclass(frozen=True, kw_only=True)
class Layer(ABC):
    """One or more source datasets published to Mapbox as one tileset.

    Attributes:
        name: Mapbox tileset name (``<account>.<name>``), also used for local file names.
        title: Display name in Mapbox Studio.
        sources: Datasets to download and read.
    """

    name: str
    title: str
    sources: tuple[Source, ...]

    def __post_init__(self) -> None:
        validate_tileset_name(self.name)

    @property
    def raw_dir(self) -> Path:
        return RAW_DATA_DIR / self.name

    @property
    def mbtiles_path(self) -> Path:
        return MBTILES_DIR / f"{self.name}.mbtiles"

    def fetch(self, refresh: bool = False) -> list[tuple[Path, Source]]:
        """Fetch every source and return each file to process with the source it came from."""
        return [
            (path, source)
            for index, source in enumerate(self.sources)
            for path in source.fetch(self.raw_dir / str(index), refresh=refresh)
        ]

    @abstractmethod
    def tile(self, files: list[tuple[Path, Source]]) -> Path:
        """Convert the fetched ``files`` into ``self.mbtiles_path``."""

    def run(self, upload: bool = True, refresh: bool = False) -> Path:
        """Fetch, tile and optionally upload the layer. Returns the MBTiles path."""
        console.rule(self.title)
        mbtiles = self.tile(self.fetch(refresh=refresh))
        console.print(f"Tiled to {mbtiles}")
        if upload:
            self.upload()
        return mbtiles

    def upload(self) -> None:
        """Upload the existing ``mbtiles_path`` to Mapbox, replacing the tileset if it exists."""
        if not self.mbtiles_path.exists():
            raise FileNotFoundError(f"{self.mbtiles_path} not found: run the layer first")
        upload_tileset(
            self.mbtiles_path,
            self.name,
            username=os.environ["MAPBOX_USER"],
            token=os.environ["MAPBOX_TOKEN"],
            name=self.title,
        )
        console.print(f"Uploaded as {os.environ['MAPBOX_USER']}.{self.name}")


@dataclass(frozen=True, kw_only=True)
class VectorLayer(Layer):
    """A vector source tiled with ``vector_to_mbtiles``.

    Attributes:
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.
        fields: Attributes to keep in the tiles. ``None`` keeps all of them. Include ``"type"``
            to keep the source labels.
        where: Attribute filter, e.g. ``"STATUS = 'Designated'"``.
        open_options: GDAL open options for the source, e.g. ``("ENCODING=ISO-8859-1",)``.
    """

    min_zoom: int = 0
    max_zoom: int = 10
    fields: tuple[str, ...] | None = None
    where: str | None = None
    open_options: tuple[str, ...] = ()

    def tile(self, files: list[tuple[Path, Source]]) -> Path:
        labelled = any(source.label for _, source in files)
        return vector_to_mbtiles(
            [path for path, _ in files],
            self.mbtiles_path,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom,
            fields=self.fields,
            where=self.where,
            labels=[source.label or "" for _, source in files] if labelled else None,
            open_options=self.open_options,
        )


@dataclass(frozen=True, kw_only=True)
class ClassifiedRasterLayer(Layer):
    """A tiled raster classified into value bins and published as polygons, like landcover.

    Each source tile is downloaded, polygonized once per zoom band and deleted, by
    ``workers`` tiles at a time, so the full raster is never on disk. Tiles already
    polygonized are skipped, so an interrupted run resumes where it stopped. Each polygon
    gets ``level``, the lower bound of its bin, and ``class``, the bin's label. The polygons
    are deleted once the MBTiles is built.

    A copy of each tile averaged to ``coarse_resolution`` is kept. Bands at that resolution
    or coarser are polygonized from it, so changing their settings needs no new download.

    Attributes:
        sources: Tile lists to read.
        classes: ``(level, label)`` pairs in ascending order. Each bin runs from its level up
            to the next one; values below the first level are left out.
        max_value: Upper bound of the last bin.
        bands: Zoom bands, each with its own resampling and sieve, covering every zoom
            level once.
        workers: Number of tiles processed at the same time.
        coarse_resolution: Cell size of the kept copies, in degrees. Band resolutions from
            it up should be whole multiples of it.
    """

    sources: tuple[TileListSource, ...]
    classes: tuple[tuple[int, str], ...]
    max_value: float
    bands: tuple[ZoomBand, ...]
    workers: int = 4
    coarse_resolution: float = 0.004

    @property
    def polygons_dir(self) -> Path:
        return POLYGONS_DIR / self.name

    @property
    def coarse_dir(self) -> Path:
        return self.polygons_dir / f"coarse_{self.coarse_resolution:g}deg"

    def fetch(self, refresh: bool = False) -> list[tuple[Path, Source]]:
        """Nothing is fetched up front: ``tile`` downloads the tiles one at a time."""
        if refresh:
            shutil.rmtree(self.polygons_dir, ignore_errors=True)
        return []

    def tile(self, files: list[tuple[Path, Source]]) -> Path:
        tiles = {tile: url for source in self.sources for tile, url in source.tile_urls().items()}
        console.print(f"Polygonizing {len(tiles)} tiles, {self.workers} at a time")
        with ThreadPoolExecutor(self.workers) as pool:
            futures = {
                tile: pool.submit(self._polygonize_tile, tile, url) for tile, url in tiles.items()
            }
        failed = [tile for tile, future in futures.items() if future.exception()]
        for tile in failed:
            console.print(f"[red]{tile} failed: {futures[tile].exception()}")
        if failed:
            raise RuntimeError(f"{len(failed)} tiles failed; run again to retry only those")

        MBTILES_DIR.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory(dir=MBTILES_DIR) as tmp,
            ThreadPoolExecutor(len(self.bands)) as pool,
        ):
            bands = list(pool.map(lambda band: self._tile_band(band, Path(tmp)), self.bands))
            mbtiles = merge_mbtiles(bands, self.mbtiles_path)
        # The polygons are only needed to build the MBTiles; the coarse copies are kept.
        for path in self.polygons_dir.iterdir():
            if path != self.coarse_dir:
                shutil.rmtree(path)
        return mbtiles

    def _polygons_path(self, band: ZoomBand, tile: str) -> Path:
        return self.polygons_dir / band.name / f"{tile}.gpkg"

    def _polygonize_tile(self, tile: str, url: str) -> None:
        # Tiles without any polygon in a band, such as open ocean, leave an `.empty` marker.
        missing = [
            band
            for band in self.bands
            if not self._polygons_path(band, tile).exists()
            and not self._polygons_path(band, tile).with_suffix(".empty").exists()
        ]
        if not missing:
            return
        coarse = self.coarse_dir / f"{tile}.tif"
        fine = [band for band in missing if band.resolution < self.coarse_resolution]
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.raw_dir) as tmp:
            if fine or not coarse.exists():
                raster = download_file(url, Path(tmp) / f"{tile}.tif")
                # Nodata means no trees here: count it as 0 when averaging into coarse cells.
                unset_nodata(raster)
                if not coarse.exists():
                    # Moved into place only once complete, like the polygons.
                    resample(raster, Path(tmp) / "coarse.tif", self.coarse_resolution)
                    coarse.parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / "coarse.tif").replace(coarse)
            for band in missing:
                source = raster if band in fine else coarse
                self._polygonize_band(source, band, tile)
        console.print(f"Polygonized {tile}")

    def _polygonize_band(self, raster: Path, band: ZoomBand, tile: str) -> None:
        path = self._polygons_path(band, tile)
        polygons = classify_to_polygons(
            raster,
            path,
            layer=self.name,
            classes=self.classes,
            max_value=self.max_value,
            resolution=band.resolution,
            sieve=band.sieve,
        )
        if polygons is None:
            path.with_suffix(".empty").touch()

    def _tile_band(self, band: ZoomBand, dest: Path) -> Path:
        console.print(f"Tiling {band.name}")
        return vector_to_mbtiles(
            sorted((self.polygons_dir / band.name).glob("*.gpkg")),
            dest / f"{band.name}.mbtiles",
            min_zoom=band.min_zoom,
            max_zoom=band.max_zoom,
            layer_name=self.name,
        )
