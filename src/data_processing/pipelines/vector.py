"""Layers built from vector datasets."""

from dataclasses import dataclass
from pathlib import Path

from ..converters.mbtiles import vector_to_mbtiles
from .base import Layer
from .sources import Source


@dataclass(frozen=True, kw_only=True)
class VectorLayer(Layer):
    """One or more vector datasets merged into a single tile layer.

    Attributes:
        sources: Datasets to download and read.
        min_zoom: Lowest zoom level to generate.
        max_zoom: Highest zoom level to generate.
        fields: Attributes to keep in the tiles. ``None`` keeps all of them. Include ``"type"``
            to keep the source labels.
        where: Attribute filter, e.g. ``"STATUS = 'Designated'"``.
        open_options: GDAL open options for the source, e.g. ``("ENCODING=ISO-8859-1",)``.
    """

    sources: tuple[Source, ...]
    min_zoom: int = 0
    max_zoom: int = 10
    fields: tuple[str, ...] | None = None
    where: str | None = None
    open_options: tuple[str, ...] = ()

    def build(self, refresh: bool = False) -> Path:
        files = [
            (path, source.label or "")
            for index, source in enumerate(self.sources)
            for path in source.fetch(self.raw_dir / str(index), refresh=refresh)
        ]
        labelled = any(source.label for source in self.sources)
        return vector_to_mbtiles(
            [path for path, _ in files],
            self.mbtiles_path,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom,
            fields=self.fields,
            where=self.where,
            labels=[label for _, label in files] if labelled else None,
            open_options=self.open_options,
        )
