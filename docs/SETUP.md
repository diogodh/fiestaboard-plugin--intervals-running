# Setup Guide — Intervals.icu Running Stats

This plugin needs two things from Intervals.icu: your **Athlete ID** and
an **API Key**. Unlike Strava, there's no OAuth authorization step — just
generate a key once and you're done.

## 1. Generate an API key

1. Log into <https://intervals.icu> and go to **Settings**.
2. Scroll to the bottom and find **Developer Settings**.
3. Generate an API key and copy it. Keep it secret — anyone with this key
   can read your Intervals.icu data.

## 2. Find your Athlete ID (optional)

You almost certainly don't need this step. Just leave the **Athlete ID**
field set to its default, `0`, which always means "the account this API
key belongs to."

If you ever do need your real athlete id (e.g. to look at someone you
coach), it's in the URL when you're logged in — it looks like `i1234567`.

## 3. Install the plugin in FiestaBoard

This is a personal/external plugin, so install it via a git URL. The
easiest way is directly from the web UI:

1. Open your FiestaBoard's web UI and log in.
2. Go to **Integrations**.
3. Click **Add from Git**.
4. Paste: `https://github.com/diogodh/fiestaboard-plugin--intervals-running`
5. Confirm — FiestaBoard clones and loads it automatically.

(If you'd rather use the API directly, `POST /api/plugins/install` with
`{"repository": "https://github.com/diogodh/fiestaboard-plugin--intervals-running"}`
works too, but requires you to be logged in — see your FiestaBoard's own
docs on session auth for the request.)

## 4. Configure it

1. In **Integrations**, find **Intervals.icu Running Stats** and enable it.
2. Leave **Athlete ID** as `0` unless you have a reason to change it.
3. Paste your **API Key** from step 1.
4. (Optional) Adjust **Refresh Interval** — default is 1 hour.

## 5. Use it on a page

Available template variables:

| Variable                                 | Example | Meaning                          |
| ----------------------------------------- | ------- | --------------------------------- |
| `{{intervals_running.distance_km}}`       | `842`   | Lifetime running distance, km (rounded) |
| `{{intervals_running.moving_time_hours}}` | `87:24` | Lifetime running time, hours:minutes    |
| `{{intervals_running.avg_pace}}`          | `5:12`  | Average pace, minutes:seconds/km |
| `{{intervals_running.run_count}}`         | `91`    | Number of runs recorded          |

FiestaBoard also supports typing `{{blue}}`, `{{yellow}}`, `{{green}}`,
`{{red}}`, `{{orange}}`, `{{violet}}`, `{{white}}`, or `{{black}}`
directly into a page — each renders as one colored tile on the physical
board (one tile = one character position). A compact layout that fits a
15×3 Vestaboard Note, with a different color marking each stat:

```text
{{blue}} {{intervals_running.distance_km}} km
{{yellow}} {{intervals_running.moving_time_hours}} {{green}} {{intervals_running.run_count}}x
{{red}} {{intervals_running.avg_pace}}/km
```

Which renders as three lines: a blue tile then "842 km"; a yellow tile,
"87:24", a green tile, and "91x"; and a red tile then "5:12/km". Feel
free to swap in whichever colors you like from the list above, or use
the wider layout from the earlier examples if you have a larger board.

## Troubleshooting

- **401/403 errors**: double-check the API key was copied without extra
  spaces, and that you haven't regenerated/cleared it since.
- **Numbers look wrong**: this plugin counts activities in the `Run`,
  `TrailRun`, and `VirtualRun` categories (there's no separate `Treadmill`
  category on Intervals.icu — treadmill runs are just `Run`). If some of
  your runs got categorized differently (e.g. imported from another
  device under an unusual type), they won't be counted. Check the
  activity's type on its page in Intervals.icu.
- **Numbers include activities from a coach/teammate**: make sure
  Athlete ID is `0` (or explicitly your own id), not someone else's.
