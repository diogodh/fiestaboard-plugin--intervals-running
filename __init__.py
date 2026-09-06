"""Intervals.icu Running Stats plugin for FiestaBoard.

Fetches this year's running activities from Intervals.icu and aggregates
them into year-to-date totals (distance, moving time, run count),
including a computed average pace. Exposed as board template variables.

Authentication is a single long-lived API key (HTTP Basic auth, username
literally "API_KEY"). See
https://forum.intervals.icu/t/api-access-to-intervals-icu/609

Note on a previous approach: an earlier version of this plugin used the
`athlete-summary` endpoint, assuming it returned one pre-aggregated row
per athlete for an arbitrary date range. In practice it returns one row
per day (a rolling summary), so picking a single row badly understated
the totals. This version instead lists the athlete's activities directly
(GET /api/v1/athlete/{id}/activities) and sums them itself, which is
unambiguous -- each activity's own distance/moving_time is a real,
individual value, not part of a rolling window.
"""

import logging
from datetime import date
from typing import Any, Dict, List

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

INTERVALS_BASE_URL = "https://intervals.icu/api/v1"
REQUEST_TIMEOUT = 15

# Intervals.icu activity "type" values counted as a run for this board.
# TrailRun is deliberately excluded to match how the totals are filtered
# on intervals.icu's own Totals page ("Run, Virtual Run").
RUNNING_TYPES = {"Run", "VirtualRun"}


class IntervalsRunningPlugin(PluginBase):
    """Fetches and aggregates this year's running totals from Intervals.icu."""

    @property
    def plugin_id(self) -> str:
        """Return the plugin ID - must match manifest.json 'id' field."""
        return "intervals_running"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration. Return a list of error messages (empty if valid)."""
        errors = []
        if not config.get("athlete_id"):
            errors.append("Intervals.icu Athlete ID is required")
        if not config.get("api_key"):
            errors.append("Intervals.icu API Key is required")
        return errors

    @staticmethod
    def _year_start() -> str:
        """ISO date for January 1st of the current year."""
        today = date.today()
        return date(today.year, 1, 1).isoformat()

    @staticmethod
    def _format_duration_hm(moving_time_seconds: float) -> str:
        """Format total moving time as H:MM (hours:minutes), e.g. '87:24'."""
        total_minutes = int(round(moving_time_seconds / 60))
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}:{minutes:02d}"

    @staticmethod
    def _format_pace(moving_time_seconds: float, distance_meters: float) -> str:
        """Format average pace as M:SS per kilometer."""
        if not distance_meters:
            return "0:00"
        distance_km = distance_meters / 1000
        seconds_per_km = moving_time_seconds / distance_km
        minutes, seconds = divmod(int(round(seconds_per_km)), 60)
        return f"{minutes}:{seconds:02d}"

    def fetch_data(self) -> PluginResult:
        """Fetch this year's activities and aggregate running totals."""
        athlete_id = self.config.get("athlete_id")
        api_key = self.config.get("api_key")

        if not athlete_id or not api_key:
            return PluginResult(
                available=False, error="Athlete ID and API key are required"
            )

        try:
            response = requests.get(
                f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/activities",
                params={
                    "oldest": self._year_start(),
                    "fields": "type,distance,moving_time",
                    # Without an explicit limit the API silently caps how many
                    # activities it returns, which under-counted a full year
                    # of activity for an active athlete. 5000 comfortably
                    # covers any realistic single-year activity count.
                    "limit": 5000,
                },
                # Intervals.icu personal API keys authenticate via HTTP Basic
                # auth with the literal username "API_KEY".
                auth=("API_KEY", api_key),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            activities = response.json()

            if not isinstance(activities, list):
                return PluginResult(
                    available=False, error="Unexpected response from Intervals.icu"
                )

            distance_meters = 0.0
            moving_time_seconds = 0.0
            run_count = 0

            for activity in activities:
                if not isinstance(activity, dict):
                    continue
                if activity.get("type") not in RUNNING_TYPES:
                    continue
                run_count += 1
                distance_meters += activity.get("distance") or 0
                moving_time_seconds += activity.get("moving_time") or 0

            data = {
                "distance_km": f"{distance_meters / 1000:.0f}",
                "moving_time_hours": self._format_duration_hm(moving_time_seconds),
                "avg_pace": self._format_pace(moving_time_seconds, distance_meters),
                "run_count": str(run_count),
            }

            return PluginResult(available=True, data=data)

        except requests.RequestException as e:
            logger.warning("Network error fetching Intervals.icu data: %s", e)
            return PluginResult(
                available=False, error="Network error contacting Intervals.icu"
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error("Unexpected Intervals.icu response format: %s", e)
            return PluginResult(
                available=False, error="Unexpected response from Intervals.icu"
            )
        except Exception as e:  # noqa: BLE001 - fetch_data must never raise
            logger.exception("Unexpected error in %s", self.plugin_id)
            return PluginResult(available=False, error=str(e))
