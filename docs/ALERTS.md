# Optional alerts for the hitaveita monitoring package

These are **optional, copy-paste** examples. The monitoring package
(`packages/hitaveita_monitor.yaml`) works perfectly on its own — it just exposes
sensors and warning `binary_sensor`s you can view on a dashboard. **Alerts are an
extra, opt-in step;** nothing here is required.

> This is **not** a billing or certified-measurement system — it's a convenience
> monitor. **Tune the thresholds per house** (the `input_number.*` helpers); the
> defaults are only starting points.

## How alerts work

Each example automation triggers off a warning `binary_sensor` from the monitoring
package and is **time-debounced** with `for:` so brief spikes don't alert:

- `binary_sensor.hitaveita_high_return_temperature` — only `on` **while flow is
  active** (the binary sensor already handles the "warm standing water isn't a
  problem" case, so the automation doesn't need to re-check flow).
- `binary_sensor.hitaveita_poor_heat_extraction` — low delta-T while flow is active.
- `binary_sensor.hitaveita_continuous_flow_candidate` — sustained flow.

## Choose where alerts go (your `notify.` service)

Replace `notify.mobile_app_your_phone` below with **your own** notify service:

- **Home Assistant mobile app push** — `notify.mobile_app_<your_device>` (install the
  HA Companion app; the service appears automatically). Best default.
- **Email** — if you've configured the SMTP `notify` integration, use
  `notify.<your_smtp_name>`.
- **Persistent UI notification** — `notify.persistent_notification` (shows in the HA
  dashboard, no phone needed; handy for testing).
- **Other channels** — only if you already have the integration set up:
  `notify.telegram`, `notify.discord`, Pushover, ntfy, Twilio SMS, etc. (HA does not
  send SMS without a provider like Twilio or a GSM gateway.)
- **Several at once** — make a [notify group](https://www.home-assistant.io/integrations/group/#notify-groups)
  and point the automations at it.

> Tip: start with `notify.persistent_notification` to verify the logic, then switch
> to your phone push.

## Example automations

Add these to your `automations.yaml` (or via the UI). Replace the notify service,
then tune the `for:` durations and the helper thresholds to taste.

```yaml
- alias: "Hitaveita – high return temperature"
  description: "Return temp above threshold while flow is active, sustained 30 min."
  trigger:
    - platform: state
      entity_id: binary_sensor.hitaveita_high_return_temperature
      to: "on"
      for: "00:30:00"
  action:
    - action: notify.mobile_app_your_phone   # <-- replace with YOUR notify service
      data:
        title: "Hitaveita: high return temperature"
        message: "Return temperature has been high (while drawing) for 30 minutes."
  mode: single

- alias: "Hitaveita – poor heat extraction"
  description: "Low delta-T while flow is active, sustained 30 min."
  trigger:
    - platform: state
      entity_id: binary_sensor.hitaveita_poor_heat_extraction
      to: "on"
      for: "00:30:00"
  action:
    - action: notify.mobile_app_your_phone   # <-- replace with YOUR notify service
      data:
        title: "Hitaveita: poor heat extraction (low delta-T)"
        message: "delta-T has stayed low while drawing hot water for 30 minutes."
  mode: single

- alias: "Hitaveita – continuous flow"
  description: "Flow above the continuous-flow threshold for 6 hours."
  trigger:
    - platform: state
      entity_id: binary_sensor.hitaveita_continuous_flow_candidate
      to: "on"
      for: "06:00:00"
  action:
    - action: notify.mobile_app_your_phone   # <-- replace with YOUR notify service
      data:
        title: "Hitaveita: continuous flow"
        message: "Flow has stayed above the continuous-flow threshold for 6 hours."
  mode: single
```

If you'd like richer messages, you can include live values in the `message`, e.g.
`{{ states('sensor.hitaveita_delta_t') }}` — using whichever source entity_ids your
install actually has (see the monitoring package's dependency note).
