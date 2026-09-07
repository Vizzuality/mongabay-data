"""Check that the project package is importable from the installed environment."""

import data_processing


def test_package_is_importable():
    assert data_processing.__doc__
