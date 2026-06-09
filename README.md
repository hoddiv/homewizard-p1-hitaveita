# Hitaveita (district hot water) → Home Assistant, via a HomeWizard P1 meter

Bring an **MBus heat / hot-water meter** (e.g. Icelandic *hitaveita* district heating) into
Home Assistant when it's attached to a **HomeWizard Wi-Fi P1 meter** — including **volume, live
flow, supply/return temperature, heat energy**, a **monthly usage meter**, and a simple
**cost** estimate.

> **Why this is needed:** the HomeWizard P1 exposes your **electricity** meter through its local
> `GET /api/v1/data`, and HA's official HomeWizard integration uses that. But an attached **MBus
> heat/water meter is _not_ parsed into the `external` array** of `/api/v1/data` (it comes back
> `"external": []`). The data *is* present in the **raw P1 telegram** (`GET /api/v1/telegram`) on
> MBus channel `0-1:24.2.x`, so this project scrapes the telegram with a small REST sensor.

No add-ons or custom components required — just YAML.

![Orka & Hitaveita dashboard in Home Assistant](images/dashboard.png)

---

## Does this apply to me?

You can use this if **all** of these are true:

1. You have a **HomeWizard Wi-Fi P1 meter** with the **local API enabled** (HomeWizard app → device →
   *Local API*).
2. A **heat / hot-water (MBus) meter** is connected to your smart meter's P1 port (common with
   Icelandic *hitaveita*, and some district-heating setups elsewhere).
3. The meter's readings appear in the telegram but **not** in `/api/v1/data`'s `external` array.

**Quick check** (replace the IP with your P1's address):

```bash
# Electricity only? Heat meter missing here?
curl -s http://YOUR_P1_IP/api/v1/data | grep external      # often: "external":[]

# But present in the raw telegram on an MBus channel:
curl -s http://YOUR_P1_IP/api/v1/telegram | grep -E '0-1:24\.2\.'
```

Example telegram lines (this is what we parse):

```
0-1:24.2.1(1234.567*m3)      # cumulative volume
0-1:24.2.2(0000.050*m3/h)    # live flow
0-1:24.2.3(000070.0*degC)    # supply temperature
0-1:24.2.4(000035.0*degC)    # return temperature
0-1:24.2.5(0123.456*Wh)      # heat energy register
```

> **Find your channel.** The examples use MBus channel **`0-1`**. Some installs put the heat meter
> on `0-2` or `0-3`. Run the `grep` above; if you see `0-2:24.2.x` instead, change `0-1` to `0-2`
> everywhere in `packages/hitaveita.yaml`.

---

## Install

### 1. Enable packages (one-time)

In `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 2. Add the package

Copy [`packages/hitaveita.yaml`](packages/hitaveita.yaml) into your HA `config/packages/` folder
and **edit two things**:

- replace `YOUR_P1_IP` with your P1 meter's IP,
- confirm the MBus channel (`0-1` by default — see above).

*(Alternatively, paste the contents of the package straight into `configuration.yaml`.)*

### 3. Check & restart

- **Developer Tools → YAML → Check configuration**, then **Restart**.
- ⚠️ On a low-RAM Home Assistant **VM (≤1 GiB)**, `ha core check` / restarts can thrash. **2 GiB+**
  recommended.

### 4. Set the price & add to dashboards

- Set **`input_number.hitaveita_verd_per_m3`** to your tariff (ISK per m³) in the UI.
- Add **`sensor.hitaveita_rummal`** under **Settings → Dashboards → Energy → Water consumption**
  (it's `device_class: water` + `state_class: total_increasing`, and the Energy dashboard can apply a
  static price for cost there too).
- Optional dashboard: [`dashboards/orka.yaml`](dashboards/orka.yaml) (see its header for how to
  register a YAML dashboard).

---

## Entities created

| Entity (default `entity_id`) | What |
|---|---|
| `sensor.hitaveita_rummal` | Cumulative volume (m³) |
| `sensor.hitaveita_rennsli` | Live flow (**L/min** — see gotcha #2) |
| `sensor.hitaveita_framrasarhiti` | Supply temperature (°C) |
| `sensor.hitaveita_bakrasarhiti` | Return temperature (°C) |
| `sensor.hitaveita_orka` | Heat energy register (Wh) |
| `sensor.hitaveita_rummal_manudur` | Volume this month (resets on the 1st) |
| `input_number.hitaveita_verd_per_m3` | Tariff (ISK/m³), set in UI |
| `sensor.hitaveita_kostnadur_manudur` | Cost this month = monthly m³ × price |
| `sensor.hitaveita_kostnadur_uppsafnadur` | Lifetime cost = total m³ × price |

> `entity_id`s are derived from the (Icelandic) names. If you rename the sensors, update the
> cross-references in the package (`utility_meter.source` and the two cost templates).

---

## Gotchas we hit (so you don't have to)

1. **`/api/v1/data` won't show the heat meter** (`external: []`). Use the telegram. *(If HomeWizard
   ever parses MBus "heat" into `external`, the official integration would expose it natively — see
   [`docs/HOMEWIZARD_FEATURE_REQUEST.md`](docs/HOMEWIZARD_FEATURE_REQUEST.md).)*
2. **Flow showed `0` in the dashboard.** `device_class: volume_flow_rate` is *unit-convertible*, so
   HA converted our `L/min` back to `m³/h` (~0.05) which rounds to `0`. Fix: report flow in **L/min
   with _no_ device_class** so it displays literally (idle hitaveita circulation ≈ 1 L/min; a shower
   ≈ 8–15 L/min).
3. **There is no live price API for hitaveita** — it's a fixed tariff (and bills often add a standing
   charge / energy component). So price is a manual `input_number`; treat cost as an estimate.
4. **The "energy" register (`24.2.5`) is often a small/rolling value**, not lifetime kWh — **volume
   (m³) is the meaningful usage figure**.
5. **The telegram has two `0-1:24.2.1(...)` lines** (a timestamp and the volume). The regex matches
   only the `*m3` one.

---

## Security note

This relies on the HomeWizard **local API v1, which is unauthenticated** on your LAN — anything that
can reach the P1 can read your energy + hot-water usage (and Wi-Fi SSID). HA needs it on, so:

- **Do not expose the P1 to the internet** (no router port-forward to it).
- Prefer putting IoT devices on a **separate VLAN / restricted subnet**.
- The newer HomeWizard **v2 API (HTTPS, token)** is auth'd, but does not change the MBus parsing gap.

---

## Contributing / improving upstream

- Best fix for everyone: ask HomeWizard to expose MBus **heat** in `/api/v1/data` →
  [`docs/HOMEWIZARD_FEATURE_REQUEST.md`](docs/HOMEWIZARD_FEATURE_REQUEST.md).
- Prefer not to copy-paste? An optional, **credential-free** prompt that generates a tailored
  package from your own telegram is in
  [`docs/GENERATOR_PROMPT.md`](docs/GENERATOR_PROMPT.md). It does **not** require giving any tool
  access to your Home Assistant.

PRs welcome for other MBus device types (water, gas) and non-ISK currencies.

## License

MIT — see [`LICENSE`](LICENSE).
