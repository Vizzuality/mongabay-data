"""Layers published to the Mongabay Mapbox account. Add a config here to add a layer."""

from .base import Layer
from .base import VectorLayer

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"

# Marine Regions, Flanders Marine Institute (2023), CC BY 4.0.
EEZ = VectorLayer(
    name="eez",
    title="Exclusive Economic Zones (Marine Regions v12)",
    url=(
        f"{MARINE_REGIONS_WFS}?service=WFS&version=1.0.0&request=GetFeature"
        "&typeName=MarineRegions:eez&outputFormat=SHAPE-ZIP"
    ),
    source_file="eez.shp",
    max_zoom=8,
    fields=(
        "mrgid",
        "geoname",
        "pol_type",
        "territory1",
        "iso_ter1",
        "sovereign1",
        "iso_sov1",
        "area_km2",
    ),
    # GeoServer declares the encoding in a .cst file, which GDAL does not read.
    open_options=("ENCODING=ISO-8859-1",),
)

LAYERS: dict[str, Layer] = {layer.name: layer for layer in (EEZ,)}
