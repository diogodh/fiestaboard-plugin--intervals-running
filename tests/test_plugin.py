"""Tests for the Intervals.icu Running Stats plugin."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest


ACTIVITIES_RESPONSE = [
    {"type": "Run", "distance": 10000, "moving_time": 3600},  # 10km in 1h
    {"type": "Run", "distance": 5000, "moving_time": 1800},  # 5km in 30min
    {"type": "Ride", "distance": 40000, "moving_time": 5400},  # not a run
    {"type": "TrailRun", "distance": 15000, "moving_time": 5400},  # excluded on purpose
    {"type": "VirtualRun", "distance": 15000, "moving_time": 5400},  # counts as a run
]
# Expected totals: Run(10000+5000) + VirtualRun(15000) = 30000m, 3 activities
# moving_time: 3600+1800+5400 = 10800s (3h) -> pace 10800/30 = 360s/km = 6:00


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


class TestYearStart:
    def test_year_start_is_january_first_of_current_year(self, plugin_module):
        expected = date(date.today().year, 1, 1).isoformat()
        assert plugin_module.IntervalsRunningPlugin._year_start() == expected


class TestFormatDurationHM:
    def test_format_duration_exact_hours(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(10800) == "3:00"

    def test_format_duration_with_minutes(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(314640) == "87:24"

    def test_format_duration_zero_padded_single_digit_minutes(self, plugin_module):
        # 87h 4m = 313440s -> must be "87:04", not "87:4"
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(313440) == "87:04"

    def test_format_duration_rounds_to_nearest_minute(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(61) == "0:01"

    def test_format_duration_zero(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(0) == "0:00"

    def test_format_duration_minutes_roll_over_to_hour(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_duration_hm(3590) == "1:00"


class TestFormatPace:
    def test_format_pace_normal(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(10800, 30000) == "6:00"

    def test_format_pace_rounds_seconds(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(301, 1000) == "5:01"

    def test_format_pace_zero_distance(self, plugin_module):
        assert plugin_module.IntervalsRunningPlugin._format_pace(0, 0) == "0:00"


class TestFetchData:
    def test_fetch_data_sums_run_and_virtualrun_only(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(ACTIVITIES_RESPONSE)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data["run_count"] == "3"
        assert result.data["distance_km"] == "30"
        assert result.data["moving_time_hours"] == "3:00"
        assert result.data["avg_pace"] == "6:00"

    def test_fetch_data_excludes_trail_run(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        """TrailRun must never be counted, per explicit user request."""
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        response = [{"type": "TrailRun", "distance": 99999, "moving_time": 99999}]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "0"
        assert result.data["distance_km"] == "0"

    def test_fetch_data_uses_basic_auth_and_year_start(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response([])
            plugin.fetch_data()

        _, kwargs = mock_get.call_args
        assert kwargs["auth"] == ("API_KEY", sample_config["api_key"])
        assert kwargs["params"]["oldest"] == plugin_module.IntervalsRunningPlugin._year_start()
        assert kwargs["params"]["limit"] >= 1000  # must not silently truncate a year of activity

    def test_fetch_data_empty_activity_list(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response([])
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "0"
        assert result.data["distance_km"] == "0"
        assert result.data["avg_pace"] == "0:00"

    def test_fetch_data_handles_null_fields_gracefully(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        activities = [{"type": "Run", "distance": None, "moving_time": None}]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(activities)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "1"
        assert result.data["distance_km"] == "0"

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

    def test_fetch_data_skips_non_dict_entries(
        self, plugin_module, sample_manifest, sample_config, mock_response
    ):
        plugin = _make_plugin(plugin_module, sample_manifest, sample_config)
        response = ["not-a-dict", {"type": "Run", "distance": 1000, "moving_time": 300}]

        with patch.object(plugin_module.requests, "get") as mock_get:
            mock_get.return_value = mock_response(response)
            result = plugin.fetch_data()

        assert result.available is True
        assert result.data["run_count"] == "1"


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
            mock_get.return_value = mock_response(ACTIVITIES_RESPONSE)
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
