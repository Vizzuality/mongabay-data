"""Layers published to the Mongabay Mapbox account. Add a config here to add a layer."""

from .base import ArcGISTileListSource
from .base import ClassifiedRasterLayer
from .base import Layer
from .base import Source
from .base import TileListSource
from .base import VectorLayer
from .base import ZoomBand

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"

# Marine Regions, Flanders Marine Institute (2023), CC BY 4.0.
EEZ = VectorLayer(
    name="eez",
    title="Exclusive Economic Zones (Marine Regions v12)",
    sources=(
        Source(
            url=(
                f"{MARINE_REGIONS_WFS}?service=WFS&version=1.0.0&request=GetFeature"
                "&typeName=MarineRegions:eez&outputFormat=SHAPE-ZIP"
            ),
            files=("eez.shp",),
        ),
    ),
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

# UNEP-WCMC and IUCN (2026), Protected Planet: WDPA and WD-OECM, October 2026. Non-commercial.
# The URL changes with each monthly release, and the licence requires using the latest one.
MARINE_PROTECTED_AREAS = VectorLayer(
    name="marine_protected_areas",
    title="Marine Protected Areas (WDPA, October 2026)",
    sources=(
        Source(
            url=(
                "https://d1gam3xoknrgr2.cloudfront.net/current/"
                "WDPA_WDOECM_Oct2026_Public_marine_shp.zip"
            ),
            # Split into three nested zips; points (sites without boundaries) are left out.
            files=("*/*-polygons.shp",),
        ),
    ),
    # Protected Planet practice: implemented sites only, without UNESCO-MAB buffer zones.
    where=(
        "STATUS IN ('Designated', 'Inscribed', 'Established') "
        "AND DESIG_ENG <> 'UNESCO-MAB Biosphere Reserve'"
    ),
    max_zoom=10,
    fields=(
        "SITE_ID",
        "SITE_TYPE",
        "NAME_ENG",
        "NAME",
        "DESIG_ENG",
        "IUCN_CAT",
        "STATUS",
        "STATUS_YR",
        "ISO3",
        "NO_TAKE",
        "GIS_M_AREA",
    ),
)

# UNEP-WCMC et al. (2021), warm-water coral reefs v4.1, and UNEP-WCMC et al. (2017),
# cold-water corals v5.1. Non-commercial. Only polygons: the point records are survey
# locations, not reef extents.
CORAL_REEFS = VectorLayer(
    name="coral_reefs",
    title="Coral reefs (UNEP-WCMC)",
    sources=(
        Source(
            url="https://wcmc.io/WCMC_008",
            files=("*/01_Data/WCMC008_CoralReef2018_Py_v4_1.shp",),
            label="warm",
        ),
        Source(
            url="https://wcmc.io/WCMC_001",
            files=("*/01_Data/WCMC001_ColdCorals2017_Py_v5_1.shp",),
            label="cold",
        ),
    ),
    max_zoom=10,
    fields=(
        "type",
        "NAME",
        "FAMILY",
        "GENUS",
        "SPECIES",
        "DATA_TYPE",
        "VERIF",
        "METADATA_I",
        "DEPTH_MIN",
        "DEPTH_MAX",
    ),
)

# Bunting et al. (2022), Global Mangrove Watch v3.0, Remote Sensing. CC BY 4.0.
MANGROVES = VectorLayer(
    name="mangroves",
    title="Mangroves (Global Mangrove Watch v3.0, 2020)",
    sources=(
        Source(
            url="https://zenodo.org/records/6894273/files/gmw_v3_2020_vec.zip?download=1",
            files=("gmw_v3_2020_vec.shp",),
        ),
    ),
    max_zoom=12,
)

FOREST_BANDS = (
    ZoomBand(min_zoom=0, max_zoom=0, resolution=0.2, sieve=2),
    ZoomBand(min_zoom=1, max_zoom=2, resolution=0.1, sieve=2),
    ZoomBand(min_zoom=3, max_zoom=3, resolution=0.08, sieve=2),
    ZoomBand(min_zoom=4, max_zoom=4, resolution=0.04, sieve=2),
    ZoomBand(min_zoom=5, max_zoom=7, resolution=0.016, sieve=4),
    ZoomBand(min_zoom=8, max_zoom=9, resolution=0.004, sieve=8),
    ZoomBand(min_zoom=10, max_zoom=10, resolution=0.002, sieve=16),
)

# Hansen et al. (2013), Science. Global Forest Change v1.2, tree cover 2000. CC BY 4.0.
TREE_COVER_2000 = ClassifiedRasterLayer(
    name="tree_cover_2000",
    title="Tree cover 2000 (Hansen/UMD/Google/USGS/NASA)",
    sources=(
        TileListSource(
            url="https://storage.googleapis.com/earthenginepartners-hansen/GFC2015/treecover2000.txt"
        ),
    ),
    # Canopy density, %.
    classes=((10, "10-30"), (30, "30-50"), (50, "50-75"), (75, "75-100")),
    max_value=100,
    bands=FOREST_BANDS,
)

# Harris et al. (2021), Nature Climate Change. WHRC aboveground live woody biomass density
# 2000, v1.4. CC BY 4.0.
TREE_BIOMASS_DENSITY = ClassifiedRasterLayer(
    name="tree_biomass_density",
    title="Aboveground live woody biomass density 2000 (WHRC)",
    sources=(
        ArcGISTileListSource(
            url=(
                "https://services2.arcgis.com/g8WusZB13b9OegfU/arcgis/rest/services/"
                "Aboveground_Live_Woody_Biomass_Density/FeatureServer/0"
            ),
            name_field="tile_id",
            url_field="Mg_ha_1_download",
        ),
    ),
    # Biomass, Mg/ha.
    classes=(
        (1, "1-80"),
        (80, "80-160"),
        (160, "160-240"),
        (240, "240-320"),
        (320, "320-400"),
        (400, "400+"),
    ),
    max_value=65535,  # the UInt16 maximum: the last bin is open-ended
    bands=FOREST_BANDS,
)

LAYERS: dict[str, Layer] = {
    layer.name: layer
    for layer in (
        EEZ,
        MARINE_PROTECTED_AREAS,
        CORAL_REEFS,
        MANGROVES,
        TREE_COVER_2000,
        TREE_BIOMASS_DENSITY,
    )
}
