# Oral-B firmware: bundled images, public manifests and OTA format

The Oral-B Android app does **not** bundle the brush application firmware in
its APK (with one exception, see §1). It downloads firmware from a public
endpoint. This document records what is in the APK, the endpoint, the
manifests, the images we downloaded and their formats.

> All firmware images below were downloaded from URLs published in the
> official app's own manifest endpoint. Their MD5 checksums match the
> manifest values. They are vendor-signed release images, not extracted
> secrets.

---

## 1. What is inside the APK

| File | Size | What it is |
|---|---:|---|
| `res/raw/sonos_firmware_0x6e.bin` | 123,137 B | Bundled Sonos / TI CC2640 OTA image (`0x6E` = 110) |
| `assets/tensorflowmodels/models/*.tflite` | ~1.3–1.6 MB each | AI brushing-recognition models (Comino / iO) |
| `assets/pt20c25hz25ws/*.bin` | 1,214,104 B each | Position-tracking models (25 Hz) |
| `assets/pt20c26hz26ws/*.bin` | 1,214,104 B each | Position-tracking models (26 Hz) |
| `assets/pt20c6p5hz26ws/*.bin` | 1,214,104 B each | Position-tracking models (6.5 Hz) |

The bundled `sonos_firmware_0x6e.bin` is the only brush firmware image in the
APK. It is a Sonos-platform image: it contains the same GATT table
(`A0F0FF00` / `A0F0FF20` / `A0F0FF80`), the characteristic names (`Device
State`, `Battery Level`, `OTA Command`, …) and the string `Oral-B Toothbrush`
at offset `0x1318d`.

```
MD5     bc098829907f55b723f17108c1eeac1c
SHA-256 3f59fc3c6167da0e1f890d29f0d1325a7dabac8179c365be081e8265f0d1b946
```

It is **not** byte-identical to the public V025 or V050 Sonos images; it is a
different build (likely a newer `0x6E`/110 build for a specific retail
variant). Its first ~10 KB are high entropy (signature/encrypted header),
followed by plaintext application code and strings.

The TensorFlow models are not firmware; they implement the app's 3D teeth
tracking / AI brushing recognition and run on the phone.

---

## 2. Public firmware endpoint

The app builds the manifest URL in
`com.pg.oralb.oralbapp.util.OTAUtils.t()`:

```
https://fw.iot-dev.alchemy.codes/oralb/0x<deviceType>/0x<deviceType>.json
```

`<deviceType>` is the **4-digit uppercase hex** device type from the
advertisement (`String.format("0x%04X", brush.deviceType.value)`). For
example, an iO5 (type `0x35`) uses:

```
https://fw.iot-dev.alchemy.codes/oralb/0x0035/0x0035.json
```

China builds use the mirror:

```
https://pg-fw.it-pg.com.cn/oralb/0x<deviceType>/0x<deviceType>.json
```

The manifest is a JSON document followed by a signature block:

```
{ ...json... }
---------- SIGNATURE ----------
<base64 RSA-2048 SHA-256 signature>
```

The app verifies the signature with the RSA public key in
`res/raw/manifest_public`:

```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyZj/xJrqyuP2+Xr+Pt+k
GQMn7MYZBTVPdRMkF+JFGkUKqiVx1V+11NnO9A+8Q8UYf43TTy6t6NKK+qQMeocG
XP81aCgOcPzg0X3r1J2ODgIgBXkYn5al9qCi2Ktxfd2IGrRVZJOTFocYSxIqE/M3
iZIVWYrpToQV++5H4rXFX3bKFj+tOUH7PjZ02/1GbsfaOqs91m19+li3TyCQVxhy
MVK2MzDNKGEZjtH+TFqOHK9gA40gNAuN9173otJ/cJU/ELXO6WfPbfbhdtwZBpUW
fmMSN/6trhTsN9PnUBcF/9olBGiX4/mxX1CUHoHrrA3UngSnKXADO5SKIvTqOpVm
UQIDAQAB
-----END PUBLIC KEY-----
```

Only four device-type manifests are currently published:

| Device type | File | Models | PCBA | HW config |
|---:|---|---|---|---|
| `0x0031` | `0x0031.json` | Sonos iO (M7/M8/M9) | `0x06`, `0x0B`, `0x0C` | `0x01` (color), `0x02` (greyscale) |
| `0x0034` | `0x0034.json` | iO4 | `0x0A`, `0x0B`, `0x10`, `0x11` | `0x00` |
| `0x0035` | `0x0035.json` | iO5 | `0x0C`, `0x12`, `0x14` | `0x00` |
| `0x0036` | `0x0036.json` | iO6–iO10 (E-Platform) | `0x06`, `0x07` | `0x01`, `0x02` |

Other device types return `403` (no manifest published).

### Manifest fields

```json
{
  "signatureAlgorithm": "SHA256WithRSA",
  "signatureEncoding": "base64",
  "hardwareMapping": [
    {
      "PCBA": ["0x06", "0x0B", "0x0C"],
      "hardwareConfiguration": ["0x01"],
      "images": [
        {
          "notes": "Small TI FW50 ROW M8 M9 color incl Rev5 - Deployment A",
          "url": "https://fw.iot-dev.alchemy.codes/oralb/0x0031/full/...bin",
          "version": "0x32",
          "minRequiredVersion": "0x15",
          "supportedBootloaderVersions": ["0x03"],
          "supported2ndControllerVersions": ["0x21"],
          "supportedInfoSectorVersions": ["0x00"],
          "supportedMemoryMapVersions": ["0x00", "0x01"],
          "supportedMediaContentVersions": ["0x0C"],
          "fileChecksum": "04e96b7a2d41fb8a0356f5e4564c6580",
          "fileChecksumType": "MD5",
          "countries": ["*"]
        }
      ]
    }
  ]
}
```

The app matches the brush's PCBA, hardware configuration, bootloader,
second-controller, info-sector, memory-map and media-content versions against
the manifest, filters by country, then picks the highest `version` that is
newer than the current firmware.

---

## 3. Downloaded images

All files below are in `fw/`. MD5 values match the manifests.

| File | Size | Version | MD5 | SHA-256 |
|---|---:|---:|---|---|
| `sign_201102_OTA_Sonos_CC2640_V025_ColorDisplay.bin` | 114,945 | `0x19` (25) | `d9b2a460ca493afba62018aceff412a8` | `01827613b0ca8c78d566dc04972b7454e41732d0ab73b729bd4b4902280021cb` |
| `sign_210205_OTA_Sonos_CC2640_V050_ColorDisplay.bin` | 114,945 | `0x32` (50) | `04e96b7a2d41fb8a0356f5e4564c6580` | `6e4af3e6ab6f7b4bb96cb9d16a6d1dfd943f6cd0f636f399f8162eeed331ce33` |
| `sign_210205_OTA_Sonos_CC2640_V050_GreyscaleDisplay.bin` | 114,945 | `0x32` (50) | `eb1ac9503c1cacec20862fe07efb71a1` | `6a82a3a08d20b9eaba60b73a826330bc0f48bc0534bdfc98c1c016d80315f582` |
| `IO4_G011_V42_signed.gbl` | 272,540 | `0x2A` (42) | `43717a96601069b85b2f1c48a8376bd2` | `e13ec60ea7bd04f8569a99c347ce59bce67be6ac1511149d30a67b4bcaba5bf1` |
| `IO5_G011_V42_signed.gbl` | 284,336 | `0x2A` (42) | `19947364408a67ca0732b55801bb12e7` | `0f323b13a170a7c4499e10254c6506f97d4367a635df99e638b335368b4a27ff` |
| `E-Platform_G008_V88_signed.gbl` | 341,864 | `0x58` (88) | `3d2a32b68830fb57b3b0ec0e350ed744` | `b4c4d8de8b53d43f8bcf2958d121917d6d36c830379dc07ef604f31ffec69aea` |

The exact SHA-256 values are printed by:

```bash
sha256sum fw/*.bin fw/*.gbl
```

### Sonos / TI CC2640 images

`file(1)` reports "data"; the images are TI CC2640 OTA containers with a
high-entropy header (signature/encryption) followed by the plaintext
application. They contain:

- the `B-larO` / `SMGP` little-endian base UUID,
- the GATT table (service `FF00`, `FF20`, `FF80`),
- characteristic names (`Handle ID`, `Device State`, `Battery Level`,
  `OTA Command`, …),
- the device name `Oral-B Toothbrush`,
- the bootloader strings `FW Version: %c%u:%u`, `BW Version: %c%u:%u`,
  `SLOT1 pending`, `Image 1 selected`, `invalid signature`.

The public V025 and V050 color/greyscale images are 114,945 bytes each; the
bundled `0x6E` image is 123,137 bytes.

### iO4 / iO5 / E-Platform images

These are **Silicon Labs Gecko Bootloader (GBL)** update images:

```
$ file IO4_G011_V42_signed.gbl
Silicon Labs Gecko bootloader update image, signed (ECDSA-P256), application image
```

They start with the GBL magic `EB 17 A6 03`, a version/flags header and
tag-length-value records. They are ECDSA-P256 signed and are intended for
the EFR32 MCU in the iO4/iO5/iO6–iO10 handles. The manifest `notes` strings
confirm the target and the OTA wave:

- iO4: "OTA UPDATE iO4 FW V12 to FW V42 - Deployment ILST-00130161 - WAVE 2"
- iO5: "OTA UPDATE iO5 FW V12 to FW V42 - Deployment ILST-00130160 - WAVE 2"
- iO6–iO10: "OTA UPDATE iO6-iO10 FW V68 to FW V88 - Deployment ILST-00130179 - WAVE 2"

---

## 4. OTA transport

The BLE OTA transport is documented in `PROTOCOL.md` §9. In short:

- current protocol (V006+): `FF81` command, `FF82` 244-byte payload chunks,
  `FF84` state, `FF85` transferred size;
- legacy protocol (V001–V005): `FF81` command, `FF82`/`FF83` 20-byte halves
  with a 4-byte offset, then flash/reset.

The firmware image is sent verbatim; the brush's bootloader verifies the
signature (and, for GBL, the ECDSA-P256 signature) before activating it.
The app does not re-sign or re-encrypt the image.

---

## 5. Reproducing the download

```bash
# manifest
curl -sS https://fw.iot-dev.alchemy.codes/oralb/0x0035/0x0035.json -o 0x0035.json

# image URL from the manifest
curl -sS -O https://fw.iot-dev.alchemy.codes/oralb/0x0035/full/IO5_G011_V42_signed.gbl

# verify against the manifest
md5sum IO5_G011_V42_signed.gbl
```

The manifest signature can be verified with the public key above and the
`---------- SIGNATURE ----------` block. The app does this in
`OTAUtils.B()` using `SHA256WithRSA`.

---

## 6. Safety notes

- The images are **release firmware for specific PCBAs**. Flashing the wrong
  image can brick the brush. The manifest's `PCBA`/`hardwareConfiguration`
  and version constraints exist for a reason.
- The Home Assistant integration deliberately does **not** implement OTA.
- The brush must be charged and awake for an update; the app checks battery
  and temperature and refuses the transfer otherwise.
- A failed transfer can leave the brush in the bootloader until a retry; the
  app handles resume/pause states (`APP_UNKNOWN_PAUSE`,
  `APP_COMPLETED_NOT_CHARGED`).
