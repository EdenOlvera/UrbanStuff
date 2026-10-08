# Initial implementation plan

The repository was empty, with no AGENTS.md or existing conventions. The selected vertical slice is create project → inspect and declare GeoTIFF → validate → queue explicit demo job → inspect and download outputs.

1. Define Pydantic models, managed storage, and versioned SQLite migration.
2. Implement real raster/weather inspection and actionable validation.
3. Implement separate worker, isolated job subprocess, synthetic adapter, immutable snapshots, provenance package, and geometry cache.
4. Connect a React/TypeScript workspace to these endpoints using MapLibre with a key-free blank basemap.
5. Probe installed QGIS providers; keep real execution unavailable unless its installed interface can be verified and integrated.
6. Test the backend, frontend client, live API/worker workflow, and browser flow. Record supported features and remaining boundaries; save repeatable environment setup/start instructions.
