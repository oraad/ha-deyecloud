## DeyeCloud v1.1.0

Renames user-facing **Plant** terminology to **Station**, simplifies device names, and migrates existing installs automatically.

### Changed

- **Plant → Station** in UI strings, config flow steps, options, and subentry type (`station`).
- **Device names** show the device type only (e.g. `Inverter`, `Battery`). When multiple devices share a type in one station, the serial is appended (e.g. `Battery 05403000CA180191`).
- **Entity unique IDs** use the `station_{station_id}_…` prefix instead of `plant_{station_id}_…`.
- **Config entry version 2** migrates subentry type, `selected_stations` options key, and entity registry unique IDs on upgrade.
- **Internal renames** for clarity (`StationCoordinatorData`, `async_sync_station_subentries`, etc.).

### Migration (automatic)

On first load after upgrading, the integration:

1. Recreates `plant` subentries as `station` subentries (same data and titles).
2. Renames `selected_plants` → `selected_stations` in entry options.
3. Updates entity registry unique IDs from `plant_…` to `station_…`.

No manual reconfiguration is required. Reload the integration once after upgrading if entities do not appear immediately.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.
3. Reload the DeyeCloud integration if needed.

DeyeCloud API station titles (e.g. a user-named “Home Plant” in the app) are unchanged — only integration terminology and device naming were updated.

### Verification

- 98 tests, 95%+ coverage
