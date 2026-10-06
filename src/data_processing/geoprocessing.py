"""Common GeoDataFrame clean-up helpers."""

import geopandas as gpd


def reorder_columns_geometry_last(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return ``gdf`` with the ``geometry`` column moved to the end."""
    cols = [c for c in gdf.columns if c != "geometry"] + ["geometry"]
    return gdf[cols]


def process_geodataframe_columns(
    gdf: gpd.GeoDataFrame,
    columns_to_drop: list[str] | None = None,
    lowercase_columns: bool = True,
    sort_by: str | list[str] | None = None,
    ascending: bool = True,
) -> gpd.GeoDataFrame:
    """Apply the usual column clean-up to a GeoDataFrame.

    Args:
        gdf: GeoDataFrame to process. It is not modified.
        columns_to_drop: Columns to drop. Names missing from ``gdf`` are ignored.
        lowercase_columns: Whether to lowercase column names before dropping.
        sort_by: Column or columns to sort the rows by.
        ascending: Sort order.

    Returns:
        A new GeoDataFrame with the geometry column last.
    """
    if lowercase_columns:
        gdf = gdf.rename(columns=str.lower)

    if columns_to_drop:
        gdf = gdf.drop(columns=columns_to_drop, errors="ignore")

    if sort_by:
        gdf = gdf.sort_values(by=sort_by, ascending=ascending, ignore_index=True)

    return reorder_columns_geometry_last(gdf)
