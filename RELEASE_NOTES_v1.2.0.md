## DeyeCloud v1.2.0

Improves sensor naming, device-class mapping, and display precision; renames the COLLECTOR device type label to match the DeyeCloud API.

### Changed

- **Collector device label** — `COLLECTOR` devices now show as **Collector** instead of **Concentrator** (matches the API `deviceType`).
- **Station metric names** — station sensors use clearer labels (e.g. **Solar generation**, **Grid import**, **Battery SOC**) instead of raw API keys.
- **Device sensor names** — untranslated measure points keep the API catalog name (e.g. **PV1 Voltage**); common keys use English translation strings.
- **Display precision** — sensors suggest appropriate decimal places by unit and device class (e.g. 0 for watts and SOC, 2 for kWh).
- **Online binary sensor** — entity translation moved from sensor to binary_sensor strings (no behavior change).

### Fixed

- **Energy vs power classification** — measure points with a `kWh` unit are no longer forced to **power** because the key ends in `_power`.
- **Unit mapping order** — explicit units (%, V, A, kWh, etc.) are evaluated before key-suffix heuristics, improving device-class accuracy.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.
3. Reload the DeyeCloud integration to refresh device names (e.g. Collector) and sensor labels.

Existing entity unique IDs are unchanged; friendly names and display precision update on reload.
