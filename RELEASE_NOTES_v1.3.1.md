## DeyeCloud v1.3.1

Packaging fix. No behaviour changes and no entity or unique-ID changes.

### Fixed

- **Stale bytecode in the release zip** - the release job runs the test suite in the dev container before building the artifact, so `__pycache__` was written into the checkout and copied into the zip. v1.2.0 and v1.3.0 shipped 18 and 19 compiled `.pyc` files respectively. `build_zip` now filters `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `*.pyc`, `*.pyo`, and `.DS_Store` out of the archive and writes entries in sorted order so the layout does not depend on filesystem iteration order.

The `.pyc` files were tagged for CPython 3.14, so most installs ignored them and behaviour was unaffected. They are removed because shipping compiled output that can shadow its own source does not belong in a release artifact, and nothing in the test suite exercised the packaging script.

### Technical notes

- No integration code changed in this release. v1.3.1 contains exactly the same runtime code as v1.3.0; only the artifact contents differ.
- The archive is now 29 entries instead of 48, all of them source files.
- If you installed v1.3.0, no action is required. The leftover `.pyc` files are replaced on update.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.

Entity unique IDs are unchanged from v1.3.0.
