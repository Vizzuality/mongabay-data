# Mongabay data

Data processing and analysis for the Mongabay project family.

## Project organization

``` txt
├── LICENSE
├── README.md
├── CHANGELOG.md
├── pyproject.toml               <- Project metadata and dependencies (uv)
├── uv.lock                      <- Pinned dependency versions, committed
├── .env.example                 <- Template for the local .env
├── .editorconfig                <- Editor defaults
├── .pre-commit-config.yaml      <- Pre-commit hooks (ruff, Conventional Commits)
├── .github/                     <- Issue and pull request templates
│
├── src/data_processing/         <- The project package, installed into the environment
├── tests/                       <- Tests, mirroring the layout of src/
│
├── notebooks/                   <- Analysis and processing notebooks
│   ├── templates/               <- Starting points for new notebooks
│   └── archive/                 <- Preserved 2021-2023 work (see below)
│
├── cloud_functions/             <- Google Cloud Functions, deployed independently
│   ├── animation/
│   └── fire_tool/
│
├── data/                        <- Local only, not tracked in git
│   ├── raw/                     <- Original, immutable inputs
│   └── processed/               <- Final, canonical datasets
│
└── docs/                        <- Local only, not tracked in git
```

`data/` and `docs/` are gitignored on purpose. `data/` holds inputs and outputs that are too
large or too sensitive for the repository; fetch or regenerate them from the notebook or
script that produces them. `docs/` is a scratch space for client documents, methodology notes
and working specs that are not meant to be shared through git.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). Install it once, then from the repository
root:

``` bash
uv sync
```

This creates `.venv`, installs every dependency at the versions pinned in `uv.lock`, and
installs `src/data_processing` in editable mode. There is no `sys.path` juggling: notebooks,
tests and scripts can all `import data_processing` directly.

The converters in `data_processing.converters` (MBTiles and COG) call the unified `gdal`
command, a system dependency that needs **GDAL 3.13 or newer** (`brew install gdal` on macOS;
check with `gdal --version`). Upstream still marks this command as provisional, so a GDAL
upgrade can change its syntax: all calls go through `converters/_gdal.py`.

Install the git hooks:

``` bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Copy the environment template and fill in your values:

``` bash
cp .env.example .env
```

## Daily commands

``` bash
uv run jupyter lab            # start JupyterLab
uv run pytest                 # run the tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv add <package>              # add a dependency and update pyproject.toml + uv.lock
uv add --dev <package>        # add a development-only dependency
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/); the
`commit-msg` hook enforces this.

## Layer pipelines

Layers published to the Mongabay Mapbox account are configured in
`src/data_processing/pipelines/layers.py`. Each pipeline downloads the source into `data/raw/`
(cached between runs), tiles it into `data/processed/mbtiles/` and uploads it as a Mapbox
tileset. Uploading needs `MAPBOX_USER` and `MAPBOX_TOKEN` in `.env`.

``` bash
uv run python -m data_processing.pipelines --list           # available layers
uv run python -m data_processing.pipelines eez --no-upload  # tile only
uv run python -m data_processing.pipelines eez              # tile and upload
```

To add a vector layer, add a config and register it in `LAYERS`:

``` python
MANGROVES = VectorLayer(
    name="mangroves",  # Mapbox tileset name, at most 32 characters
    title="Mangrove forests",
    sources=(
        Source(
            url="https://example.org/mangroves.zip",
            files=("*/mangroves.shp",),  # glob patterns inside the extracted zip
        ),
    ),
    max_zoom=10,
    fields=("name", "year"),  # attributes to keep
    where="year >= 2000",  # optional attribute filter
)
```

Every file matched by every source is merged into a single tile layer, named after the
tileset. Zips nested inside the download are extracted too.
When a layer merges several sources, give each one a `label` and list `"type"` in `fields`:
each feature then gets a `type` attribute with its source label (see `CORAL_REEFS`, which
labels features as `warm` or `cold`).

Check each source's licence: most require attribution on the map. The EEZ layer is Marine
Regions, CC BY 4.0. Global Mangrove Watch v3.0 is CC BY 4.0: cite Bunting et al. (2022).
The WDPA and the UNEP-WCMC coral datasets are for **non-commercial** use only, must not be
downloadable from the map, and need a visible citation with the release year and a link to [protectedplanet.net](https://www.protectedplanet.net) or
[unep-wcmc.org](https://www.unep-wcmc.org). The WDPA licence also requires the latest
monthly release, so update its URL in `layers.py` when publishing again.

## Notebooks

New work goes directly in `notebooks/`, starting from `notebooks/templates/` if useful.
Notebooks read from and write to `data/`, and import shared logic from `data_processing`;
once a piece of code is used by more than one notebook, move it into `src/data_processing/`
and add a test for it.

`notebooks/archive/` holds the 2021-2023 work from earlier contracts: the `processing/`
series on basemaps, MBTiles and fire tooling, the `mongabay_restoration/` R script, and the
`mongabay_charts_tool/` forest loss exploration. It is kept for reference and for its git
history. These notebooks were written against a conda environment inside Docker that no
longer exists, and several of them point at data paths that were never committed, so they are
not expected to run as-is. Linting and formatting skip this directory.

## Cloud functions

`cloud_functions/` contains two Google Cloud Functions, `animation` and `fire_tool`. They are
deployed independently, each pinning its own dependencies in its `requirements.txt`, and are
deliberately outside the uv environment and the lint configuration.
