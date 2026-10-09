"""Project paths shared by the processing modules and pipelines."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
MBTILES_DIR = PROCESSED_DATA_DIR / "mbtiles"
POLYGONS_DIR = PROCESSED_DATA_DIR / "polygons"
COG_DIR = PROCESSED_DATA_DIR / "cogs"
