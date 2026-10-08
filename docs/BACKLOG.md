# Prioritized backlog

1. Scientific SOLWEIG adapter: install/verify UMEP provider, engine-specific weather conversion, wall geometry and sky-view factors, installed parameter validation, scientific fixture comparison, cancellation and version-specific output discovery.
2. Derived data preparation: editable shared grid, buffered processing-boundary tools, explicit reprojection/datum/unit transformations, categorical/continuous resampling, quality masks and full provenance.
3. Weather: distinguish missing intervals from expected cadence, ingestion UI for observed/typical-year/hypothetical classification, timezone cross-checks, verified engine conversions.
4. LiDAR: PDAL metadata/classification inspection, evidence-based building/vegetation separation, terrain extraction, height normalization, common-grid products and quality masks. Never relabel an all-points maximum raster as a building DSM.
5. Scenarios: immutable baseline UI, input replacement controls, dependency-aware geometry cache invalidation, capability checks for non-solid shade structures.
6. Acquisition: opt-in source adapters with coverage/licensing/CRS/datum metadata, checksums, authentication through settings, and download budgets.
7. Additional engines: separate verified URock, SpatialTC, and standalone SOLWEIG adapters, each with its own capabilities and scientific test fixtures.
8. Production hardening: authentication, authorization, quotas, tiled raster cache, worker scheduling/leases, retention, backup/migrations, package/resource limits, deployment configuration, and richer accessible UI/component tests.
