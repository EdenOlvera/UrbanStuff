"""Engine boundaries. Scientific execution must never enter the demo adapter."""

import shutil, os, platform, hashlib, json, subprocess
from functools import lru_cache
from pathlib import Path
from typing import Protocol
import numpy as np
import rasterio
from .geo import LABEL, checksum, inspect_raster


class EngineAdapter(Protocol):
    def capabilities(self) -> dict: ...
    def validate_inputs(self, snapshot: dict) -> list[str]: ...
    def prepare(self, snapshot: dict, work: Path) -> dict: ...
    def run(self, prepared: dict, config: dict, work: Path) -> list[dict]: ...
    def collect_outputs(self, outputs: list[dict]) -> list[dict]: ...


def versions():
    import pyproj, shapely

    return {
        "python": platform.python_version(),
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "numpy": np.__version__,
        "pyproj": pyproj.__version__,
        "shapely": shapely.__version__,
        "demo": "1.0",
    }


class DemoAdapter:
    def capabilities(self):
        return {
            "available": True,
            "synthetic": True,
            "label": LABEL,
            "outputs": ["shade", "mean_radiant_temperature"],
        }

    def validate_inputs(self, snapshot):
        return []

    def prepare(self, snapshot, work):
        from .storage import ROOT, managed_path

        surface = next(
            a
            for a in snapshot["assets"]
            if a["role"] in ("surface_dsm", "building_dsm")
        )
        # Geometry cache deliberately excludes weather and thermal parameters.
        key = hashlib.sha256(
            json.dumps(
                {
                    "inputs": [
                        (a["id"], a["checksum"], a["role"])
                        for a in snapshot["assets"]
                        if a["metadata"].get("kind") == "raster"
                    ],
                    "grid": snapshot["project"].get("grid"),
                    "stage": "geometry-1",
                    "versions": versions(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cache = ROOT / "cache" / key
        cache.mkdir(parents=True, exist_ok=True)
        cached = cache / "geometry.npz"
        with rasterio.open(managed_path(surface["storage_location"])) as src:
            profile = src.profile.copy()
            if cached.exists():
                with np.load(cached) as d:
                    height, mask = d["height"], d["mask"]
                hit = True
            else:
                data = src.read(1, masked=True).astype("float32")
                mask = ~np.ma.getmaskarray(data) & np.isfinite(data.filled(np.nan))
                height = data.filled(0).astype("float32")
                temporary = cache / f"geometry-{os.getpid()}.npz"
                np.savez_compressed(temporary, height=height, mask=mask)
                temporary.replace(cached)
                hit = False
        return {
            "height": height,
            "mask": mask,
            "profile": profile,
            "cache_key": key,
            "cache_hit": hit,
        }

    def run(self, prepared, config, work):
        h = prepared["height"]
        mask = prepared["mask"]
        y, x = np.indices(h.shape)
        # Deliberately illustrative spatial pattern, not a physical solar model.
        shade = (
            (
                np.sin(x / 8)
                + np.cos(y / 11)
                + np.clip(h - np.median(h[mask]), -20, 20) / 20
            )
            > config["solar_altitude"] / 90
        ).astype("float32")
        tmrt = (
            config["air_temperature"]
            + 18 * (1 - shade)
            + 3 * np.sin(x / 17) * np.cos(y / 19)
        ).astype("float32")
        outputs = []
        for role, units, data in [
            ("shade", "fraction", shade),
            ("mean_radiant_temperature", "°C", tmrt),
        ]:
            data[~mask] = -9999
            path = work / f"{role}.tif"
            profile = prepared["profile"].copy()
            profile.update(
                driver="GTiff",
                dtype="float32",
                count=1,
                nodata=-9999,
                compress="deflate",
            )
            with rasterio.open(path, "w", **profile) as dst:
                dst.write(data, 1)
                dst.update_tags(
                    synthetic="true", description=LABEL, quantity=role, units=units
                )
            outputs.append(
                {
                    "id": role,
                    "role": role,
                    "units": units,
                    "synthetic": True,
                    "label": LABEL,
                    "filename": path.name,
                    "checksum": checksum(path),
                    "metadata": inspect_raster(path),
                }
            )
        return outputs

    def collect_outputs(self, outputs):
        return outputs


@lru_cache(maxsize=1)
def qgis_capability():
    from .storage import ROOT

    env = os.environ.copy()
    for key, name in [
        ("XDG_CONFIG_HOME", "qgis-config"),
        ("XDG_CACHE_HOME", "qgis-cache"),
        ("XDG_DATA_HOME", "qgis-share"),
    ]:
        directory = ROOT / name
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    env["QT_QPA_PLATFORM"] = "offscreen"
    python = os.environ.get("UMEP_QGIS_PYTHON", "/usr/bin/python3")
    result = {
        "available": False,
        "qgis_executable": bool(shutil.which("qgis_process")),
        "configured_prefix": bool(os.environ.get("QGIS_PREFIX_PATH")),
        "algorithms": [],
        "version": None,
    }
    try:
        proc = subprocess.run(
            [python, str(Path(__file__).with_name("qgis_probe.py"))],
            capture_output=True,
            text=True,
            env=env,
            timeout=25,
        )
        marker = next(
            (
                line[len("UMEP_PROBE_JSON=") :]
                for line in proc.stdout.splitlines()
                if line.startswith("UMEP_PROBE_JSON=")
            ),
            None,
        )
        probe = (
            json.loads(marker)
            if marker
            else {"error": proc.stderr[-2000:] or "Probe produced no provider metadata"}
        )
        result.update(
            version=probe.get("qgis_version"),
            algorithms=probe.get("algorithms", []),
            providers=probe.get("providers", []),
            probe_errors=probe.get("errors", [])
            or ([probe["error"]] if probe.get("error") else []),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        result["probe_errors"] = [str(e)]
    result["reason"] = (
        "UMEP provider is not installed or registered."
        if not result["algorithms"]
        else "UMEP algorithms detected; installed parameter-to-asset mapping and scientific execution remain unimplemented."
    )
    result["reason"] += " Scientific execution is unsupported; no demo fallback."
    return result


class QgisUmepAdapter:
    def capabilities(self):
        return qgis_capability()

    def validate_inputs(self, snapshot):
        return [self.capabilities()["reason"]]

    def prepare(self, *args):
        raise RuntimeError(self.capabilities()["reason"])

    def run(self, *args):
        raise RuntimeError(self.capabilities()["reason"])

    def collect_outputs(self, *args):
        raise RuntimeError(self.capabilities()["reason"])


class LidarProcessor:
    stages = [
        "inspect classifications",
        "normalize CRS/units",
        "filter outliers",
        "extract ground",
        "separate buildings/vegetation",
        "calculate height above ground",
        "rasterize shared grid",
        "quality masks",
    ]

    def capabilities(self):
        return {
            "pdal_present": bool(shutil.which("pdal")),
            "available": False,
            "stages": self.stages,
            "reason": "LAS/LAZ registration only. Metadata inspection and classification-based preparation are not implemented.",
        }

    def process(self, *args):
        raise NotImplementedError(self.capabilities()["reason"])
