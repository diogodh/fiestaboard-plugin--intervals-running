# Intervals.icu Running Stats — FiestaBoard Plugin

Shows this year's running totals from Intervals.icu on your split-flap
board: year-to-date distance, moving time, average pace, and number of
runs (`Run` and `VirtualRun` only).

## How it works

Intervals.icu authentication is a single long-lived **API key** — no
OAuth, no token refresh, no expiry to manage. You generate it once
(Settings → Developer Settings) and it stays valid until you regenerate
or clear it yourself. Requests authenticate with HTTP Basic auth using
the literal username `API_KEY` and the key itself as the password:

```python
requests.get(url, auth=("API_KEY", api_key))
```

This is documented at
<https://forum.intervals.icu/t/api-access-to-intervals-icu/609>.

### Where the totals come from

This plugin lists the athlete's activities directly:

```
GET /api/v1/athlete/{id}/activities?oldest=<Jan 1 of current year>&fields=type,distance,moving_time
```

...and sums them itself:

1. `_year_start()` computes January 1st of the current year, fresh on
   every fetch — the totals automatically reset each new year with no
   configuration needed.
2. Every returned activity is checked against `RUNNING_TYPES` — only
   `Run` and `VirtualRun` count (matching how the totals are filtered on
   intervals.icu's own **Totals** page). `TrailRun` is intentionally
   excluded.
3. Matching activities' `distance` (meters) and `moving_time` (seconds)
   are summed, and counted for `run_count`. The request explicitly sets
   `limit=5000` — without it, the API silently caps how many activities
   it returns per call, which under-counted a full year of activity for
   an active athlete (real totals like 233 runs / 2,380 km showed up as
   189 / 1,902 km). 5,000 comfortably covers any realistic single-year
   activity count across all sports, not just running.
4. Derives the board values:
   - `distance_km` = `distance / 1000`, rounded to a whole number
   - `moving_time_hours` = `moving_time` formatted as `H:MM`
   - `avg_pace` = `moving_time / (distance / 1000)`, formatted `M:SS`
   - `run_count` = the count of matching activities

### A dead end worth knowing about (in case you ever revisit this)

An earlier version of this plugin used `GET /athlete/{id}/athlete-summary`
instead, assuming a wide `start`/`end` range would return one
pre-aggregated row per athlete for that whole range (like Strava's
lifetime-totals endpoint). In practice it returns **one row per day**
(a rolling summary) — so taking a single row badly understated the
totals (real numbers like 2,467 km / 246 runs showed up on the board as
something like 75 km / 9 runs). Listing and summing individual
activities, as this version does, has no such ambiguity: each
activity's `distance`/`moving_time` is its own real value, never part of
a rolling window.

### Athlete ID

Intervals.icu lets you pass `0` as the athlete id on any endpoint that
takes one, meaning "the athlete this API key belongs to". This plugin
defaults to `"0"` so most users never need to look up their real id
(which looks like `i1234567`).

## Rate limits

API-key callers are limited to **5,000 requests/day** and **2,500 per
rolling 15-minute window**. This plugin uses exactly 1 request per fetch
cycle, so even the minimum `refresh_seconds` of 900 (15 minutes) uses a
tiny fraction of that budget.

## Files

- `manifest.json` — metadata, settings schema, declared variables
- `__init__.py` — `IntervalsRunningPlugin(PluginBase)` implementation
- `tests/` — pytest suite (98% line coverage overall)
- `docs/SETUP.md` — user-facing setup guide
