# P1 MBus heat meter present in telegram but missing from `/api/v1/data` `external[]`

Source material for an upstream report to **`homewizard/api-documentation`**. If the attached heat
meter were populated into `/api/v1/data` `external[]`, Home Assistant's official HomeWizard
integration would surface it natively and the workaround in this repo would no longer be needed.

> **Accuracy note:** HomeWizard's measurement documentation **already defines** externally connected
> utility meters via `external[]`, including `heat_meter`, `warm_water_meter`, `inlet_heat_meter`,
> `water_meter`, and `gas_meter`. So this is **not** a request to add a heat-meter concept from
> scratch — the model exists. It's a report that a real attached MBus heat meter is **visible in the
> telegram but not populated into `external[]`**, plus a request for guidance.

---

**Suggested upstream issue title**

`P1 MBus heat meter present in /api/v1/telegram but missing from /api/v1/data external[]`

---

## Summary

On a HomeWizard Wi-Fi P1 meter (HWE-P1, firmware 6.x, local API v1) with an attached MBus
**district-heating / hot-water (heat) meter**, the meter's readings appear in the raw telegram
endpoint (`GET /api/v1/telegram`) on MBus channel `0-1:24.2.x`, but the parsed endpoint
(`GET /api/v1/data`) returns `"external": []` — the attached heat meter is not represented there.

The measurement documentation already defines externally connected utility meters via `external[]`,
including `heat_meter`, `warm_water_meter`, and `inlet_heat_meter`, so one would expect this meter to
appear there the way gas/water meters do.

## Observed behavior

`GET /api/v1/telegram` includes the heat meter (example lines — **illustrative / redacted**, not a
real telegram; channel may be `0-1`, `0-2`, `0-3`, or `0-4` on other setups):

```text
0-1:24.1.0(...)              # MBus device type / id  (redacted)
0-1:24.2.1(1234.567*m3)      # cumulative volume
0-1:24.2.2(0000.050*m3/h)    # flow
0-1:24.2.3(000070.0*degC)    # supply temperature
0-1:24.2.4(000035.0*degC)    # return temperature
0-1:24.2.5(0123.456*Wh)      # energy register
```

`GET /api/v1/data` for the same device returns an empty external array:

```json
{ "external": [] }
```

## Likely explanations

This suggests one of:

- this OBIS layout (`0-1:24.2.x` heat meter) is **not currently supported / parsed**, or
- the attached meter is **not detected** as one of the documented heat / warm-water external meter
  types, or
- there is a **parsing gap** between the telegram and the parsed measurement endpoint.

## Expected / requested behavior

If this is intended to be supported, please expose the attached MBus heat / district-heating meter
through `/api/v1/data` `external[]` using the **documented external meter model**. If it is not
currently supported, it would help to clarify whether this OBIS layout could be supported.

Useful fields, if available:

- cumulative volume — `m3`
- flow — `m3/h`
- supply temperature — `degC`
- return temperature — `degC`
- energy register — `Wh`

## Why this matters

District heating (e.g. Icelandic *hitaveita*) is metered exactly this way. The data is already inside
the P1 (it's in the telegram); exposing it through `external[]` would let Home Assistant and other
integrations support these meters **natively** instead of scraping the raw telegram.

## Current workaround

This repository provides a small Home Assistant YAML package that scrapes `/api/v1/telegram`
directly. It works, but reading the raw telegram is more brittle than native `/api/v1/data`
`external[]` support (string parsing, OBIS/channel assumptions, no schema guarantees).

- Workaround repo: https://github.com/hoddiv/homewizard-p1-hitaveita
- This document: https://github.com/hoddiv/homewizard-p1-hitaveita/blob/main/docs/HOMEWIZARD_FEATURE_REQUEST.md

I'm happy to provide a **redacted** real telegram sample and the corresponding `/api/v1/data` output
if useful.

## Environment

- Device: HomeWizard Wi-Fi P1 meter (HWE-P1), firmware 6.x, local API v1.
- Smart meter with an attached MBus heat / district-heating meter (channel `0-1` in this setup).
