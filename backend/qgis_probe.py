"""Run with the Python interpreter belonging to QGIS, never the API venv."""

import sys, json, os


def probe():
    from qgis.core import QgsApplication, Qgis, QgsProcessingParameterDefinition

    app = QgsApplication([], False)
    app.initQgis()
    sys.path.insert(0, "/usr/share/qgis/python/plugins")
    plugin = os.environ.get("UMEP_PLUGIN_DIR")
    if plugin:
        sys.path.insert(0, plugin)
    from processing.core.Processing import Processing

    Processing.initialize()
    errors = []
    # Provider registration is deliberately configured rather than inferred from a filename.
    if plugin:
        try:
            import processing_umep

            provider_plugin = processing_umep.classFactory(None)
            provider_plugin.initGui()
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
    registry = QgsApplication.processingRegistry()
    algorithms = []
    for alg in registry.algorithms():
        if "umep" in alg.id().lower() or "solweig" in alg.id().lower():
            algorithms.append(
                {
                    "id": alg.id(),
                    "name": alg.displayName(),
                    "parameters": [
                        {
                            "name": p.name(),
                            "description": p.description(),
                            "type": p.type(),
                            "optional": bool(
                                p.flags()
                                & QgsProcessingParameterDefinition.FlagOptional
                            ),
                        }
                        for p in alg.parameterDefinitions()
                    ],
                }
            )
    result = {
        "qgis_version": Qgis.QGIS_VERSION,
        "providers": [p.id() for p in registry.providers()],
        "algorithms": algorithms,
        "errors": errors,
    }
    print("UMEP_PROBE_JSON=" + json.dumps(result), flush=True)
    app.exitQgis()


if __name__ == "__main__":
    try:
        probe()
    except Exception as e:
        print(
            "UMEP_PROBE_JSON="
            + json.dumps({"error": f"{type(e).__name__}: {e}", "algorithms": []})
        )
        sys.exit(1)
