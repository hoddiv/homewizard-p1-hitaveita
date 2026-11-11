#!/usr/bin/env python3
"""Average hitaveita supply/return temperatures over trailing windows.

Answers "what return temperature (bakrásarhiti) am I actually getting?" — the
question that comes up whenever Icelandic homeowners compare notes. A spot
reading off the meter is close to useless: on this installation the return
temperature swings ~26–42 °C within a single day. Only an average is
comparable between houses.

Works straight off Home Assistant's recorder, so it needs no config changes
and no long-term statistics. (If you add `state_class: measurement` to the
temperature sensors — see docs/averaging.md — HA will keep hourly means
forever and you can read the same numbers off a statistics card instead.)

Note on the HA history API: `/api/history/period/<start>` defaults to a
**24-hour** window unless `end_time` is also given. This script fetches one
day at a time, which both avoids that trap and keeps responses small.

Usage
-----
    tools/temp_averages.py                     # 1/7/14/30-day windows
    tools/temp_averages.py --days 365          # add a 365-day window
    tools/temp_averages.py --daily 30          # per-day breakdown too
    tools/temp_averages.py --json
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import shlex
import subprocess
import sys
import urllib.parse

# Defaults match the entity_ids packages/hitaveita.yaml creates. Override them
# if you renamed the entities (HA slugifies the sensor *name*, so a rename in the
# entity registry leaves these pointing at nothing and every day is skipped).
SUPPLY = "sensor.hitaveita_framrasarhiti"   # Framrásarhiti
RETURN = "sensor.hitaveita_bakrasarhiti"    # Bakrásarhiti
FLOW = "sensor.hitaveita_rennsli"           # optional, used only as a weight

REMOTE = r'''
import json, os, urllib.request, urllib.parse
tok = open("/run/s6/container_environment/SUPERVISOR_TOKEN").read().strip()
a, b, ents = os.environ["A"], os.environ["B"], os.environ["ENTS"]
url = ("http://supervisor/core/api/history/period/%s?end_time=%s"
       "&filter_entity_id=%s&minimal_response&no_attributes"
       % (urllib.parse.quote(a, safe=""), urllib.parse.quote(b, safe=""), ents))
req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
print(json.dumps(json.load(urllib.request.urlopen(req, timeout=180))))
'''


def fetch_day(host: str, a: dt.datetime, b: dt.datetime, ents: str):
    env = {"A": a.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "B": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "ENTS": ents}
    pre = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
    cmd = ["ssh", "-o", "BatchMode=yes", host, f"{pre} python3 -c {shlex.quote(REMOTE)}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout)


def step_hold(pts, grid):
    """Zero-order hold: a sensor keeps its value until it next changes."""
    if not pts:
        return [None] * len(grid)
    ts = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    out = []
    for g in grid:
        i = bisect.bisect_right(ts, g) - 1
        out.append(vs[i] if i >= 0 else None)
    return out


def parse_block(block):
    """-> [(timestamp, value|None)]. `unavailable`/`unknown` is kept as a None
    transition rather than dropped: dropping it would make step_hold() extend the
    previous reading across the whole outage, counting missing measurements as
    observed ones and applying stale flow weights."""
    pts = []
    for s in block:
        try:
            v = float(s["state"])
        except (TypeError, ValueError):
            v = None
        t = dt.datetime.fromisoformat(s["last_changed"].replace("Z", "+00:00")).timestamp()
        pts.append((t, v))
    return pts


def summarise(rows):
    """rows = [(supply, return, flow|None)] at one-minute resolution."""
    n = len(rows)
    if not n:
        return None
    ms = sum(r[0] for r in rows) / n
    mr = sum(r[1] for r in rows) / n
    out = {"minutes": n, "supply": round(ms, 1), "return": round(mr, 1),
           "delta_t": round(ms - mr, 1),
           "return_min": round(min(r[1] for r in rows), 1),
           "return_max": round(max(r[1] for r in rows), 1)}
    fw = [r for r in rows if r[2]]
    W = sum(r[2] for r in fw) if fw else 0
    if W > 0:
        vs = sum(r[0] * r[2] for r in fw) / W
        vr = sum(r[1] * r[2] for r in fw) / W
        out.update(supply_flow_wtd=round(vs, 1), return_flow_wtd=round(vr, 1),
                   delta_t_flow_wtd=round(vs - vr, 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="root@homeassistant.local")
    ap.add_argument("--days", type=int, default=30, help="how far back to fetch (default 30)")
    ap.add_argument("--windows", default="1,7,14,30",
                    help="comma-separated trailing windows to report")
    ap.add_argument("--daily", type=int, default=0, help="also print the N most recent days")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--supply", default=SUPPLY, help="supply temperature entity_id")
    ap.add_argument("--return-entity", dest="return_entity", default=RETURN,
                    help="return temperature entity_id")
    ap.add_argument("--flow", default=FLOW,
                    help="flow entity_id, used only as a weight (any unit)")
    args = ap.parse_args()

    supply, ret, flow = args.supply, args.return_entity, args.flow
    ents = ",".join([supply, ret, flow])
    now = dt.datetime.now(dt.timezone.utc)
    per_day = []
    for d in range(args.days):
        a, b = now - dt.timedelta(days=d + 1), now - dt.timedelta(days=d)
        try:
            blocks = fetch_day(args.host, a, b, ents)
        except Exception as ex:                       # noqa: BLE001
            print(f"  day -{d}: fetch failed ({ex})", file=sys.stderr)
            continue
        pts = {}
        for blk in blocks:
            if blk:
                pts[blk[0]["entity_id"]] = parse_block(blk)
        if not pts.get(ret):
            continue
        grid = [a.timestamp() + i * 60 for i in range(1440)]
        S = step_hold(pts.get(supply, []), grid)
        R = step_hold(pts.get(ret, []), grid)
        F = step_hold(pts.get(flow, []), grid)
        rows = [(s, r, f) for s, r, f in zip(S, R, F) if s is not None and r is not None]
        per_day.append((d, a, rows))

    if not per_day:
        print("No data for %s / %s. If you renamed these entities, pass --supply / "
              "--return-entity (see --help)." % (supply, ret), file=sys.stderr)
        sys.exit(1)

    windows = [int(w) for w in args.windows.split(",") if w.strip()]
    result = {"generated": now.isoformat(timespec="seconds"), "windows": {}, "daily": []}
    for w in windows:
        rows = [r for d, _, day in per_day if d < w for r in day]
        s = summarise(rows)
        if s:
            result["windows"][f"{w}d"] = s
    for d, a, rows in per_day[: args.daily]:
        s = summarise(rows)
        if s:
            s["date"] = a.strftime("%Y-%m-%d")
            result["daily"].append(s)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Hitaveita supply/return averages  (°C, from HA recorder)\n")
    print(f"{'window':>8} | {'framrás':>8} | {'bakrás':>7} | {'ΔT':>5} | "
          f"{'bakrás range':>14} | flow-weighted")
    for key, s in result["windows"].items():
        fw = ""
        if "return_flow_wtd" in s:
            fw = (f"  framrás {s['supply_flow_wtd']}  bakrás {s['return_flow_wtd']}"
                  f"  ΔT {s['delta_t_flow_wtd']}")
        print(f"{key:>8} | {s['supply']:8.1f} | {s['return']:7.1f} | {s['delta_t']:5.1f} | "
              f"{s['return_min']:5.1f} – {s['return_max']:<6.1f} |{fw}")
    if result["daily"]:
        print("\nper day (most recent first)")
        for s in result["daily"]:
            print(f"  {s['date']}  framrás {s['supply']:5.1f}  bakrás {s['return']:5.1f}"
                  f"  ΔT {s['delta_t']:4.1f}  (min {s['return_min']:4.1f} max {s['return_max']:4.1f})")
    print("\nFor comparing with other households, quote ΔT and the period — supply "
          "temperature is set by the utility, not by your house.")


if __name__ == "__main__":
    main()
