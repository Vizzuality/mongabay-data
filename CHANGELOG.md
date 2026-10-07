# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## v0.2.0

Unreleased

### Added

- `data_processing` base modules for publishing layers to Mapbox: download helpers, GeoDataFrame
  clean-up, MBTiles (vector and raster) and COG converters built on the GDAL 3.13 `gdal` CLI,
  and a Mapbox Uploads API client.
- Config-driven layer pipelines (`python -m data_processing.pipelines`) and the Exclusive
  Economic Zones layer (Marine Regions v12).
- Layers built from several sources and files, with nested zip extraction, attribute filters
  and source labels.
- Marine Protected Areas (WDPA, October 2026) and Coral reefs (UNEP-WCMC warm-water and
  cold-water corals) layers.

### Changed

### Fixed

- Vector tiles stay under the Mapbox 500 KB limit, and features beyond the Web Mercator
  latitude limits are clipped instead of failing to project.

### Removed
