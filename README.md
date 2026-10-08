# UMEP Studio

A local geospatial workspace for preparing an urban climate analysis. This initial implementation provides a complete **explicit demonstration** workflow. Every generated raster and run is labeled **“Demonstration data — not a scientific simulation.”** Mean radiant temperature is displayed separately from the hypothetical air-temperature parameter. No UTCI or PET is calculated.

## Start

Requirements: Python 3.12, Node 24 (Node 22 should also work), npm 11, Linux for the worker's process supervision. QGIS and PDAL are optional. No account, API key, paid basemap, or cloud storage is needed.

From the checkout root:

```bash
./scripts/install.sh
./scripts/start.sh
```

The frontend runs on port 5173, the API on port 8000, both bound to localhost. Open the frontend with your local browser. This cloud onboarding UI does not offer web preview links. The launcher checks HTTP readiness, supervises all three services, and stops its process groups on exit. Logs are in `.data/logs/`.

Or run three terminals, all in the repository root:

```bash
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
.venv/bin/python -m backend.worker
npm --prefix frontend run dev -- --port 5173 --strictPort
```

Configuration is read from process environment; `.env.example` documents it but is **not automatically loaded**. `UMEP_DATA_DIR` defaults to `.data` relative to the working directory. Keep the same directory across restarts. The API migrates SQLite automatically. Use one worker per data directory; a file lock enforces this.

## Try the workflow

1. Create a project. Draw a polygon with map clicks, or upload GeoJSON. For a quick demo leave the boundary unset; reporting then uses the raster extent.
2. Load the synthetic sample district, or upload `examples/demo-surface.tif`. A normal upload begins with an unassigned role: declare **Combined surface DSM**, metre units, absolute height reference, and the documented vertical datum. The fixture shortcut supplies those synthetic declarations explicitly.
3. Run validation. Errors block demo submission; warnings stay in the manifest. Declare vegetation unknown, confirmed absent, or provided with both canopy and trunk layers.
4. Select the **Demonstration engine**, configure hypothetical temperature and solar altitude, then run it. The separate worker executes outside API request handlers. Watch progress and logs.
5. Explore shade fraction and illustrative mean radiant temperature, adjust visibility/opacity, click for source pixel values, and download GeoTIFFs, the manifest, or the ZIP containing inputs and outputs.

Projects, boundaries, assets, configurations embedded in jobs, history, and completed runs survive restart. Submitted jobs freeze the asset metadata, checksums, configuration, and project boundaries. A restarted worker marks abandoned running jobs interrupted; queued jobs resume. Cancellation terminates a running job subprocess, and successful downloads are unavailable for partial or failed jobs.

## Implemented

- FastAPI/Pydantic API, migration-tracked SQLite, local managed storage, persistent job records, separate worker and isolated subprocess per job.
- Real GeoTIFF metadata/CRS/bounds/resolution/NoData inspection, SHA-256 checksums, explicit semantic declarations, observed/derived/estimated/synthetic provenance.
- Valid GeoJSON polygon drawing/upload, distinct reporting and processing polygons (processing must contain reporting). An uploaded reporting geometry may include an additional `processing` geometry field. GeoJSON is EPSG:4326.
- Shared projected metre grid inferred from the first declared surface DSM. Grid alignment, coverage, units, height references, NoData, required surface/vegetation inputs, duplicate surfaces, and related terrain/surface/trunk/canopy consistency validation.
- Documented timezone-explicit weather CSV ingestion and timestamp/value validation.
- Deterministic synthetic georeferenced output rasters, masked unknown pixels, geometry cache independent of thermal/weather changes, manifest with software versions and stage keys, reproducible packages.
- Bounded 512-pixel backend previews reprojected to WGS84 with nearest-neighbour sampling, server-side original-pixel inspection, valid-pixel summaries inside the reporting polygon. Continuous analysis inputs are never resampled automatically. The map uses a blank offline background; no map service requests.
- QGIS subprocess diagnostics record installed version, providers, available UMEP algorithm parameter definitions, and probe errors. Runtime optional-dependency availability is displayed.
- Immutable baseline reference via duplicated job configuration; API supports role-based input overrides using assets from the same project.

## Partial integrations and limitations

**Scientific processing is not implemented.** QGIS 3.40.6 is installed in the onboarding machine, but its provider registry contains no UMEP algorithms. The QGIS/UMEP adapter performs capability diagnostics only; real wall geometry, sky-view factor, weather conversion, and SOLWEIG execution still need verified installed parameter mapping. A requested scientific job fails with a useful message, never demo results. Official UMEP documentation URLs returned HTTP 403 during onboarding. See [QGIS integration](docs/QGIS.md).

LAS/LAZ uploads are registered and checksummed; point-cloud metadata inspection and PDAL preparation are unsupported even if PDAL is detected. No building/vegetation classification claims are made. URock, SpatialTC, automatic data acquisition, overhead structures, and the standalone SOLWEIG engine are future integrations.

The demo formula is an illustrative spatial pattern, not a solar/thermal model. Uploaded weather and vegetation layers are preserved in provenance but do not drive its formula. Grid editing, source repairs/reprojection, arbitrary scenario geometry editing, unsaved configuration drafts across browser reload, and advanced raster statistics are not implemented. The baseline reference is informational; submitted snapshots are immutable.

One raster at a time is displayed; visibility/opacity controls affect the selected raster. Boundary styles distinguish their geometry only through their shared outline; there is no separate interactive buffer editor. Raster display assumes a local study area without antimeridian crossings; rotated grids are blocked by validation. Previews use percentile colors and are for inspection; pixel queries use original raster values. Reporting summaries select pixels by center. All bands are recorded, but this MVP processes band one.

Uploads default to 100 MB and 25 million raster pixels. Compression, archive size, scientific scheduling, and multiuser quotas need deployment controls. The API has no authentication and is for trusted local development only; it is **not ready for public deployment**. Paths are generated by the server, filenames reject directory components, and all asset/job routes enforce project membership. CORS is limited to configured origins.

## Checks

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
# With scripts/start.sh running:
.venv/bin/python -m scripts.smoke
npm --prefix frontend run test:e2e
```

Browser tests use system Chromium (`/usr/bin/chromium`); set `CHROMIUM_PATH` for another installation. They create a persistent acceptance project in the running API. The smoke test creates a project and uploads a generated GeoTIFF, declares it, validates, queues work in the real worker, inspects a pixel/preview, and downloads the manifest/package. Backend tests use an isolated temporary data directory and exercise worker subprocess recovery, failure reporting, input integrity, weather errors, missing CRS, alignment, NoData versus zero, and project isolation.

`requirements.txt` pins direct Python dependencies; `requirements.lock.txt` pins the installed dependency set used by setup. `frontend/package-lock.json` records the JavaScript dependency graph. Exact versions used in each run are included in its manifest.

See [architecture](docs/ARCHITECTURE.md) and [prioritized backlog](docs/BACKLOG.md).
