# iAquaLink iQPump (i2d) — Home Assistant integration

Monitor and **control** a Jandy/Zodiac **iQPump01** variable-speed pool pump from Home
Assistant. These pumps are exposed by the iAquaLink cloud as `device_type=i2d`, which the
official `iaqualink` integration rejects with `i2d is not a supported system type`
([home-assistant/core#49182](https://github.com/home-assistant/core/issues/49182)).

This is a self-contained custom integration — it talks to the iAquaLink cloud directly
(no external Python dependency beyond what Home Assistant ships) and adds full RPM control.

**Supported hardware:** Jandy / Zodiac **iQPump01** pump controllers, e.g. the **Zodiac
FloPro VS** variable-speed pool pump, that appear in the iAquaLink app as `device_type=i2d`.
Keywords: Home Assistant, HACS, iAquaLink, Jandy, Zodiac, FloPro VS, iQPump01, i2d,
variable speed pool pump, RPM control.

## Features

- **Set running RPM + duration** — pick a target RPM and how long to hold it.
- **Return to schedule** — hand control back to the pump's own program.
- Sensors: motor speed (RPM), motor power (W), **motor temperature (°C)**, target RPM,
  custom-speed RPM, custom-speed timer, operating mode.
- Priming binary sensor.
- A `set_custom_speed` service for automations, plus `return_to_schedule`.

> **Temperature note:** the iQPump01 only reports **motor winding temperature**, which the
> controller already provides in °C. It does **not** expose pool-water temperature.

## Compatibility

This integration drives any pump the iAquaLink cloud reports as **`device_type=i2d`** —
i.e. a **Jandy Pro Series iQPUMP01** control interface attached to a Jandy/Zodiac
variable-speed pump. The iQPUMP01 is the box that adds iAquaLink app control to these
pumps, so the pump model matters less than "is it behind an iQPUMP01?".

**Check yours:** during setup the integration lists your account's devices and only offers
`i2d` ones. In the iAquaLink app, an iQPUMP01-controlled pump shows up as its own pump tile.

| Pump | Interface | Status |
| --- | --- | --- |
| Zodiac **FloPro VS** 1.65 HP | iQPUMP01 | ✅ **Verified** (developer's pump, `productid=17`) |
| Jandy **VS FloPro** — 0.85 / 1.3 / 1.65 / 1.85 / 2.7 / 3.8 HP | iQPUMP01 | 🟢 Expected to work (same i2d interface) |
| Zodiac **FloPro VS** — all HP variants (EU branding of VS FloPro) | iQPUMP01 | 🟢 Expected to work |
| Jandy **ePump** (JEP-R) | built-in iAquaLink RS | ⚠️ Untested — may report a different `device_type` |
| Any VS pump behind an **AquaLink RS / PDA** controller (no iQPUMP01) | AquaLink RS | ❌ Different system type — use the official `iaqualink` integration or [AqualinkD](https://github.com/sfeakes/AqualinkD) |

RPM limits vary by model; the integration reads the controller's own `globalrpmmin` /
`globalrpmmax` and adapts automatically, so no per-model configuration is needed.

> Got a different iQPUMP01 pump working (or not)? Please
> [open an issue](https://github.com/tkhduracell/ha-iaqualink-i2d/issues) with your model
> and `productid` so this table can be expanded.

## Install via HACS (recommended)

[HACS](https://hacs.xyz) (the Home Assistant Community Store) is the easiest way to
install and keep this integration updated. This is a **custom repository** — it is not
(yet) in the HACS default list, so you add it once by URL:

1. Open **HACS** in Home Assistant.
2. Top-right **⋮ menu → Custom repositories**.
3. Paste the repository URL and pick category **Integration**:
   ```
   https://github.com/tkhduracell/ha-iaqualink-i2d
   ```
   Click **Add**.
4. Search HACS for **iAquaLink iQPump (i2d)**, open it, and click **Download**.
5. **Restart Home Assistant** (Settings → System → Restart).
6. **Settings → Devices & Services → + Add Integration →** search **iAquaLink iQPump (i2d)**.
7. Sign in with your **iAquaLink email + password**. If your account has more than one
   iQPump you'll be asked which to add. Done — entities appear under a new device.

Updates: when a new release is published, HACS shows an update badge; click **Update**
and restart.

### Manual install (without HACS)

Copy the `custom_components/iaqualink_i2d/` folder into your Home Assistant
`config/custom_components/` directory, restart, then add the integration from the UI
(step 6 onward above). Directory layout:

```
config/
└── custom_components/
    └── iaqualink_i2d/
        ├── __init__.py
        ├── manifest.json
        └── ...
```

## Entities

| Entity | Purpose |
| --- | --- |
| `fan.*_pool_pump` | The pump. On/off, speed as a **percentage** (mapped to the device's min/max RPM in 25-RPM steps; exact RPMs are in the entity attributes), and a **`auto`** preset that hands control back to the pump's schedule. Setting a speed puts the pump in custom mode for the selected duration. |
| `select.*_custom_speed_duration` | Run duration used when setting a custom speed. Held in memory; resets to the configured default on HA restart. |
| `sensor.*_motor_power` / `_motor_temperature` | Live motor telemetry (°C for temperature). |
| `sensor.*_motor_speed` | Actual motor RPM (diagnostic). |
| `sensor.*_operating_mode`, `_custom_speed_timer` | State (diagnostic). |
| `binary_sensor.*_priming` | On while priming (diagnostic). |

Setting the fan speed switches the pump to custom mode and runs at that RPM for the
`custom_speed_duration`; the `auto` preset returns it to the schedule.

## Services

```yaml
# Run at 1800 RPM for 1 hour
service: iaqualink_i2d.set_custom_speed
target:
  entity_id: number.pool_pump_pump_rpm
data:
  rpm: 1800
  duration_seconds: 3600
```

```yaml
service: iaqualink_i2d.return_to_schedule
target:
  entity_id: number.pool_pump_pump_rpm
```

## How control works

All traffic is `POST https://r-api.iaqualink.net/v2/devices/{serial}/control.json`:

| Purpose | command | params |
| --- | --- | --- |
| Read all state | `/alldata/read` | — |
| Mode: Auto / Custom / Off | `/opmode/write` | `value=0` / `1` / `2` |
| Set custom RPM | `/customspeedrpm/write` | `value=<rpm>` |
| Set custom timer | `/customspeedtimer/write` | `value=<seconds>` |

Setting a speed runs `opmode=1 → customspeedrpm → customspeedtimer` (RPM writes are ignored
in scheduled mode, so the mode switch comes first). Service mode (`opmode=7`) blocks writes.

## Credits

Protocol and field notes reverse-engineered by the community, notably
[`CLARENNE-Q/iaqualink_iqpump01`](https://github.com/CLARENNE-Q/iaqualink_iqpump01) and the
`flz/iaqualink-py` i2d docs. This integration is an independent async reimplementation.

## Disclaimer

Not affiliated with Jandy, Zodiac, or Fluidra. Uses an undocumented cloud API that may
change at any time. Use at your own risk.
