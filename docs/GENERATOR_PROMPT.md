# Optional: generate a tailored package from your own telegram (no system access)

Prefer not to hand-edit YAML? You can have an LLM (Claude, ChatGPT, etc.) produce a package matched
to *your* meter — **without giving it any access to your Home Assistant or network**. You just paste
in your own telegram output.

> ⚠️ **Do not** give an AI agent SSH/root access to your Home Assistant to "set it up for you." This
> generator is deliberately credential-free: it only transforms text you paste. Review the YAML it
> produces before adding it.

### Step 1 — grab your telegram (on your LAN)

```bash
curl -s http://YOUR_P1_IP/api/v1/telegram
```

### Step 2 — paste this prompt + your telegram

````
You are helping me add an MBus heat / hot-water meter from a HomeWizard P1 dongle to Home
Assistant. The official HomeWizard integration does NOT expose this meter (its /api/v1/data
returns "external": []), so I read the raw P1 telegram instead.

Here is my telegram output:

<PASTE THE FULL TELEGRAM HERE>

Please:
1. Identify the MBus channel and OBIS codes for the heat/water meter (e.g. 0-1:24.2.x: volume m3,
   flow m3/h, supply degC, return degC, energy Wh). Tell me which channel you found.
2. Generate a Home Assistant *package* (a single YAML file for config/packages/) with REST sensors
   that scrape http://YOUR_P1_IP/api/v1/telegram every 30s and parse those values, with sensible
   names, device_class, state_class and units.
3. IMPORTANT: report flow in L/min with NO device_class (volume_flow_rate is unit-convertible and HA
   would convert small L/min values back to m3/h, which round to 0 in cards).
4. Add: an input_number for a fixed price per m3, a monthly utility_meter on the volume, and two
   template "cost" sensors (monthly and lifetime) = volume * price.
5. Output only the final YAML plus a one-paragraph note on which line(s) to edit (the IP) and the
   expected entity_ids.

Do not ask me to give you any access to my systems — only use the telegram text above.
````

### Step 3 — review & install

Read the YAML, replace the IP, drop it in `config/packages/`, check config, restart. See the main
[README](../README.md) for the install steps, the Energy-dashboard hookup, and the gotchas.
