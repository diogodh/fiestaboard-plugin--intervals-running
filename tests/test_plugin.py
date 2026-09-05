"""Tests for the Intervals.icu Running Stats plugin."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _summary(athlete_id, categories):
    return {"athlete_id": athlete_id, "byCategory": categories}


RUN_CATEGORY = {"category": "Run", "count": 2, "distance": 15000, "moving_time": 5400}
TRAIL_RUN_CATEGORY = {"category": "TrailRun", "count": 1, "distance": 15000, "moving_time": 5400}
RIDE_CATEGORY = {"category": "Ride", "count": 5, "distance": 200000, "moving_time": 30000}

# Totals across Run + TrailRun: 3 runs, 30000m, 10800s (3h) -> 6:00/km pace
SINGLE_ATHLETE_RESPONSE = [
    _summary("i123", [RUN_CATEGORY, TRAIL_RUN_CATEGORY, RIDE_CATEGORY])
]


def _make_plugin(plugin_module, manifest, config=None):
    plugin = plugin_module.IntervalsRunningPlugin(manifest)
    if config is not None:
        plugin.config = config
    return plugin


class TestPluginIdentity:
    def test_plugin_id(self, plugin_module, sample_manifest):
        plugin = _make_plugin(plugin_module, sample_manifest)
        assert plugin.plugin_id == "intervals_running"


class TestValidateConfig:
    def test_validate_config_valid(self, plugin_module, sample_manifest, sample_config):
        plugin = _make_plugin(plugin_module, sample_manifest)
        assert plugin.validate_config(sample_config) == []

    def test_validate_config_missing_athlete_id(self, plugin_module, sample_manifest):
        plugin = _make_plugin(plugin_module, sample_manifest)
        errors = plugin.validate_config({"api_key": "x"})
        assert any("Athlete ID" in e for e in errors)

    def test_validate_config_missing_api_key(self, plugin_module, sample_manifest):
        plugin = _make_plugin(plugin_module, sample_manifest)
        errors = plugin.validate_config({"athlete_id": "0"})
        assert any("API Key" in e for e in errors)

    def test_validate_config_missing_both(self, plugin_module, sample_manifest):
        plugin = _make_plugin(plugin_module, sample_manifest)
        assert len(plugin.validate_config({})) == 2


class TestFormatPace:
    def test_format_pace_normal(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(10800, 30000) == "6:00"

    def test_format_pace_rounds_seconds(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(301, 1000) == "5:01"

    def test_format_pace_zero_distance(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(0, 0) == "0:00"


class TestSelectOwnSummary:
    def test_empty_list_returns_none(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._select_own_summary([], "0") is None

    def test_single_entry_is_used_regardless_of_id(self, plugin_module):
        summaries = [_summary("i999", [])]
        result = plugin_module.IntervalsRunningPlugin._select_own_summary(summaries, "0")
        assert result["athlete_id"] == "i999"

    def test_multiple_entries_matches_configured_athlete_id(self, plugin_module):
        summaries = [_summary("i111", []), _summary("i222", [])]
        result = plugin_module.IntervalsRunningPlugin._select_own_summary(summaries, "i222")
        assert result["athlete_id"] == "i222"

    def test_multiple_entries_matches_id_without_i_prefix(self, plugin_module):
        summaries = [_summary("i111", []), _summary("i222", [])]
        result = plugin_module.IntervalsRunningPlugin._select_own_summary(summaries, "222")
        assert result["athlete_id"] == "i222"

    def test_multiple_entries_falls_back_to_first_when_ambiguous(self, plugin_module):
        summaries = [_summary("i111", []), _summary("i222", [])]
        result = plugin_module.IntervalsRunningPlugin._select_own_summary(summaries, "0")
        assert result["athlete_id"] == "i111"


class TestFetchData:
    def test_fetch_data_sums_running_categories_only(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(SINGLE_ATHLETE_RESPONSE)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data["run_count"] == "3"
        assert result.data["distance_km"] == "30.0"
        assert result.data["moving_time_hours"] == "3.0"
        assert result.data["avg_pace"] == "6:00"

    def test_fetch_data_uses_basic_auth_with_api_key_username(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response([])
            plugin.fetch_data()

        _, kwargs = mock_get.call_args
        assert kwargs["auth"] == ("API_KEY", sample_config["api_key"])
        assert kwargs["params"]["start"] == plugin_module.HISTORY_START

    def test_fetch_data_empty_summary_list(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response([])
            result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    def test_fetch_data_no_running_categories(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        """An athlete who has never logged a run should get clean zeros."""
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        response = [_summary("i123", [RIDE_CATEGORY])]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "0"
        assert result.data["distance_km"] == "0.0"
        assert result.data["avg_pace"] == "0:00"

    def test_fetch_data_missing_byCategory_key(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        response = [{"athlete_id": "i123"}]  # no byCategory at all

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "0"

    def test_fetch_data_handles_null_fields_gracefully(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        category = {"category": "Run", "count": 1, "distance": None, "moving_time": None}
        response = [_summary("i123", [category])]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "1"
        assert result.data["distance_km"] == "0.0"

    def test_fetch_data_missing_config_skips_network_call(
        self, plugin_module, sample_manifest
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, {})

        with patch.object(plugin_module.requests, "get") as mock_get:
            result = plugin.fetch_data()

        assert result.available is False
        mock_get.assert_not_called()

    def test_fetch_data_network_error(self, plugin_module, sample_manifest, sample_config):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.side_effect = plugin_module.requests.RequestException("timeout")
            result = plugin.fetch_data()

        assert result.available is False
        assert "Intervals.icu" in result.error

    def test_fetch_data_http_error(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response({}, status_code=401)
            result = plugin.fetch_data()

        assert result.available is False

    def test_fetch_data_malformed_response_not_a_list(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response({"error": "not a list"})
            result = plugin.fetch_data()

        assert result.available is False
        assert "Unexpected response" in result.error

    def test_fetch_data_skips_non_dict_category_entries(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        response = [_summary("i123", ["not-a-dict", RUN_CATEGORY])]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "2"


class TestManifestConsistency:
    def test_data_keys_match_declared_variables(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        declared_vars = manifest["variables"]["simple"]

        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(SINGLE_ATHLETE_RESPONSE)
            result = plugin.fetch_data()

        assert result.available
        for var in declared_vars:
            assert var in result.data, f"Variable '{var}' declared in manifest but missing from data"

    def test_manifest_id_matches_plugin_id(self, plugin_module, sample_manifest):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        plugin = _make_plugin(plugin_module, sample_manifest)
        assert manifest["id"] == plugin.plugin_id
