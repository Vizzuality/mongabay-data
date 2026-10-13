"""Classify rasters into value bins and turn the bins into polygons with the ``gdal`` CLI."""

import sqlite3
import tempfile
from collections.abc import Sequence
from pathlib import Path

from ._gdal import run_gdal


def unset_nodata(path: Path) -> Path:
    """Remove the nodata value of a raster in place, so its nodata pixels count as values.

    Resampling skips nodata pixels, so a coarse cell with a single valid pixel gets that
    pixel's value. Where nodata means "none", such as no biomass, unset it first so those
    pixels lower the average instead. Only the metadata is rewritten.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    run_gdal("raster", "edit", "--quiet", "--nodata", "none", str(path))
    return path


def resample(input_path: Path, output_path: Path, resolution: float) -> Path:
    """Average a raster onto a coarser grid. Nodata pixels are left out of the average.

    Classifying the result at a resolution that is a whole multiple of ``resolution`` gives
    the same cell averages as classifying ``input_path``, up to rounding to the input's data
    type. An existing ``output_path`` is replaced.

    Args:
        input_path: Raster to resample.
        output_path: Destination GeoTIFF.
        resolution: Cell size of the output, in the input's units.

    Returns:
        The path of the resampled raster.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_gdal(
        "raster", "pipeline", "--quiet",
        "!", "read", str(input_path),
        "!", "resize", "--resolution", f"{resolution},{resolution}", "-r", "average",
        "!", "write", str(output_path), "--overwrite", "--co", "COMPRESS=DEFLATE",
    )  # fmt: skip
    return output_path


def classify_to_polygons(
    input_path: Path,
    output_path: Path,
    layer: str,
    classes: Sequence[tuple[int, str]],
    max_value: float,
    resolution: float,
    sieve: int = 0,
) -> Path | None:
    """Resample a raster, classify it into bins and polygonize the bins into a GeoPackage.

    Each polygon gets ``level``, the lower bound of its bin, and ``class``, the bin's label.
    Values below the first bin are left out, and so are nodata pixels from the averages (see
    ``unset_nodata``). ``output_path`` only appears once complete; an existing one is
    replaced.

    Args:
        input_path: Raster to classify, in a geographic CRS.
        output_path: Destination ``.gpkg`` file.
        layer: Name of the output layer.
        classes: ``(level, label)`` pairs in ascending order. Each bin runs from its level
            up to the next one; the last bin runs up to ``max_value`` included.
        max_value: Upper bound of the last bin.
        resolution: Cell size of the resampled raster, in the input's units.
        sieve: Merge patches smaller than this many cells into their neighbours. 0 keeps
            them all.

    Returns:
        The path of the generated GeoPackage, or ``None`` when no cell falls in a bin; then
        nothing is written.

    Raises:
        RuntimeError: If ``gdal`` fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    levels = [level for level, _ in classes]
    bins = [f"[{low},{high})={low}" for low, high in zip(levels, levels[1:], strict=False)]
    mapping = "; ".join([*bins, f"[{levels[-1]},{max_value}]={levels[-1]}", "DEFAULT=0"])
    cases = " ".join(f"WHEN {level} THEN '{label}'" for level, label in classes)

    with tempfile.TemporaryDirectory(dir=output_path.parent) as tmp:
        classified = Path(tmp) / "classified.tif"
        polygons = Path(tmp) / "polygons.gpkg"
        labelled = Path(tmp) / "labelled.gpkg"
        steps = [
            "!", "read", str(input_path),
            "!", "resize", "--resolution", f"{resolution},{resolution}", "-r", "average",
            "!", "reclassify", "-m", mapping, "--ot", "UInt16",
            "!", "edit", "--nodata", "0",
        ]  # fmt: skip
        if sieve:
            steps += ["!", "sieve", "--size-threshold", str(sieve), "--connect-diagonal-pixels"]
        steps += ["!", "write", str(classified), "--co", "COMPRESS=DEFLATE"]
        run_gdal("raster", "pipeline", "--quiet", *steps)
        run_gdal(
            "raster", "polygonize", "--quiet", str(classified), str(polygons),
            "--attribute-name", "level", "--output-layer", layer,
        )  # fmt: skip
        # Without any polygon, GDAL writes a GeoPackage with no layer, which it cannot read.
        db = sqlite3.connect(polygons)
        has_layer = db.execute("SELECT 1 FROM gpkg_contents").fetchone()
        db.close()
        if not has_layer:
            return None
        run_gdal(
            "vector", "pipeline", "--quiet",
            "!", "read", str(polygons),
            "!", "sql", "--dialect", "SQLITE",
            f'SELECT *, CASE level {cases} END AS class FROM "{layer}"',
            "!", "write", str(labelled), "--output-layer", layer,
        )  # fmt: skip
        # Moved into place only once complete, so a present file is always a finished one.
        labelled.replace(output_path)
    return output_path
