Mongabay data processing and cloud functions
==============================

This repository contains the code for the data processing and cloud functions for the Mongabay project family.

Project Organization
------------

``` txt
├── LICENSE                             <- The LICENSE using this project.
├── README.md                           <- The top-level README for developers using this project.
├── CHANGELOG.md                        <- The top-level CHANGELOG for developers using this project.
├── Makefile                            <- Makefile with commands
├──.editorconfig                        <- Helps maintain consistent coding styles
├──.pre-commit-config                   <- Helps setup github basic pre-commit hooks
├── docker-compose.yml                  <- Docker configs environment definition
├── .gitignore                          <- files don't want to copy in github
├── .github                             <- github configs
│   └── templates                       <- github templates for issues and pull requests
├── cloud_functions                     <- Cloud functions for the project
├── data
    ├── env.default                     <- Environment vars definition
    ├── data
    │   ├── processed                   <- The final, canonical data sets.
    │   └── raw                         <- The original data.
    |
    └── notebooks                       <- Naming convention is a number (for ordering),
        │                                  the creator's initials, and a short `-` delimited e.g.
        │                                  `1.0-jqp-initial-data-exploration`.
        ├──.env
        ├──.dockerignore
        ├──environment.conda-lock.yaml  <- Notebook env.lock that will be used to quick install dependencies
        ├──package.yaml                 <- Notebooks requirements base on conda/mamba/micromamba env
        ├──Dockerfile                   <- Sets up Jupyter notebooks environment
        ├──jupyter_server_config.py     <- Configure Jupyter notebooks
        ├──template_notebooks           <- where the notebooks template will live.
        │
        ├──mongabay_charts_tool         <-
        │
        ├──mongabay_restoration         <-
        │
        └──processing                   <- .

```

--------

## Steps for use:

#### First, setup one of your environments

- With [docker]() and [docker-compose]() in your system, you can develop inside containers:
``` bash
make up
```
And if you want to get into the main container:
``` bash
make inside
```
------------
- Install requirements on your machine:
``` bash
make requirements
```
- Set up a new environment in your machine
``` bash
make create_environment && make requirements
```
------------

#### Happy coding and science!

You can run your tests:
``` bash
make test
```

You can lint and reformat your code:
``` bash
make lint
```
or up and serve the documentation:
``` bash
make serve-doc
```

--------
<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>
