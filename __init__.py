"""Intervals.icu Running Stats plugin for FiestaBoard.

Fetches the athlete's lifetime running totals from Intervals.icu and
exposes them as board template variables, including a computed average
pace.

Unlike Strava, Intervals.icu has no OAuth dance for personal use --
authentication is a single long-lived API key (HTTP Basic auth, username
literally "API_KEY"). See
https://forum.intervals.icu/t/api-access-to-intervals-icu/609

Totals come from the athlete-summary endpoint
(GET /api/v1/athlete/{id}/athlete-summary), which returns activity counts,
distance and moving time pre-aggregated by sport category for a given date
range -- confirmed against the official OpenAPI spec published at
https://github.com/jcurbelo/intervals-icu-sdk/blob/main/spec/intervals-openapi.normalized.json
(schemas SummaryWithCats / CategorySummary). This is one lightweight
request instead of downloading and summing the athlete's entire activity
history.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

INTERVALS_BASE_URL = "https://intervals.icu/api/v1"
REQUEST_TIMEOUT = 10

# Intervals.icu "category" values (CategorySummary.category in the OpenAPI
# spec) that count as a run. Confirmed against the spec's enum -- note
# there is no "Treadmill" category, despite what you might expect from
# other platforms.
RUNNING_CATEGORIES = {"Run", "TrailRun", "VirtualRun"}

# Far enough back to capture a lifetime of activity in a single request.
# If you started training before this date, push it back further.
HISTORY_START = "2000-01-01"


class IntervalsRunningPlugin(PluginBase):
    """Fetches and aggregates lifetime running totals from Intervals.icu."""

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
    def _format_pace(moving_time_seconds: float, distance_meters: float) -> str:
        """Format average pace as M:SS per kilometer."""
        if not distance_meters:
            return "0:00"
        distance_km = distance_meters / 1000
        seconds_per_km = moving_time_seconds / distance_km
        minutes, seconds = divmod(int(round(seconds_per_km)), 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _select_own_summary(
        summaries: List[Dict[str, Any]], athlete_id: str
    ) -> Optional[Dict[str, Any]]:
        """Pick the summary entry that represents this athlete.

        athlete-summary is designed for coaches and can return one entry
        per followed athlete. For a personal (non-coaching) account there
        is normally exactly one entry. If a real athlete id (not "0") was
        configured, prefer matching it explicitly; otherwise fall back to
        the first entry.
        """
        if not summaries:
            return None
        if len(summaries) == 1:
            return summaries[0]
        if athlete_id and athlete_id != "0":
            wanted = athlete_id.lstrip("i")
            for summary in summaries:
                if str(summary.get("athlete_id", "")).lstrip("i") == wanted:
                    return summary
        # Ambiguous multi-athlete response with no explicit id to match --
        # best effort, but see docs/SETUP.md for how to disambiguate.
        return summaries[0]

    def fetch_data(self) -> PluginResult:
        """Fetch the athlete's lifetime running totals."""
        athlete_id = self.config.get("athlete_id")
        api_key = self.config.get("api_key")

        if not athlete_id or not api_key:
            return PluginResult(
                available=False, error="Athlete ID and API key are required"
            )

        try:
            response = requests.get(
                f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/athlete-summary",
                params={
                    "start": HISTORY_START,
                    "end": date.today().isoformat(),
                },
                # Intervals.icu personal API keys authenticate via HTTP Basic
                # auth with the literal username "API_KEY".
                auth=("API_KEY", api_key),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            summaries = response.json()

            if not isinstance(summaries, list):
                return PluginResult(
                    available=False, error="Unexpected response from Intervals.icu"
                )

            own_summary = self._select_own_summary(summaries, athlete_id)
            if own_summary is None:
                return PluginResult(
                    available=False,
                    error="Intervals.icu returned no summary data for this athlete",
                )

            categories = own_summary.get("byCategory") or []

            distance_meters = 0.0
            moving_time_seconds = 0.0
            run_count = 0

            for category in categories:
                if not isinstance(category, dict):
                    continue
                if category.get("category") not in RUNNING_CATEGORIES:
                    continue
                run_count += category.get("count") or 0
                distance_meters += category.get("distance") or 0
                moving_time_seconds += category.get("moving_time") or 0

            data = {
                "distance_km": f"{distance_meters / 1000:.1f}",
                "moving_time_hours": f"{moving_time_seconds / 3600:.1f}",
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
