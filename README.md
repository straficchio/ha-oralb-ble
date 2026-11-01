# Oral-B BLE for Home Assistant

Local, cloud-free Home Assistant integration for Oral-B Bluetooth
toothbrushes (Genius, Smart Series, iO). It uses the brush's BLE
advertisements for live data and a short GATT connection for battery,
firmware metadata and stored brushing sessions.

> **Status:** the protocol is derived from the official Android app 10.8.1 and
> the public firmware images. It has unit/integration tests against Home
> Assistant 2026.10.4, but live GATT verification on a physical brush is
> still pending. Please open an issue with a diagnostics dump if a value
> looks wrong.

## Features

- **Passive live sensors** — state, mode, pressure, brushing time, quadrant,
  smiley, RSSI and "new sessions" flag come from the advertisement; no
  connection is needed while brushing.
- **Battery** — percentage and remaining time over GATT.
- **Firmware metadata** — model, protocol, firmware, bootloader, secondary
  firmware, hardware version, device UUID.
- **Session history** — the brush stores every brushing session. The
  integration reads new sessions after a brushing session (or on demand),
  exposes last-session sensors and fires an event for each session.
- **Safe writes only** — the integration writes the unlock key, extends the
  connection and optionally syncs the clock. No factory reset, no OTA.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add this repository URL as an **Integration**.
3. Install "Oral-B BLE" and restart Home Assistant.

### Manual (web UI only, no SSH client)

You do not need SSH or Samba. The official **Terminal & SSH** add-on gives
you a web terminal inside Home Assistant:

1. **Settings → Add-ons → Add-on Store**, install **Terminal & SSH** (or
   **Studio Code Server**, which also has a terminal), start it and open its
   **Web UI**.
2. Paste this into the terminal:

   ```bash
   wget -O /tmp/oralb.tar.gz \
     https://github.com/straficchio/ha-oralb-ble/archive/refs/heads/master.tar.gz
   mkdir -p /config/custom_components
   tar -xzf /tmp/oralb.tar.gz -C /tmp
   cp -r /tmp/ha-oralb-ble-master/custom_components/oralb_ble \
     /config/custom_components/
   ```

   If `wget` is not available, replace the first line with
   `curl -L -o /tmp/oralb.tar.gz <same URL>`.

3. Restart Home Assistant: **Settings → System → Restart** (or `ha core
   restart` in the terminal).
4. **Settings → Devices & Services → Add Integration → Oral-B BLE**.

The integration depends on Home Assistant's `bluetooth` integration. A
Bluetooth adapter (or a remote ESPHome Bluetooth proxy) must be in range of
the brush.

### HACS

If HACS is already installed: **HACS → Integrations → ⋮ → Custom
repositories**, add `https://github.com/straficchio/ha-oralb-ble` as an
**Integration**, install it, and restart. If HACS is not installed, the
terminal route above is the shortest path.

## Pairing

Home Assistant has no generic "pair this BLE device" button. For most Oral-B
brushes you do **not** need to pair manually: BlueZ bonds automatically on
the first GATT connection when the brush asks for it, and the integration
performs the app-level unlock (`MGS` written to `FF10`) itself.

If a read fails with an authentication/insufficient-encryption error:

1. Press the **Pair / test connection** button on the device page. It asks
   BlueZ to bond and then reads the live values. No shell needed.
2. If that works but later reads still fail, open **Settings → Devices &
   Services → Oral-B BLE → Configure** and enable **Pair on connect**, so
   every poll bonds first.
3. Close the Oral-B phone app and, if the brush is still bonded to the phone,
   remove it from the phone's Bluetooth settings. A brush accepts one active
   connection at a time.
4. Check **Settings → System → Logs** for the integration's debug message. If
   bonding still fails, the brush may use a pairing variant that BlueZ cannot
   complete headlessly; a Bluetooth proxy or a USB adapter with a working
   BlueZ agent may be needed.

The application-level "unlock" is not a secret and is not the same as BLE
bonding: it is a fixed three-byte write (`4D 47 53`, ASCII `MGS`) that the
official app sends to `FF10` on V008+ firmware.

## Setup

The brush advertises manufacturer data with company id `0x00DC`
(Procter & Gamble). Home Assistant should discover it automatically:

1. Wake the brush (press its power button) so it advertises.
2. Settings → Devices & Services → Add Integration → Oral-B BLE.
3. Pick the discovered brush, or enter its MAC address manually.

The brush must be awake for the first GATT poll; if it is asleep the entry is
still created and the first poll runs when it advertises again.

## Entities

### Sensors

| Entity | Description |
|---|---|
| Battery | battery percentage |
| Battery time remaining | estimated minutes left |
| State | idle / running / charging / paused / … |
| Brushing mode | daily clean, sensitive, gum care, … |
| Pressure | low / normal / high / button pressed |
| Brushing time | live timer from the advertisement |
| Quadrant | current quadrant/sector |
| Smiley | firmware smiley face |
| Last session duration | seconds |
| Last session start | timestamp |
| Last session mode | mode used |
| Last session high/low pressure time | seconds |
| Last session average/maximum pressure | mN |
| Last session high/low pressure events | count |
| Last session battery | percentage at end |
| Sessions today | sessions started today (local time) |
| Total sessions | sessions seen by this integration |
| Model / Protocol / Firmware / Bootloader / Secondary firmware | diagnostic |
| Hardware version / Device UUID | diagnostic |
| Signal strength | RSSI |
| Last session sync / Last advertisement | timestamps |

### Binary sensors

- **Brushing** — state is `running`.
- **Charging** — state is `charging`.
- **New sessions available** — advertisement flag.
- **In range** — an advertisement was seen in the last 10 minutes.
- **High pressure** — current pressure is high.

### Buttons

- **Sync sessions** — connect and scan the stored session slots now.
- **Sync clock** — write the current time and timezone to the brush.
- **Pair / test connection** — connect with bonding enabled and read the live
  values. This is the web-UI equivalent of "pair the brush"; use it if the
  sensors stay empty.

## Events

Every new session fires the event below.  The **first** sync imports the
sessions already stored on the brush silently (so a new install does not
flood the event bus with months of history); every later session fires the
event.


```yaml
event: oralb_ble_session
data:
  address: "78:DB:2F:C2:48:BE"
  name: "Oral-B iO5"
  session:
    start_time: "2026-11-01T18:42:00+00:00"
    duration: 124
    mode: "sensitive"
    mode_value: 1
    high_pressure_time: 8
    low_pressure_time: 3
    high_pressure_events: 2
    low_pressure_events: 1
    average_pressure: 1
    maximum_pressure: 2
    final_battery_level: 80
    configured_time: 120
    number_of_sectors: 4
    session_id: 42
    user_id: 0
    tongue_time: 0
    eco_settings: 1
```

Example automation:

```yaml
automation:
  - alias: "Log Oral-B session"
    trigger:
      - platform: event
        event_type: oralb_ble_session
    action:
      - service: logbook.log
        data:
          name: "Oral-B"
          message: >
            {{ trigger.event.data.session.duration }}s,
            mode {{ trigger.event.data.session.mode }},
            {{ trigger.event.data.session.high_pressure_events }} high-pressure events
```

## Options

| Option | Default | Description |
|---|---|---|
| Battery/state poll interval | 360 min | how often to connect for battery/metadata/session sync |
| Sync stored sessions | on | read new sessions after brushing / on poll |
| Enable live advertisement sensors | on | create live sensors (state, mode, …) |
| Session slots to scan | 250 | how many session slots to scan |
| Pair on connect | off | attempt BLE bonding if reads fail with an authentication error |

## How it works

- Advertisements are parsed by `protocol.parse_advertisement()`.
- A poll connects with `bleak-retry-connector`, writes `MGS` to `FF10` for
  V008+ firmware, extends the connection (`FF21 31 FF`), reads `FF04`–`FF0B`,
  optionally reads metadata (`FF21 05 id` + `FF29`) and session records
  (`FF21 02 index` + `FF29`), then disconnects.
- The last-sync timestamp and the recent session list are stored in
  `.storage/oralb_ble.<address>`.

The full protocol reference is in [docs/PROTOCOL.md](docs/PROTOCOL.md);
firmware details are in [docs/FIRMWARE.md](docs/FIRMWARE.md).

## Limitations

- The integration identifies a brush by its BLE address. Oral-B brushes use a
  stable address; if yours rotates (rare), re-add it.
- The brush accepts one connection at a time. The phone app and Home
  Assistant cannot both hold it.
- A sleeping brush is normal; entities keep their last values and the
  integration retries later.
- Reading 250 session slots takes tens of seconds. The integration scans a
  bounded number of slots and stops after a run of old/invalid slots; use
  the **Sync sessions** button to force a full scan.
- No OTA, no factory reset, no settings writes other than clock sync.
- Some brushes may require bonding before protected characteristics are
  readable. Pair the brush with the Home Assistant host's adapter if a read
  fails with an authentication error.
- The iO Sense charger is not supported (different GATT service).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # or: pip install homeassistant pytest-homeassistant-custom-component
PYTHONPATH=. .venv/bin/python -m pytest tests -q
```

The tests cover the advertisement parser, all characteristic parsers, session
layouts, configure/control builders, config flow and entity setup.

## License

MIT
