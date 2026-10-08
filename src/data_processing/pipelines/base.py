"""The base class of every layer published to the Mongabay Mapbox account."""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path

from rich import get_console

from ..config import MBTILES_DIR
from ..config import RAW_DATA_DIR
from ..mapbox import MapboxAccount
from ..mapbox import upload_tileset
from ..mapbox import validate_tileset_name


@dataclass(frozen=True, kw_only=True)
class Layer(ABC):
    """A dataset built into one MBTiles file and published to Mapbox as one tileset.

    Attributes:
        name: Mapbox tileset name (``<account>.<name>``), also used for local file names.
        title: Display name in Mapbox Studio.
    """

    name: str
    title: str

    def __post_init__(self) -> None:
        validate_tileset_name(self.name)

    @property
    def raw_dir(self) -> Path:
        return RAW_DATA_DIR / self.name

    @property
    def mbtiles_path(self) -> Path:
        return MBTILES_DIR / f"{self.name}.mbtiles"

    @abstractmethod
    def build(self, refresh: bool = False) -> Path:
        """Fetch the sources and tile them into ``mbtiles_path``, which is returned.

        Args:
            refresh: Download the sources again instead of using cached files.
        """

    def run(self, account: MapboxAccount | None = None, refresh: bool = False) -> Path:
        """Build the layer, and upload it when an ``account`` is given."""
        get_console().rule(self.title)
        mbtiles = self.build(refresh=refresh)
        get_console().print(f"Tiled to {mbtiles}")
        if account:
            self.upload(account)
        return mbtiles

    def upload(self, account: MapboxAccount) -> None:
        """Upload the existing ``mbtiles_path``, replacing the tileset if it exists."""
        if not self.mbtiles_path.exists():
            raise FileNotFoundError(f"{self.mbtiles_path} not found: run the layer first")
        upload_tileset(self.mbtiles_path, self.name, account, name=self.title)
        get_console().print(f"Uploaded as {account.username}.{self.name}")
