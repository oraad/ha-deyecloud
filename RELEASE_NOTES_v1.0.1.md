## DeyeCloud v1.0.1

Bug-fix release that restores entity and device creation on first install and aligns plant telemetry with the live DeyeCloud OpenAPI.

### Fixes

- **Empty plants on first setup** — plant subentries no longer trigger a reload that skips platform setup; entities and devices are created on the first load.
- **Plant-level sensors missing** — `/station/latest` now uses production field names (`generationPower`, `consumptionPower`, `batterySOC`, etc.) instead of stale `*Value` keys.
- **Duplicate devices** — duplicate `deviceSn` rows from `/station/device` are deduplicated, preferring entries with a known `deviceType`.
- **Plant device tree** — a fallback plant status sensor ensures the plant hub device exists when station metrics are unavailable.
- **Measure point log spam** — permanent `/device/measurePoints` failures (`device not supported`, `no upload records found`) are cached and logged at debug level.

### Notes

- **Inverters** expose full telemetry (~50 sensors each) from cached measure-point catalogs and `/device/latest`.
- **Batteries, collectors, optimizers, and meters** typically expose an **Online** binary sensor only; DeyeCloud often does not provide measure-point catalogs for these types.
- Use the **Europe/Asia-Pacific** API region unless your account is in the Americas.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.
3. If plants were empty after v1.0.0, reload the integration or remove and re-add it, then select your plants.

### Verification

- 92 tests, 95%+ coverage
- Validated against live EU API accounts with multiple plants, inverters, batteries, collectors, and optimizers
