# Intervals.icu Running Stats — FiestaBoard Plugin

Shows your lifetime running totals from Intervals.icu on your split-flap
board: total distance, total moving time, average pace, and number of runs.

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

Strava exposes a pre-aggregated lifetime-totals endpoint; Intervals.icu's
closest equivalent is `athlete-summary`, which is normally used by coaches
to see rollups for the athletes they follow. Called with a wide `start`
date, it returns each athlete's activity counts, distance, and moving
time **pre-aggregated per sport category** for that range — so no need to
download and sum the raw activity list:

```
GET /api/v1/athlete/{id}/athlete-summary?start=2000-01-01&end=<today>
```

This plugin:

1. Calls that endpoint (`HISTORY_START` in `__init__.py` controls how far
   back `start` goes — push it further back if you trained before 2000).
2. Picks the summary entry for "you" (see **Multiple athletes** below).
3. Reads its `byCategory` list and sums the entries whose `category` is
   `Run`, `TrailRun`, or `VirtualRun` (`RUNNING_CATEGORIES` in
   `__init__.py`) — each category entry already has `count`, `distance`
   (meters), and `moving_time` (seconds) pre-summed by Intervals.icu.
4. Derives the board values:
   - `distance_km` = `distance / 1000`, rounded to a whole number
   - `moving_time_hours` = `moving_time` formatted as `H:MM`
     (hours:minutes, e.g. `87:24`)
   - `avg_pace` = `moving_time / (distance / 1000)`, formatted `M:SS`
   - `run_count` = the summed category counts

This was verified against the official OpenAPI spec (via the community
[`jcurbelo/intervals-icu-sdk`](https://github.com/jcurbelo/intervals-icu-sdk)
repo, which tracks it), specifically the `SummaryWithCats` and
`CategorySummary` schemas. Note there is **no `Treadmill` category** in
the enum, despite what you might expect from other platforms — treadmill
runs are presumably logged as plain `Run`.

### Athlete ID

Intervals.icu lets you pass `0` as the athlete id on any endpoint that
takes one, meaning "the athlete this API key belongs to". This plugin
defaults to `"0"` so most users never need to look up their real id
(which looks like `i1234567`).

### Multiple athletes (coaches)

`athlete-summary` is built for coaches and can return one entry per
followed athlete rather than just you. For a personal, non-coaching
account this isn't a concern — you'll only ever get one entry back. If
you *are* a coach and this plugin picks the wrong athlete, set **Athlete
ID** to your own real id (not `0`) in the plugin settings; the plugin
will then match on `athlete_id` explicitly instead of guessing.

## Rate limits

API-key callers are limited to **5,000 requests/day** and **2,500 per
rolling 15-minute window**. This plugin uses exactly 1 request per fetch
cycle, so even the minimum `refresh_seconds` of 900 (15 minutes) uses a
tiny fraction of that budget.

## Files

- `manifest.json` — metadata, settings schema, declared variables
- `__init__.py` — `IntervalsRunningPlugin(PluginBase)` implementation
- `tests/` — pytest suite (93% line coverage on `__init__.py`)
- `docs/SETUP.md` — user-facing setup guide
