"""Where layers get their data: downloadable datasets and lists of raster tiles."""

import zipfile
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich import get_console

from ..download import download_file
from ..download import unzip


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
            get_console().print(f"Using cached {dest}")
            return self._match(dest)

        get_console().print(f"Downloading {self.url}")
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
            if not (matches := sorted(dest.glob(pattern))):
                raise FileNotFoundError(f"{pattern} not found in the download from {self.url}")
            paths += matches
        return paths


@dataclass(frozen=True, kw_only=True)
class TileIndex(ABC):
    """A raster split into tiles, with the download URL of each tile listed at ``url``."""

    url: str

    @abstractmethod
    def tile_urls(self) -> dict[str, str]:
        """Return the download URL of each tile, by tile id."""


@dataclass(frozen=True, kw_only=True)
class TextTileIndex(TileIndex):
    """A text file with one tile URL per line. Tiles are named after their file name."""

    def tile_urls(self) -> dict[str, str]:
        response = requests.get(self.url, timeout=60)
        response.raise_for_status()
        return {Path(urlparse(url).path).stem: url for url in response.text.split()}


@dataclass(frozen=True, kw_only=True)
class ArcGISTileIndex(TileIndex):
    """An ArcGIS feature layer with one feature per tile.

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
