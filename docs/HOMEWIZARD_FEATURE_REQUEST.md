# Feature request to HomeWizard — expose MBus heat meter in `/api/v1/data`

Use this as the basis for a feature request / support ticket to HomeWizard. If they implement it,
Home Assistant's official HomeWizard integration would surface the heat/hot-water meter natively and
this whole project becomes unnecessary.

---

**Title:** P1 meter: expose attached MBus *heat* meter in `/api/v1/data` `external[]`

**Summary**

When a heat / hot-water (district-heating) meter is attached to the smart meter's P1/MBus port, the
P1 dongle includes its readings in the **raw telegram** (`GET /api/v1/telegram`) on MBus channel
`0-1:24.2.x`, but the parsed endpoint **`GET /api/v1/data` returns `"external": []`** — the heat
meter is not represented there. As a result, the official Home Assistant integration (which reads
`/api/v1/data`) cannot see it, and users must scrape the raw telegram themselves.

**Telegram lines currently parsed only manually** (example):

```
0-1:24.1.0(...)              # MBus device type / id
0-1:24.2.1(1234.567*m3)      # cumulative volume
0-1:24.2.2(0000.050*m3/h)    # flow
0-1:24.2.3(000070.0*degC)    # supply temperature
0-1:24.2.4(000035.0*degC)    # return temperature
0-1:24.2.5(0123.456*Wh)      # energy
```

**Request**

Parse this MBus device and add it to `external[]` in `/api/v1/data`, e.g.:

```json
{
  "external": [
    { "type": "heat_meter",  "unique_id": "...", "value": 1234.567, "unit": "m3" }
  ]
}
```

Ideally also surface flow / supply / return / energy as additional fields or entries so the heat
meter is fully represented (similar to how gas/water MBus devices are handled).

**Why it matters**

District heating (e.g. Icelandic *hitaveita*) is metered exactly this way; the data is already in
the dongle, just not in the parsed API. Native support would remove a brittle telegram-scraping
workaround for a whole class of users.

**Environment**

- Device: HomeWizard Wi-Fi P1 meter (HWE-P1), firmware 6.x, local API v1.
- Smart meter with an MBus heat meter on channel `0-1`.
