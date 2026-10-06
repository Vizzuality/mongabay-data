"""Layer configs that know how to fetch, tile and upload themselves to Mapbox."""

import os
import zipfile
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..config import MBTILES_DIR
from ..config import RAW_DATA_DIR
from ..converters.mbtiles import vector_to_mbtiles
from ..download import download_file
from ..download import unzip
from ..mapbox import upload_tileset
from ..mapbox import validate_tileset_name

console = Console()


@dataclass(frozen=True, kw_only=True)
class Layer(ABC):
    """A source dataset published to Mapbox as one tileset.

    Attributes:
        name: Mapbox tileset name (``<account>.<name>``), also used for local file names.
        title: Display name in Mapbox Studio.
        url: Where to download the source data. Zip archives are extracted.
        source_file: File to process, relative to the extracted download.
    """

    name: str
    title: str
    url: str
    source_file: str

    def __post_init__(self) -> None:
        validate_tileset_name(self.name)

    @property
    def raw_dir(self) -> Path:
        return RAW_DATA_DIR / self.name

    @property
    def mbtiles_path(self) -> Path:
        return MBTILES_DIR / f"{self.name}.mbtiles"

    def fetch(self, refresh: bool = False) -> Path:
        """Download the source unless it is already cached, and return the file to process."""
        source = self.raw_dir / self.source_file
        if source.exists() and not refresh:
            console.print(f"Using cached {source}")
            return source

        console.print(f"Downloading {self.url}")
        download = download_file(self.url, self.raw_dir / "download")
        if zipfile.is_zipfile(download):
            unzip(download, self.raw_dir)
            download.unlink()
        else:
            download.replace(source)

        if not source.exists():
            raise FileNotFoundError(f"{self.source_file} not found in the download from {self.url}")
        return source

    @abstractmethod
    def tile(self, source: Path) -> Path:
        """Convert ``source`` into ``self.mbtiles_path``."""

    def run(self, upload: bool = True, refresh: bool = False) -> Path:
        """Fetch, tile and optionally upload the layer. Returns the MBTiles path."""
        console.rule(self.title)
        mbtiles = self.tile(self.fetch(refresh=refresh))
        console.print(f"Tiled to {mbtiles}")
        if upload:
            upload_tileset(
                mbtiles,
                self.name,
                username=os.environ["MAPBOX_USER"],
                token=os.environ["MAPBOX_TOKEN"],
                name=self.title,
            )
            console.print(f"Uploaded as {os.environ['MAPBOX_USER']}.{self.name}")
        return mbtiles


@dataclass(frozen=True, kw_only=True)
class VectorLayer(Layer):
    """A vector source tiled with ``vector_to_mbtiles``.

    Attributes:
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.
        fields: Attributes to keep in the tiles. ``None`` keeps all of them.
        open_options: GDAL open options for the source, e.g. ``("ENCODING=ISO-8859-1",)``.
    """

    min_zoom: int = 0
    max_zoom: int = 10
    fields: tuple[str, ...] | None = None
    open_options: tuple[str, ...] = ()

    def tile(self, source: Path) -> Path:
        return vector_to_mbtiles(
            source,
            self.mbtiles_path,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom,
            fields=self.fields,
            open_options=self.open_options,
        )
