"""Convert rasters to Cloud Optimized GeoTIFFs (COGs) with the ``gdal`` CLI."""

from pathlib import Path

from ._gdal import run_gdal


def convert_tif_to_cog(
    input_file: Path,
    output_file: Path,
    resampling: str = "average",
    nodata_value: float | None = None,
) -> Path:
    """Convert a raster to a ZSTD-compressed COG on the Web Mercator tile grid.

    The output is aligned to ``GoogleMapsCompatible`` tiles, ready to serve from a bucket
    with TiTiler. An existing ``output_file`` is replaced.

    Args:
        input_file: Source raster.
        output_file: Destination COG.
        resampling: Overview resampling method, e.g. "nearest", "average", "mode".
            Use "nearest" or "mode" for categorical data.
        nodata_value: Nodata value to set. Defaults to the one in the source file.

    Returns:
        The path of the generated COG.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    steps = ["!", "read", str(input_file)]
    if nodata_value is not None:
        steps += ["!", "edit", "--nodata", str(nodata_value)]
    steps += [
        "!", "write", str(output_file), "--of", "COG", "--overwrite",
        "--co", "COMPRESS=ZSTD",
        "--co", "BLOCKSIZE=512",
        "--co", "TILING_SCHEME=GoogleMapsCompatible",
        "--co", f"OVERVIEW_RESAMPLING={resampling}",
        "--co", "NUM_THREADS=ALL_CPUS",
    ]  # fmt: skip
    run_gdal("raster", "pipeline", "--quiet", *steps)
    return output_file
