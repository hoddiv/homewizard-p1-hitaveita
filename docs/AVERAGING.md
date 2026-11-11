# Average supply and return temperature — and how to compare them with other households

Sooner or later someone asks: *"what bakrásarhiti (return temperature) are you getting?"*
It is a good question, but a reading off the meter display is close to useless as an answer.
On one real installation the return temperature swings between **26 °C and 42 °C within a single
day**. Whatever number you happen to glance at says more about the time of day than about your
house. Only an average is comparable.

## Which number actually means something

| | who controls it | useful for comparison? |
|---|---|---|
| **Framrásarhiti** (supply) | the utility | **No** — mostly tells you where you sit on the network |
| **Bakrásarhiti** (return) | your house | Yes, but partly depends on how hard you are drawing |
| **ΔT = supply − return** | your house | **Best single number** |
| **kWh/m³** = energy ÷ volume | your house | Best of all, if your meter has an energy register |

Icelandic hitaveita is billed by **volume**, not energy. So every kelvin of ΔT is heat you got for
free. A high return temperature means you are paying for water whose heat you did not extract.
That is why ΔT, not the supply temperature, is the number worth comparing.

Supply temperature is also strongly seasonal — on the reference installation it rose from 77.3 °C
to 82.1 °C over a single November month as the utility responded to the cold. Anyone quoting a
July figure is not describing the same thing.

## How long a window?

**Use a rolling 365 days as the headline figure, and 30 days for "what is it doing now".**

- **365 days rolling** includes every season exactly once with equal weight, and is comparable
  between households *regardless of when each person installed their meter*. That is the number to
  post when someone asks.
- **30 days** tells you what your system is doing at the moment, which is what you want when you
  change something and ask "did that help?".
- **Avoid an all-time / lifetime average.** It is tempting because it needs no choices, but it is
  dominated by how long you have had the meter — so two people's numbers are not comparable — and
  it barely moves when you actually fix something, which makes it useless as feedback.

### Should every measurement count?

Within a window, yes — do not filter by time of day or cherry-pick. But there is one real caveat:

**a return temperature measured while no water is flowing is meaningless.** It is just the
stagnant water in the meter drifting toward room temperature. If your system circulates
continuously, this does not matter: on the reference installation, flow-weighting changed the
answer by only **0.2–0.3 K**, so a plain time-average is honest. If your circulation stops for long
periods — many houses in summer — a plain time-average will quietly drag your reported return
temperature toward room temperature and flatter you. In that case weight by flow.

`tools/temp_averages.py` reports both, so you can see whether it matters for your system.

## Getting it in Home Assistant

### 1. Let HA keep long-term statistics

`packages/hitaveita.yaml` sets this for you. If you are running an older copy, note that without
a `state_class` Home Assistant keeps **no long-term statistics** for these sensors — only raw
recorder history, which is purged (10 days by default). Add `state_class: measurement` to both:

```yaml
      - name: "Hitaveita – Framrásarhiti"
        unique_id: hitaveita_supply_c
        device_class: temperature
        state_class: measurement        # <-- keeps hourly/daily mean, min, max forever
        unit_of_measurement: "°C"
```

HA then stores hourly and daily mean/min/max indefinitely, surviving recorder purges.

> **Home Assistant does not backfill this by itself.** Statistics are generated from the moment
> you add `state_class`, so a 365-day average would normally read empty for a year — even though
> the recorder already holds months of raw history for that entity.
>
> **You can rebuild it:** `tools/backfill_statistics.py` reconstructs the missing hourly
> statistics (time-weighted mean, min, max) from the `states` table and imports them through the
> supported `recorder/import_statistics` websocket command. On the reference installation this
> recovered **3 273 hourly points back to 28 June** — 4.5 months — so the 30-day and 365-day cards
> had real values immediately instead of in a year's time.
>
> It runs on the Home Assistant machine, is a dry run unless you pass `--import`, never touches the
> current hour, and refuses sum/total statistics (it only handles mean-type, so it cannot corrupt a
> cumulative series the way an energy counter can):
>
> ```
> scp tools/backfill_statistics.py root@homeassistant.local:/tmp/
> ssh root@homeassistant.local 'python3 /tmp/backfill_statistics.py \
>     --entities sensor.hitaveita_framrasarhiti,sensor.hitaveita_bakrasarhiti'
> # check the dry run, then repeat with --import
> ```
>
> `tools/temp_averages.py` remains useful either way — it reads raw recorder history directly and
> needs no config change at all.

### 2. A ΔT sensor — you may already have it

ΔT is the number worth comparing, and it needs `state_class: measurement` too so that it gets
long-term statistics. **The optional `packages/hitaveita_monitor.yaml` already provides it** as
`sensor.hitaveita_delta_t`, correctly configured (no `device_class`, because marking a temperature
*difference* as `temperature` would apply the absolute °C↔°F conversion with its +32 offset).

If you run the monitoring package, there is nothing to add — just use that entity. Do **not**
define your own with `unique_id: hitaveita_delta_t` as well; Home Assistant will refuse the second
one as a duplicate.

### 3. Dashboard cards

Once statistics exist, averages need no extra sensors — the built-in `statistic` card reads them:

```yaml
type: horizontal-stack
cards:
  - type: statistic
    entity: sensor.hitaveita_bakrasarhiti
    stat_type: mean
    name: Bakrás — 30 d
    period:
      rolling_window:
        duration: { days: 30 }
  - type: statistic
    entity: sensor.hitaveita_bakrasarhiti
    stat_type: mean
    name: Bakrás — 365 d
    period:
      rolling_window:
        duration: { days: 365 }
  - type: statistic
    entity: sensor.hitaveita_delta_t
    stat_type: mean
    name: ΔT — 365 d
    period:
      rolling_window:
        duration: { days: 365 }
```

A trend view, which also shows the daily spread that makes spot readings so misleading:

```yaml
type: statistics-graph
title: Framrás / bakrás
entities:
  - sensor.hitaveita_framrasarhiti
  - sensor.hitaveita_bakrasarhiti
days_to_show: 365
period: day
stat_types: [mean, min, max]
```

### 4. Or just run the script

```
tools/temp_averages.py                 # 1/7/14/30-day windows
tools/temp_averages.py --days 365 --windows 30,365
tools/temp_averages.py --daily 14      # per-day breakdown
```

It defaults to the entity_ids this package creates. **If you renamed the sensors**, Home Assistant
slugifies the *name*, so the entity_ids change and the defaults will match nothing — pass them
explicitly:

```
tools/temp_averages.py \
    --supply sensor.my_supply_temperature \
    --return-entity sensor.my_return_temperature \
    --flow sensor.my_flow
```

It reads HA's recorder over SSH, needs no config changes, and reports both plain and
flow-weighted averages.

> **Watch out:** HA's `/api/history/period/<start>` returns only a **24-hour** window unless you
> also pass `end_time`. Ask for 30 days without it and you silently get a single day from a month
> ago. The script fetches day by day to avoid this.

## A worked example

From the reference installation, 2026-11-11:

| window | framrás | bakrás | ΔT |
|---|---|---|---|
| 24 h | 82.1 | 39.3 | 42.8 |
| 7 days | 80.5 | 39.3 | 41.2 |
| 14 days | 79.4 | 38.6 | 40.9 |
| 30 days | 78.2 | 37.8 | 40.4 |

Reported as: *"bakrás ~38 °C, framrás ~78 °C, ΔT ~40 K, 30-day average, November."*

---

## Aside: check what unit your energy register really uses

Worth doing before you trust `Hitaveita – Orka` or put it on the Energy dashboard. **Some meters
mislabel it in the telegram.** On the reference meter the telegram says:

```
0-1:24.2.5(0201.910*Wh)
```

…but the value is **MWh**. Two cross-checks, both of which you can do yourself:

1. **Lifetime sanity.** Multiply your lifetime volume by a plausible 45–55 kWh/m³. Here:
   3745 m³ × 50 ≈ **187 MWh**, against a reading of 201.91. Consistent with MWh, nowhere near Wh.
2. **Energy against volume.** Take both readings a week apart, then

   ```
   implied ΔT (K) = Δenergy_in_kWh / (Δvolume_in_m³ × 1.163)
   ```

   and compare with the ΔT your thermometers actually show. Here Δ0.184 against 3.265 m³ gives
   48.5 K if the unit is MWh — matching the measured ~45 K — while Wh and kWh give ≈0 and GJ gives
   13.5 K, which contradicts the thermometers.

### Fixing a mislabelled unit — read this first

The obvious fix is to edit `unit_of_measurement`. **On a `total_increasing` sensor that already has
statistics, that does not work**, and it is worth understanding why before you try it.

Because `Wh` and `MWh` are inter-convertible for `device_class: energy`, Home Assistant does **not**
treat the edit as a relabel. It *converts*: the entity's value is rescaled (201.913 → 201 913 000)
while the recorded history stays on the old scale. The next statistics run sees a jump of six orders
of magnitude and records it as consumption. In the case this was found, that was a bogus **201.9 GWh
spike** in `statistics_short_term`, caught only because the hourly roll-up had not run yet.

So pick one:

- **Leave it and document it.** Hitaveita is billed by volume, so the energy register is secondary —
  `Rúmmál` and the cost sensors are unaffected. This is the low-risk option, and it is why the
  package ships Orka with **no `state_class`**: HA then builds no long-term statistics from it and
  does not offer it to the Energy dashboard.
- **Clear, then relabel.** Developer Tools → Statistics → delete the statistics for the energy
  entity, *then* change the unit. Correct from then on, at the cost of the accumulated energy
  history. Volume history is untouched either way.

If you do experiment, check afterwards for a spike before the hourly roll-up cements it:

```sql
-- read-only; HA keeps short-term statistics for ~10 days
SELECT start_ts, state, sum FROM statistics_short_term
WHERE metadata_id = (SELECT id FROM statistics_meta
                     WHERE statistic_id = 'sensor.hitaveita_orka')
ORDER BY start_ts DESC LIMIT 10;
```
