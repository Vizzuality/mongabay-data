"""Convert GeoTIFFs to Cloud Optimized GeoTIFFs (COGs)."""

from pathlib import Path

from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles


def convert_tif_to_cog(
    input_file: Path,
    output_file: Path,
    resampling: str = "average",
    nodata_value: float | None = None,
) -> Path:
    """Convert a GeoTIFF to a web-optimized, ZSTD-compressed COG.

    Args:
        input_file: Source GeoTIFF.
        output_file: Destination COG.
        resampling: Overview resampling method, e.g. "nearest", "average", "mode".
            Use "nearest" or "mode" for categorical data.
        nodata_value: Nodata value to set. Defaults to the one in the source file.

    Returns:
        The path of the generated COG.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    profile = cog_profiles.get("zstd")
    profile.update({"BLOCKXSIZE": 512, "BLOCKYSIZE": 512})

    cog_translate(
        input_file,
        output_file,
        profile,
        overview_resampling=resampling,
        web_optimized=True,
        nodata=nodata_value,
    )
    return output_file
