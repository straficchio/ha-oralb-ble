# Oral-B BLE protocol reference

This document describes the Bluetooth Low Energy protocol used by Oral-B
connected toothbrushes (Genius, Smart Series, iO) as implemented by the
official Android app **`com.pg.oralb.oralbapp` 10.8.1 (versionCode 13923)**
and by the brush firmware images that the app can download.

Everything below is from shipped artifacts:

- decompiled app classes `codes.alchemy.oralb.blesdk.*`,
- the GATT tables embedded in the Sonos / iO firmware images,
- the public firmware manifests at `fw.iot-dev.alchemy.codes`.

It was cross-checked against two public community projects:

- [`Bluetooth-Devices/oralb-ble`](https://github.com/Bluetooth-Devices/oralb-ble) — passive advertisement parser.
- [`wise86-android/OralBlue_python`](https://github.com/wise86-android/OralBlue_python) — early protocol notes.

> **Verification status.** The static protocol is complete and consistent, but
> no live brush was advertising during this analysis, so the GATT read/write
> sequences below are **not yet confirmed on hardware**. The standalone probe
> (`tools/oralb.py`) and the Home Assistant integration are provided to do
> that confirmation.

---

## 1. GATT layout

Oral-B uses a 128-bit base UUID whose tail is ASCII `PGMS` + `Oral-B`:

```
A0F0xxxx-5047-4D53-8208-4F72616C2D42
```

The 16-bit `xxxx` value identifies the characteristic. The firmware images
contain the same bytes in little-endian order (`42 2D 6C 61 72 4F 08 82 53 4D
47 50 xx xx F0 A0`), which is why `strings` shows `B-larO` and `SMGP`.

### Services

| Service | Short UUID | Purpose |
|---|---|---|
| Main brush service | `FF00` | State, battery, mode, pressure, sensor/dashboard data |
| Control/configuration service | `FF20` | Configure/Control channel, RTC, timers, color, refill |
| OTA service | `FF80` | Firmware update |
| Charger service | `3C00` | iO Sense charger (Wi-Fi/MQTT/display), separate device |

### Characteristic map

| UUID | Firmware name | App model | Access | Payload |
|---|---|---|---|---|
| `FF01` | Handle ID | — | R | uint32 LE handle id |
| `FF02` | Handle Type | — | R | 3 bytes `[modeId, protocolVersion, fwVersion]` |
| `FF03` | User Account | — | R/W | 1 byte user id |
| `FF04` | Device State | `DeviceState` | R/N | 2 bytes `[state, sub_state]` |
| `FF05` | Battery Level | `BatteryLevel` | R/N | protocol dependent (see §4) |
| `FF06` | Button State | `ButtonState` | R | 2 bytes `[power, mode]` |
| `FF07` | Brushing Mode | `BrushingMode` | R/N | 1 byte mode |
| `FF08` | Brushing Time | `BrushingTime` | R | 2 bytes `[minutes, seconds]` |
| `FF09` | Quadrant | `ToothbrushQuadrant` | R | 3 bytes `[quadrant, ?, total]` |
| `FF0A` | Smiley | `Smiley` | R | 1 byte face id |
| `FF0B` | Pressure Sensor | `Pressure` | R | 1 byte (old) / 10 bytes (V007+) |
| `FF0C` | Cache | — | R | internal cache |
| `FF0D` | Sensor Data | `SensorData` | R/N | motion / gyro / dashboard records |
| `FF0E` | Data | `DashboardDataStreamChunk` | N | 2 + N×8 byte records |
| `FF10` | — | `AccessControl` | W | `4D 47 53` (`MGS`) unlock key |
| `FF21` | Command Status | `Configure`, `Control` | R/W | command/selector channel |
| `FF22` | RTC | `RTC` | R/W | 4 bytes LE seconds since 2000-01-01 |
| `FF23` | Timezone | `Timezone` | R/W | 1 byte, 15-minute units |
| `FF24` | Brushing Modes | `BrushTimer` | R/W | 1 byte signal flags |
| `FF25` | Quadrant Times | `BrushModes` | R/W | 8 mode bytes |
| `FF26` | Quadrant Times | `QuadrantTimer` | R/W | 8 × uint16 LE timers |
| `FF27` | — | `TongueTime` | R/W | 1 byte seconds |
| `FF28` | — | `PressureConfiguration` | R/W | 2 bytes `[signal, motor]` |
| `FF29` | Data | `SelectedData`, `SessionData` | R | selected metadata / session |
| `FF2A` | Flight Mode | — | R/W | flight-mode state |
| `FF2B` | Color | `MyColor` | R/W | 4 bytes `[r, g, b, id]` |
| `FF2C` | — | `ConfigureDashboard` | W | dashboard config |
| `FF2D` | Refill | `RefillReminder` | R/W | refill state / interval |
| `FF81` | OTA Command | `OTACommand` | W | 1 byte command |
| `FF82` | OTA Payload 1 | `OTAPayLoad` | W | current-protocol chunks (244 B) |
| `FF83` | OTA Payload 2 | `LegacyOTAPayLoad2` | W | legacy second half |
| `FF84` | OTA State | `OTAState` | R/N | 1 byte state / error |
| `FF85` | OTA Size | `OTATransferSize` | R/N | uint32 transferred size |
| `FF86` | — | — | ? | present in newer firmware tables; purpose not yet identified |

Charger characteristics (`3C00` service): `3C00` command, `3C01` read,
`3C02` write, `3C03` status. See §10.

The firmware GATT table (extracted from `sonos_firmware_0x6e.bin`) labels
`FF21` "Command Status", `FF22` "RTC", `FF23` "Timezone", `FF25` "Brushing
Modes", `FF26` "Quadrant Times", `FF29` "Data", `FF2A` "Flight Mode",
`FF2B` "Color" and `FF2D` "Refill". The app model names used in this
document are the names of the corresponding Kotlin classes.

---

## 2. Advertisement format

Oral-B brushes advertise manufacturer-specific data with company id
`0x00DC` (Procter & Gamble). The raw AD structure is:

```
06 FF DC 00 09 31 2A 03 00 00 00 01 00 04
│  │  │  │  │  │  │  │  │  │  │  │  │  │  └─ total quadrants
│  │  │  │  │  │  │  │  │  │  │  │  │  └──── quadrant / sector timer
│  │  │  │  │  │  │  │  │  │  │  │  └─────── progress (low 3 bits quadrant, bits 3-5 smiley)
│  │  │  │  │  │  │  │  │  │  │  └────────── mode
│  │  │  │  │  │  │  │  │  │  └───────────── seconds
│  │  │  │  │  │  │  │  │  └──────────────── minutes
│  │  │  │  │  │  │  │  └─────────────────── status / pressure / buttons
│  │  │  │  │  │  │  └────────────────────── state
│  │  │  │  │  │  └───────────────────────── software version
│  │  │  │  │  └──────────────────────────── device type
│  │  │  │  └─────────────────────────────── protocol version
│  │  │  └────────────────────────────────── company id high byte (0x00)
│  │  └───────────────────────────────────── company id low byte (0xDC)
│  └──────────────────────────────────────── AD type (0xFF = manufacturer)
└─────────────────────────────────────────── AD length
```

`bleak`/Home Assistant strip the first four bytes, so the payload handled by
the integration starts at **protocol version**:

| Index | Field | Notes |
|---:|---|---|
| 0 | protocol version | 1..9 (`V001`..`V009`) |
| 1 | device type | see table below |
| 2 | software version | one byte |
| 3 | device state | `0` unknown, `1` init, `2` idle, `3` run, `4` charge, `5` setup, `6` flight menu, `7` charge forbidden, `8` pre-run, `9` pause, `10` post-brushing stats, `113` final test, `114` PCB test, `115` sleep, `116` transport, `117` calibration |
| 4 | status | bit 7 high pressure, bit 3 power button, bit 2 mode button, bit 1 new sessions |
| 5 | brushing minutes | |
| 6 | brushing seconds | |
| 7 | mode | protocol dependent |
| 8 | progress | low 3 bits quadrant, bits 3–5 smiley |
| 9 | quadrant completion / Sonos sub-model / sector timer | V001–V007: quadrant completion; V008+: Sonos sub-model (or sector timer in some firmware) |
| 10 | total quadrants | 3 bits |

### Device types

| Value | Model |
|---:|---|
| 0/1/2 | D36 (X / 6 / 5 mode) |
| 32/33/34 | D701 (X / 6 / 5 mode) |
| 39/40/41 | D700 (5 / 4 / 6 mode) |
| 43 | iO Series 6 (`0x2B`, observed in public captures) |
| 48/49/50 | Oral-B iO (X mode / iO / Big TI) |
| 52/53 | iO4 / iO5 |
| 54 | iO E-Platform (iO6–iO10) |
| 63 | D36 experimental |
| 64–70 | D21 variants |
| 80–87 | D601 variants |
| 112–114 | D706 variants |
| 117–119 | D706 China variants |
| 165/166 | HCB G5 / HCB E-Platform |
| 255 | experimental |

### Status bits

```
bit 7 (0x80)  high pressure
bit 3 (0x08)  power button pressed
bit 2 (0x04)  mode button pressed
bit 1 (0x02)  new session data available
```

The remaining bits are display/flag bits that vary by firmware; the official
app only uses the bits above.

### Example

`08 35 2A 03 82 01 1E 01 02 00 04`

- protocol `V008`
- type `0x35` = iO5
- software `42`
- state `3` = running
- status `0x82` = high pressure + new sessions
- time `1:30`
- mode `1` = sensitive
- progress `2` = 2nd quadrant, smiley off
- total quadrants `4`

---

## 3. Connection sequence

The app's `TinyTooth` client does the following (from
`codes.alchemy.oralb.blesdk.client.TinyTooth` and
`devices.BackgroundBluetoothInteractor`):

1. Connect with MTU negotiation and high-priority connection.
2. If protocol ≥ `V008`, write `4D 47 53` (`MGS`) to `FF10` to unlock
   protected characteristics.
3. Write `31 FF` to `FF21` (`EXTEND_CONNECTION`, 255 s) so the brush keeps
   the link while sessions are read.
4. If protocol < `V008`, write `01 00` to `FF21` (`READ_PARAM(0)`) to make
   the read parameters valid.
5. Read or subscribe to the desired characteristics.
6. Disconnect. The brush resumes advertising.

The app also bonds on Android (`createBond`) for some models. The protocol
itself does not carry an application-layer PIN; reads may work without
bonding, but Android's GATT stack may require the bond for protected
characteristics. The Home Assistant integration tries without bonding first.

---

## 4. Characteristic payloads

### FF04 — Device state

```
byte 0: state       (see advertisement table)
byte 1: sub-state   (transport flags; -1/0xFF = unknown)
```

### FF05 — Battery

| Protocol | Layout |
|---|---|
| V001–V003 | `[level]` |
| V004–V007 | `[level & 0x7F, seconds_hi, seconds_lo, ?]` |
| V008–V009 | `[level & 0x7F, seconds_lo, seconds_hi, voltage_lo, voltage_hi, current_lo, current_hi, temperature, soc, discharge_u32, remaining_u32, soc_state]` |

All multi-byte fields are little-endian. The app treats the extended fields
as optional and only reads them if the payload is long enough.

### FF06 — Button state

```
[power_pressed, mode_pressed]   (1 = pressed)
```

The parser also accepts a one-byte payload where byte 0 is the power button.

### FF07 — Brushing mode

One byte. The mapping depends on the protocol:

| Value | Protocol < V006 | Protocol ≥ V006 |
|---:|---|---|
| 0 | off | daily clean |
| 1 | daily clean | sensitive |
| 2 | sensitive | gum care |
| 3 | massage | whiten |
| 4 | whitening | intense |
| 5 | deep clean | super sensitive |
| 6 | tongue clean | tongue cleaning |
| 7 | pro clean | off |
| 8 | — | settings |
| 11 | — | smart adapt |
| 12 | — | gentle white |

The app's internal enum calls the V006+ values `V006_CLEAN`, `V006_SOFT`, etc.;
the table above uses the marketing names from the public `oralb-ble` parser.

### FF08 — Brushing time

```
[minutes, seconds]
```

### FF09 — Quadrant

```
[quadrant, ?, total_quadrants]
```

`quadrant` low 3 bits: `0` none, `1`–`6` first–sixth, `7` last.
`total_quadrants` low 3 bits.

### FF0A — Smiley

One byte: `0` off, `1` standard, `2`–`11` firmware-specific faces.

### FF0B — Pressure

Older protocols (V001–V006), one byte:

```
bit 7: high pressure
bit 6: motor speed reduced
```

V007+ (10 bytes):

```
byte 0: 0 low, 1 normal, 2 high
bytes 1-2: record A timestamp (u16 LE)
bytes 3-4: record A force (u16 LE)
bytes 5-6: record B timestamp (u16 LE)
bytes 7-8: record B force (u16 LE)
byte 9: identifier
```

For V008/V009 the app divides the angle field by 100 to get degrees
(`PressureDataWithMotor.motorAngleInDegrees`).

### FF0D — Sensor data

`SensorData` is a tagged union selected by byte 0:

| Selector | Type | Layout |
|---:|---|---|
| 7 | `CalibrationData` | 3 × int16 calibration X/Y/Z |
| 8 | `HighResolutionMotionData` | 3 × int16 motion X/Y/Z |
| 16 | `DashboardData` | status + timestamp + gyro XYZ + motion XYZ |
| 18 | `GyroMotionData` | timestamp + gyro XYZ + motion XYZ |
| 19 | `MotionData` | timestamp + motion XYZ |
| 32 | `DashboardData` (V006) | as above |

This is the raw data used by the app's 3D teeth-tracking / AI recognition.
It is not needed for status sensors, but it is available.

### FF0E — Dashboard data stream

```
byte 0: status (1 first package, 2 packages pending, 8 last package, 0xF0 session id invalid)
byte 1: record count
then count × 8 bytes:
  u16 LE timestamp, int8 gyro X/Y/Z, int8 motion X/Y/Z
```

### FF29 — Selected data / session data

`FF29` is a window into a selected record. The selector is written to `FF21`:

- `02 <index>` selects a stored session (index 0..N-1).
- `02 FA` / `02 FB` selects service data A/B.
- `02 FC`..`02 FF` selects software versions / build dates.
- `05 <id>` selects metadata (device UUID, PCBA, controller versions, …).

The payload is then read from `FF29`. See §5 and §6.

---

## 5. Session records

Session slots are selected with `FF21 = 02 <index>` and read from `FF29`.
The app scans:

- 20 slots for V001,
- 30 slots for V002–V005,
- 250 slots for V006–V008 (the background sync uses 250).

An invalid slot is either all `0x44` (`'D'`) or all `0xFF`.

### V001 (16 bytes)

| Offset | Field |
|---:|---|
| 0–3 | start time, u32 LE seconds since 2000-01-01 |
| 4–5 | duration, u16 LE seconds |
| 6 | on-event count |
| 7 | mode |
| 8–9 | high-pressure time, u16 LE × 10 (100 ms units) |
| 10 | high-pressure event count |
| 11 | final battery level |
| 12–15 | last full load, u32 LE seconds since 2000-01-01 |

### V002–V006 (16 bytes)

| Offset | Field |
|---:|---|
| 0–3 | start time |
| 4–5 | duration |
| 6 | on-event count |
| 7 | mode |
| 8–9 | high-pressure time (× 10 for V002/V003, seconds otherwise) |
| 10 | high-pressure event count |
| 11 | final battery level |
| 12–13 | `configured_time` (13 bits) + `number_of_sectors` (3 bits) |
| 14–15 | `session_id` (13 bits) + `user_id` (3 bits) |

### V007–V008 (21 bytes)

| Offset | Field |
|---:|---|
| 0–3 | start time |
| 4–5 | `session_id` (13 bits) + `user_id` (3 bits) |
| 6–7 | `configured_time` (13 bits) + `number_of_sectors` (3 bits) |
| 8–9 | duration, seconds |
| 10–11 | high-pressure time, 100 ms units |
| 12–13 | low-pressure time, 100 ms units |
| 14 | average pressure, 100 mN |
| 15 | maximum pressure, 100 mN |
| 16 | high-pressure event count |
| 17 | low-pressure event count |
| 18 | on-event count |
| 19 | mode |
| 20 | final battery level |

### V009 (23 bytes)

Same as V007–V008 plus:

| Offset | Field |
|---:|---|
| 21 | tongue brushing time, seconds |
| 22 | eco settings state (`0` disabled, `1` enabled, `255` not available) |

The app's `SessionData` object exposes all of these; the Home Assistant
integration maps the most useful ones to sensors and fires an
`oralb_ble_session` event for every new session.

---

## 5a. Sectors, quadrant timers and the mouth map

There are **two different concepts** in the app, and it is important not to
confuse them:

### The sector/quadrant timer (firmware)

The brush divides a brushing session into a small number of **sectors**
(also called quadrants). It runs a timer per sector, vibrates when a sector
ends, and advances to the next one. This is a *timer*, not a position sensor.

Encoding:

- Advertisement byte 8 (`progress`) low 3 bits: current sector.
  `0` = none, `1`–`6` = first–sixth, `7` = "last" sentinel.
- Advertisement byte 10 (`total_quadrants`) low 3 bits: total sectors.
- `FF09`: `[quadrant, ?, total_quadrants]`.
- Session record: `number_of_sectors` is the 3-bit field at bits 13–15 of the
  `configured_time` word (see §5).
- `FF26` quadrant timers: eight uint16 LE values, one per sector. The app's
  `QuadrantTimer` model supports `PROFESSIONAL` (fixed 30 s per sector),
  `CUSTOM` (the eight values), and `DISABLE`.

The app's `CharacteristicParser.L0()` maps the progress byte to
`ToothbrushQuadrant`:

| progress & 7 | enum | meaning |
|---:|---|---|
| 0 | `NO_QUADRANTS_DEFINED` | no active sector |
| 1 | `FIRST_QUADRANT` | 1st |
| 2 | `SECOND_QUADRANT` | 2nd |
| 3 | `THIRD_QUADRANT` | 3rd |
| 4 | `FOURTH_QUADRANT` | 4th |
| 5 | `FIFTH_QUADRANT` | 5th |
| 6 | `SIXTH_QUADRANT` | 6th |
| 7 | `LAST_QUADRANT` | last (real number = total count, or 4 if absent) |

The enum also has `SEVENTH_QUADRANT`, `EIGHTH_QUADRANT` and
`UNKNOWN`/`NO_QUADRANTS_DEFINED`, so firmware can support up to eight
sectors even though the 3-bit advertisement field only names six plus the
"last" sentinel.

This is what the Home Assistant integration exposes as:

- `sensor.quadrant` — `none`, `1st` … `6th`, `last`
- `sensor.sector` — numeric 0–7
- `sensor.sectors_per_session` — total sectors
- `sensor.last_session_sectors` — sectors stored with the last session

### The mouth coverage map (phone-side AI)

The app's coloured mouth map is **not** sent by the brush. It is computed on
the phone from the handle's motion data:

1. The brush streams accelerometer/gyro/dashboard data over `FF0D`
   (`SensorData`) and `FF0E` (`DashboardDataStreamChunk`).
2. The app feeds it to the TensorFlow "Comino" model
   (`assets/tensorflowmodels`, `assets/pt20c25hz25ws`, …).
3. The model outputs one of 20 `CominoZone` classes: 16 detailed zones
   (top/bottom × right/centre/left × outside/onside/inside), three
   aggregate zones (`RIGHT_OUTSIDE`, `LEFT_OUTSIDE`, `CENTER_OUTSIDE`) and
   `OUT_OF_MOUTH`.
4. `SixteenZoneCoverageRecorder` accumulates brushing time per detailed
   zone; `SixZoneCoverageRecorder` aggregates that to six zones:
   top-right, bottom-right, bottom-left, top-left, top-centre,
   bottom-centre (+ out-of-mouth / tongue).
5. Coverage per zone is:

   ```
   coverage % = min(brush_time, completion_time) / completion_time * 100
   ```

   The app stores `brushTime`, `pressureTime` and `completionTime` per zone
   (`SixZone` / `SixteenZone` models) and the room database tables
   `RoomSixZoneCoverage` / `RoomSixteenZoneCoverage`.
6. The computed map is uploaded to the cloud as the `zonedBrushTime` and
   `zonedPressureTime` AWSJSON fields of the `CreateBrushingSession`
   mutation. It is not a GATT field.

The session record itself only contains `number_of_sectors` and the
configured time; it does **not** contain per-zone coverage percentages.
Therefore a local integration can report the sector timer but cannot
reconstruct the app's coverage map without also capturing and running the
motion model.

### What a local integration can and cannot do

| Data | Available over BLE? | Where |
|---|---|---|
| Current sector / total sectors | yes | advertisement byte 8/10, `FF09` |
| Per-sector timer configuration | yes | `FF26` |
| Session duration, pressure, mode, sector count | yes | `FF29` session record |
| Per-zone coverage percentages | **no** | computed by the phone from `FF0D`/`FF0E` + TFLite |
| Raw accelerometer/gyro/dashboard stream | yes | `FF0D`, `FF0E` |
| The app's 6/16-zone map | **no** | app-side `Comino` model + database |

Reconstructing the map on a Home Assistant host is theoretically possible:
record `FF0D`/`FF0E` during a session and run the same `Comino` model
(`libtptGRU3.so` / `libtptGRU6.so` and the TFLite assets) offline. That is a
separate project; the integration in this workspace deliberately stops at
the sector timer and session statistics.

---

## 6. Metadata

Metadata is read with `FF21 = 05 <id>` followed by a read of `FF29`.

| ID | Metadata | Layout |
|---:|---|---|
| 1 | Device UUID | 16 raw bytes, rendered as a UUID string |
| 2 | Business unit | 1 byte |
| 3 | BLE profile | 1 byte |
| 4 | Device type | 1 byte |
| 5 | Device PCBA | `[5, pcba]` |
| 6 | BLE controller SW | `[6, prefix, bootloader, build, prefix2, number2, build2]` |
| 7 | System controller 1 | `[7, ?, media, hw_cfg, ?, ?, mem_map, ?, ?, info_sector]` |
| 8 | System controller 2 | `[?, ?, ?, second_controller]` |
| 9 | Git commit hash | ASCII |
| 10 | GCAS information | TLV |
| 255 | Sonos type | sub-model byte |

Data selectors (`FF21 = 02 <id>`):

| ID | Data |
|---:|---|
| 250 | Service data A |
| 251 | Service data B |
| 252 | Secondary controller software version |
| 253 | Main controller software version |
| 254 | Time of build |
| 255 | Date of build |

`ServiceDataA` (V005+): 16 bytes — `[u16, u16, u32, u32, u32]`.
`ServiceDataB` (V005+): 16 bytes — eight u16 LE values.

---

## 7. Configure / Control channel (FF21)

`FF21` is a single characteristic with two command namespaces. The first byte
selects the namespace.

### Configure selectors

| Setting | Value | Wire bytes (V007+) | Wire bytes (V001–V006) |
|---|---:|---|---|
| Extend connection | 0 | `31 <seconds>` | `31 <seconds>` |
| Read parameter | 1 | `01 <param>` | `01 <param>` |
| Read data | 2 | `02 <param>` | `02 <param>` |
| Clear notifications | 3 | `03 <param>` | `03 <param>` |
| Calibration read | 4 | `04 <param>` | `04 <param>` |
| Read metadata | 5 | `05 <param>` | `05 <param>` |
| Device color read | 18 | `12 <param>` | `12 <param>` |
| RTC | 38 | `26` | `37 26` |
| Brush timer | 40 | `28` | `37 28` |
| Brush modes | 41 | `29` | `37 29` |
| Quadrant timers | 42 | `2A` | `37 2A` |
| Tongue time | 43 | `2B` | `37 2B` |
| Pressure configuration | 44 | `2C <param>` | `2C <param>` |
| My color | 47 | `2F` | `37 2F` |
| Dashboard | 48 | `30 <param>` | `30 <param>` |
| Refill reminder | 49 | `31` | `37 31` |
| Reset settings | 50 | `32 52` | `32 52` |
| Smart guide | 51 | `33 <param>` | `33 <param>` |
| Factory reset | 52 | `34 52` | `34 52` |
| Start week day | 80 | `50 <param>` | `50 <param>` |
| Flight mode | 71 | `47` | `47` |
| Debug command | 240 | `F0 <param>` | `F0 <param>` |

The older `37 xx` prefix is the app's `Configure.a()` helper: it prepends
`0x37` to the setting byte for protocols before V007. Note that
`EXTEND_CONNECTION` and `REFILL_REMINDER` share the byte `0x31`: with a
seconds byte it means "extend connection"; a bare `0x31` selects the refill
reminder.

### Control commands

Control commands are written as `10 <command>`. The four motor-ramping
commands use `2E <command>`, and the tongue-time/pressure commands use
`<command> <parameter>` with no namespace prefix (from `Control.build()`).

| Command | Value | Meaning |
|---|---:|---|
| `RESET_MEMORY_TIMER` | 41 | reset the session memory timer |
| `MY_COLOR_DISABLE` / `ENABLE` | 48 / 49 | LED color off/on |
| `STOP_TIMER_SIGNAL` | 32 | stop the timer vibration |
| `SET_MODE` | 1 | set mode (parameter = mode) |
| `MOTION_DISABLE` / `ENABLE` | 64 / 65 | motion sensor |
| `HIGH_RESOLUTION_MEASUREMENT` | 66 | high-resolution motion |
| `PRESSURE_DISABLE` | 80 | pressure feedback off |
| `RAINBOW_*` | 96/97/98 | rainbow LED |
| `CHARGE_ILLUMINATION_*` | 112/113 | charge LED |
| `TRIGGER_CONNECTION_ILLUMINATION` | 131 | connection LED |
| `TRIGGER_SHORT/LONG_STUTTER` | 33/34 | haptic |
| `TRIGGER_SHORT/LONG_VISUAL_SIGNAL` | 35/36 | visual |
| `SET_TO_DAILY_CLEAN` | 1 | mode |
| `SET_TO_PRO_CLEAN` | 7 | mode |
| `SET_TO_SENSITIVE` | 2 | mode |
| `SET_TO_WHITENING` | 4 | mode |
| `SET_TO_MASSAGE` | 3 | mode |
| `SET_TO_TONGUE_CLEAN` | 6 | mode |
| `SET_TO_DEEP_CLEAN` | 5 | mode |
| `MOTOR_OFF` | 0 | motor off |
| `MODE_SWITCHING_ON` / `OFF` | 14 / 15 | mode switching |
| `DISABLE_ALL_MOTOR_RAMPING` | 0 | ramping |
| `ENABLE_SOFT_START_ONLY` | 1 | ramping |
| `ENABLE_LOW_CHARGE_ONLY` | 2 | ramping |
| `ENABLE_ALL_MOTOR_RAMPING` | 3 | ramping |
| `TONGUE_TIME` | 43 | `2B <param>` |
| `PRESSURE_CONFIGURATION` | 44 | `2C <param>` |
| `ECO_SETTINGS_ENABLE` / `DISABLE` | 145 / 144 | eco |

### Reading a value

The app's `BluetoothAPI.P3` does:

1. Write the selector to `FF21` (with response).
2. Read `FF29`.

`BluetoothAPI.Q2` is a plain read of a characteristic; `n2` sets up
notifications. The Home Assistant integration uses plain reads and a short
delay between the selector write and the `FF29` read.

---

## 8. Settings writes

The app writes a selector to `FF21` and then writes the value to the
dedicated characteristic. Important examples:

### Time sync

```
FF21 <- 26            (V007+; 37 26 for older)
FF22 <- u32 LE seconds since 2000-01-01
FF23 <- (offset_hours * 4) + (offset_minutes / 15)
```

The timezone byte is signed; negative offsets wrap modulo 256.

### Brush timer / signals (FF24)

One byte of flags:

```
bit 0: vibrate enabled
bit 1: vibrate all signals
bit 2: flash enabled
bit 3: flash all signals
```

### Brush modes (FF25)

One byte per mode; the app writes the list of enabled modes. The order is the
order shown in the app.

### Quadrant timers (FF26)

Eight uint16 LE values (one per quadrant/sector). Writing the full set
replaces the timer configuration.

### My color (FF2B)

```
[r, g, b, identifier]
```

Follow with a `Control` `MY_COLOR_ENABLE` (`10 31`) to apply it.

### Refill reminder (FF2D)

The app's `RefillReminder` state machine:

- V007+: `0` on, `1` reset, `2` snooze, `-2` interval, `-1` off, other =
  stage.
- V001–V006: `0` legacy on (handle control), `1` legacy on (app control),
  `-1` legacy off.

### Pressure configuration (FF28)

```
[pressure_signal_enabled, reduced_motor_speed_enabled]
```

### Smart guide / start week day

`FF21 <- 33 <0|1>` for smart guide, `FF21 <- 50 <0|1|2>` for the first day
of the week (Monday/Saturday/Sunday).

> **Do not** write `FACTORY_RESET` (`34 52`) or `RESET_SETTINGS` (`32 52`)
> unless you intend to wipe the brush. They are documented for completeness
> and are not exposed by the Home Assistant integration.

---

## 9. OTA / firmware update

### Characteristics

| UUID | Direction | Purpose |
|---|---|---|
| `FF81` | write | command |
| `FF82` | write | payload (current protocol) or legacy payload 1 |
| `FF83` | write | legacy payload 2 |
| `FF84` | read/notify | state / error |
| `FF85` | read/notify | transferred size |

### Commands (`FF81`)

Current protocol (`OTACommand.Command`):

| Value | Command |
|---:|---|
| 0 | standby |
| 17 (`0x11`) | initialize |
| 19 (`0x13`) | finish upload |
| 26 (`0x1A`) | flash firmware |
| 27 (`0x1B`) | reset |
| 30 (`0x1E`) | error |

Legacy protocol (`LegacyOTACommand.Command`):

| Value | Command |
|---:|---|
| 0 | standby |
| 17 | initialize |
| 18 | verified size |
| 26 | flash firmware |
| 27 | reset |
| 30 | error |

### States (`FF84`, `OTAInfo.State`)

| Value | State |
|---:|---|
| 0 | standby |
| 17 | app initialized |
| 18 | app verify size |
| 19 | app ready for payload |
| 20 | app unknown pause |
| 21 | app completed |
| 22 | app completed not charged |
| 30 | app error |
| 238 (`0xEE`) | error |
| 170 (`0xAA`) | flash started |
| 255 (`0xFF`) | flash confirmed |

### Current transfer (V006+)

1. `FF21 <- 31 FF` (extend connection).
2. `FF81 <- 11` (initialize).
3. Wait for `FF84 = 0` (standby) → send `FF81 <- 11` again.
4. On `FF84 = 17` (app initialized), send the firmware in 244-byte chunks to
   `FF82`. The last chunk is padded with `0xFF`.
5. On `FF84 = 19` (ready for payload), keep sending; the device reports
   progress via `FF85` and `FF84`.
6. When `FF85 >= firmware length`, send `FF81 <- 13` (finish upload).
7. Wait for `FF84 = 21` (completed) → `FF84 = 170` (flash started) →
   `FF84 = 255` (flash confirmed).
8. Send `FF81 <- 27` (reset) or `FF81 <- 0` (standby).

The app's `CurrentOTAUpdater` treats `APP_VERIFY_SIZE` (18) as unexpected and
`APP_COMPLETED_NOT_CHARGED` (22) / `APP_UNKNOWN_PAUSE` (20) as errors.

### Legacy transfer (V001–V005)

1. Write the 4-byte firmware size to both `FF82` and `FF83`
   (`LegacyOTAPayLoad1` / `LegacyOTAPayLoad2`).
2. Send 40-byte groups: the first 20 bytes to `FF82`, the next 20 bytes to
   `FF83`, with a 4-byte offset prefix (`BluetoothAPI.Z1`).
3. Send `FF81 <- 1A` (flash firmware), then `FF81 <- 1B` (reset).

The legacy updater adds a configurable delay between payloads to avoid
overrunning the brush.

### Firmware format

- **Sonos / iO (TI CC2640)**: `sign_*.bin`, 114,945 bytes for the public
  V025/V050 images, 123,137 bytes for the bundled `0x6E` image. The first
  ~10 KB are high-entropy (signature/encrypted header), followed by the
  plaintext application with the GATT table and strings such as
  `Oral-B Toothbrush`.
- **iO4 / iO5 / iO6–iO10 (Silicon Labs EFR32)**: `.gbl` Gecko Bootloader
  update images, signed with ECDSA-P256. The public images are 272,540 B
  (iO4), 284,336 B (iO5), 341,864 B (E-Platform V88).

See `FIRMWARE.md` for the manifests, URLs and hashes.

---

## 10. Charger (iO Sense) — bonus

The app also supports a "charger" device with a separate GATT service:

| UUID | Purpose |
|---|---|
| `3C00` | `ChargerCommand` — command channel |
| `3C01` | `ChargerRead` |
| `3C02` | `ChargerWrite` |
| `3C03` | `ChargerStatus` |

The charger is an IoT gateway: the app configures Wi-Fi, MQTT host/port,
TLS certificates, discovery URL/token, display text/brightness, night light,
clock, touchpad, auto-update, brush connection policy, LED feedback and
firmware updates. It is out of scope for the toothbrush Home Assistant
integration, but the model classes are present in
`codes.alchemy.oralb.blesdk.data.characteristic.model.Charger*`.

---

## 11. Protocol versions and capabilities

| Version | Typical devices | Notes |
|---|---|---|
| V001 | very early Smart Series | 20 sessions, no UUID/metadata |
| V002–V003 | Genius / Smart Series | 30 sessions, RTC |
| V004–V005 | Genius X / Smart Series | battery seconds, service data |
| V006 | iO (Big TI), later Genius | 250 sessions, dashboard data |
| V007 | iO | access control, refill reminder, Sonos metadata |
| V008 | iO4 / iO5 | access control, extended battery |
| V009 | iO6–iO10 E-Platform | tongue time, eco settings |

Capability rules from `Brush`:

- `requiresReadParamUpdates`: V001–V007.
- `supportsAccessControl`: V008+.
- `supportsBrushInfo`: V006+.
- `supportsDeviceUUID`: V007+.
- `usesRefillReminder`: V007+.
- `usesSonosMetaData`: V007+.
- `usesTongueTime`: V002–V006.

---

## 12. What the Home Assistant integration uses

- Passive advertisements for live state, mode, pressure, time, quadrant,
  smiley, new-session flag and RSSI.
- GATT reads for battery, state, button, mode, time, quadrant, smiley and
  pressure.
- GATT metadata reads once per day.
- GATT session scans after a brushing session or on demand.
- Optional clock sync and session sync buttons.
- No OTA, no factory reset, no settings writes other than time sync.
