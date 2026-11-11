#!/usr/bin/env python3
"""Backfill Home Assistant long-term statistics from existing recorder history.

When you add `state_class: measurement` to a sensor, Home Assistant starts
building long-term statistics *from that moment* — it does not look back. So a
"365-day average" card reads empty for a year, even though the recorder already
holds months of raw history for that entity.

This rebuilds the missing hourly statistics (time-weighted mean, min, max) from
the `states` table and imports them through the supported
`recorder/import_statistics` websocket command.

Safe by construction:
  * dry-run unless you pass --import;
  * only writes hours strictly BEFORE the current hour;
  * mean-type statistics only — it never touches `sum`, so there is no risk of
    the cumulative corruption you can get with energy/volume counters.

RUN IT ON THE HOME ASSISTANT MACHINE (e.g. the Advanced SSH add-on), because it
reads the recorder database and the supervisor token directly:

    scp tools/backfill_statistics.py root@homeassistant.local:/tmp/
    ssh root@homeassistant.local 'python3 /tmp/backfill_statistics.py \
        --entities sensor.hitaveita_framrasarhiti,sensor.hitaveita_bakrasarhiti'
    # inspect the dry run, then repeat with --import

Afterwards, check it landed:
    Developer Tools -> Statistics, or a `statistic` card with a rolling window.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import secrets
import socket
import sqlite3
import struct
import sys

DB = "/config/home-assistant_v2.db"
TOKEN = "/run/s6/container_environment/SUPERVISOR_TOKEN"
HOUR = 3600


# --------------------------------------------------------------------------
# Minimal Home Assistant websocket client (no third-party dependencies, since
# the SSH add-on's Python has neither `websockets` nor `aiohttp`).
# --------------------------------------------------------------------------
class WS:
    def __init__(self, host: str, port: int, path: str, token: str):
        self.sock = socket.create_connection((host, port), timeout=60)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        self.sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b"101" not in buf.split(b"\r\n")[0]:
            raise RuntimeError("websocket upgrade failed: %s" % buf.split(b"\r\n")[0])
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self._id = 0
        m = self.recv()
        assert m["type"] == "auth_required", m
        self.send({"type": "auth", "access_token": token})
        m = self.recv()
        if m["type"] != "auth_ok":
            raise RuntimeError("auth failed: %s" % m)

    def _exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            d = self.sock.recv(65536)
            if not d:
                raise RuntimeError("socket closed")
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        while True:
            h = self._exact(2)
            op, ln = h[0] & 0x0F, h[1] & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._exact(8))[0]
            payload = self._exact(ln)
            if op == 0x1:
                return json.loads(payload)
            if op == 0x8:
                raise RuntimeError("server closed the connection")
            if op == 0x9:
                self._frame(payload, 0xA)

    def _frame(self, data: bytes, op: int = 0x1) -> None:
        mask = secrets.token_bytes(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        n = len(data)
        if n < 126:
            hdr = struct.pack("!BB", 0x80 | op, 0x80 | n)
        elif n < 65536:
            hdr = struct.pack("!BBH", 0x80 | op, 0x80 | 126, n)
        else:
            hdr = struct.pack("!BBQ", 0x80 | op, 0x80 | 127, n)
        self.sock.sendall(hdr + mask + masked)

    def send(self, obj) -> None:
        self._frame(json.dumps(obj).encode())

    def cmd(self, payload):
        self._id += 1
        self.send(dict(payload, id=self._id))
        while True:
            m = self.recv()
            if m.get("id") == self._id and m.get("type") == "result":
                return m


# --------------------------------------------------------------------------
def hourly_stats(cur, entity: str, cutoff: float):
    """Time-weighted hourly mean/min/max from the recorder `states` table."""
    cur.execute("SELECT metadata_id FROM states_meta WHERE entity_id=?", (entity,))
    row = cur.fetchone()
    if not row:
        return None
    cur.execute("SELECT last_updated_ts, state FROM states WHERE metadata_id=? "
                "AND last_updated_ts < ? ORDER BY last_updated_ts", (row[0], cutoff))
    pts = []
    for ts, st in cur.fetchall():
        try:
            pts.append((ts, float(st)))
        except (TypeError, ValueError):
            pts.append((ts, None))        # unavailable / unknown -> treat as a gap
    buckets: dict[int, list[float]] = {}
    for i, (ts, v) in enumerate(pts):
        if v is None:
            continue
        # a state holds until the next one; cap a trailing state at 5 minutes
        nxt = min(pts[i + 1][0] if i + 1 < len(pts) else ts + 300, cutoff)
        t = ts
        while t < nxt:
            h = int(t // HOUR) * HOUR
            seg_end = min(nxt, h + HOUR)
            d = seg_end - t
            if d > 0:
                b = buckets.setdefault(h, [0.0, 0.0, v, v])
                b[0] += v * d
                b[1] += d
                b[2] = min(b[2], v)
                b[3] = max(b[3], v)
            t = seg_end
    out = []
    for h in sorted(buckets):
        s, w, mn, mx = buckets[h]
        if w > 0:
            out.append({"start": dt.datetime.fromtimestamp(h, dt.timezone.utc).isoformat(),
                        "mean": round(s / w, 2), "min": round(mn, 2), "max": round(mx, 2)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entities", required=True, help="comma-separated entity_ids")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--host", default="supervisor")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--path", default="/core/websocket")
    ap.add_argument("--token-file", default=TOKEN)
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--import", dest="do_import", action="store_true",
                    help="actually write (default is a dry run)")
    args = ap.parse_args()

    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True, timeout=60)
    cur = con.cursor()
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now.replace(minute=0, second=0, microsecond=0).timestamp()
    ws = None

    for entity in [e.strip() for e in args.entities.split(",") if e.strip()]:
        print("\n=== %s ===" % entity)
        cur.execute("SELECT id, unit_of_measurement, mean_type, has_sum FROM statistics_meta "
                    "WHERE statistic_id=?", (entity,))
        meta_row = cur.fetchone()
        if not meta_row:
            print("  no statistics_meta row — add `state_class: measurement` and let HA "
                  "register the entity once, then re-run.")
            continue
        mid, unit, mean_type, has_sum = meta_row
        if has_sum:
            print("  SKIPPED: this is a sum/total statistic. This tool only backfills "
                  "mean-type statistics; importing sums risks corrupting the cumulative series.")
            continue
        # Exclude hours that already exist, by exact timestamp rather than by
        # MIN(start_ts): an import that failed or was interrupted part-way leaves
        # the OLDEST hours present, so a "< earliest" filter would discard every
        # hour still missing and report nothing left to do.
        cur.execute("SELECT start_ts FROM statistics WHERE metadata_id=?", (mid,))
        existing = {int(r[0]) for r in cur.fetchall()}
        if existing:
            print("  existing statistics: %d hourly rows, %s .. %s"
                  % (len(existing),
                     dt.datetime.fromtimestamp(min(existing), dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                     dt.datetime.fromtimestamp(max(existing), dt.timezone.utc).strftime("%Y-%m-%d %H:%M")))

        rows = hourly_stats(cur, entity, cutoff)
        if not rows:
            print("  no recorder history found")
            continue
        if existing:
            rows = [r for r in rows
                    if int(dt.datetime.fromisoformat(r["start"]).timestamp()) not in existing]
            print("  (skipping hours that already have statistics; safe to re-run "
                  "after a partial import)")
        if not rows:
            print("  nothing to backfill")
            continue
        means = [r["mean"] for r in rows]
        print("  %d hours: %s .. %s" % (len(rows), rows[0]["start"][:13], rows[-1]["start"][:13]))
        print("  mean of hourly means: %.2f %s  (lowest %.1f, highest %.1f)"
              % (sum(means) / len(means), unit or "", min(means), max(means)))
        if not args.do_import:
            print("  DRY RUN — pass --import to write")
            continue

        if ws is None:
            ws = WS(args.host, args.port, args.path,
                    open(args.token_file).read().strip())
        metadata = {"has_mean": True, "has_sum": False, "name": None,
                    "source": "recorder", "statistic_id": entity,
                    "unit_of_measurement": unit}
        for i in range(0, len(rows), args.batch):
            chunk = rows[i:i + args.batch]
            res = ws.cmd({"type": "recorder/import_statistics",
                          "metadata": metadata, "stats": chunk})
            if not res.get("success"):
                print("  IMPORT FAILED at %d: %s" % (i, json.dumps(res)[:400]))
                sys.exit(1)
            print("  imported %d–%d" % (i, i + len(chunk) - 1))
    con.close()


if __name__ == "__main__":
    main()
