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
