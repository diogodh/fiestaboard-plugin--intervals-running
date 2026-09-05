"""Shared test fixtures for the Intervals.icu Running Stats plugin."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load __init__.py by file path under a unique module name. Works the same
# whether this repo is tested standalone, copied into FiestaBoard's plugins/
# directory, or cloned into external_plugins/ -- and avoids sys.modules
# collisions with any other package's own "__init__" module.
PLUGIN_DIR = Path(__file__).parent.parent
_MODULE_NAME = "intervals_running_plugin_under_test"

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, PLUGIN_DIR / "__init__.py")
intervals_running_module = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = intervals_running_module
_spec.loader.exec_module(intervals_running_module)


@pytest.fixture
def plugin_module():
    """The loaded plugin module (use for patching requests.* calls)."""
    return intervals_running_module


@pytest.fixture
def sample_manifest():
    """A minimal manifest for instantiating the plugin in tests."""
    return {
        "id": "intervals_running",
        "name": "Intervals.icu Running Stats",
        "version": "1.0.0",
    }


@pytest.fixture
def sample_config():
    """A valid plugin configuration for tests."""
    return {
        "athlete_id": "0",
        "api_key": "test_api_key_12345",
        "refresh_seconds": 3600,
    }


class MockResponse:
    """Minimal stand-in for requests.Response, enough for these tests."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def mock_response():
    """Factory fixture: mock_response(json_data, status_code=200)."""
    return MockResponse
