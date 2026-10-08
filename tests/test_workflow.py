import io, zipfile, subprocess, sys, time
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from backend import storage as s
from backend.geo import weather, LABEL
from backend.runner import run
from backend.models import SimulationConfiguration


def raster_bytes(crs="EPSG:32632", origin=691000, zero=False):
    with MemoryFile() as f:
        with f.open(
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="float32",
            crs=crs,
            transform=from_origin(origin, 5330000, 2, 2),
            nodata=-9999,
        ) as dst:
            data = (
                np.zeros((10, 10), dtype="float32")
                if zero
                else np.arange(100, dtype="float32").reshape(10, 10)
            )
            data[0, 0] = -9999
            dst.write(data, 1)
        return f.read()


def uploaded(client, pid, **kwargs):
    res = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("surface.tif", raster_bytes(**kwargs), "image/tiff")},
    )
    assert res.status_code == 201, res.text
    a = res.json()
    res = client.put(
        f"/api/projects/{pid}/assets/{a['id']}",
        json={
            "role": "surface_dsm",
            "units": "m",
            "height_reference": "absolute",
            "vertical_reference": "test datum",
        },
    )
    assert res.status_code == 200
    return res.json()


def claim(jid):
    s.execute("UPDATE jobs SET state='running',started_at=? WHERE id=?", (s.now(), jid))


def test_vertical_workflow_manifest_and_download(client, project):
    pid = project["id"]
    a = uploaded(client, pid)
    assert a["metadata"]["width"] == 10 and a["metadata"]["crs"] == "EPSG:32632"
    c = SimulationConfiguration(vegetation="absent").model_dump()
    report = client.post(f"/api/projects/{pid}/validate", json=c).json()
    assert report["valid"]
    assert any(f["code"] == "nodata" for f in report["findings"])
    job = client.post(f"/api/projects/{pid}/jobs", json=c).json()
    claim(job["id"])
    assert run(pid, job["id"]) == 0
    response = client.get(f"/api/projects/{pid}/jobs/{job['id']}")
    assert response.json()["state"] == "succeeded"
    manifest = client.get(
        f"/api/projects/{pid}/jobs/{job['id']}/download/manifest"
    ).json()
    assert (
        manifest["synthetic"]
        and manifest["label"] == LABEL
        and manifest["inputs"][0]["checksum"] == a["checksum"]
    )
    assert len(manifest["outputs"]) == 2 and all(
        o["synthetic"] for o in manifest["outputs"]
    )
    b = manifest["outputs"][0]["metadata"]["geographic_bounds"]
    lon = (b[0] + b[2]) / 2
    lat = (b[1] + b[3]) / 2
    prefix = f"/api/projects/{pid}/jobs/{job['id']}/outputs/shade"
    assert client.get(prefix + "/preview.png").content.startswith(b"\x89PNG")
    assert client.get(prefix + f"/pixel?lon={lon}&lat={lat}").json()["value"] in (0, 1)
    summary = client.get(prefix + "/summary").json()
    assert summary["count"] == 99
    with zipfile.ZipFile(
        io.BytesIO(
            client.get(f"/api/projects/{pid}/jobs/{job['id']}/download/package").content
        )
    ) as z:
        assert "manifest.json" in z.namelist() and any(
            x.startswith("inputs/") for x in z.namelist()
        )
    # Weather-only/thermal change reuses geometry; immutable source declarations preserved.
    job2 = client.post(
        f"/api/projects/{pid}/jobs", json={**c, "air_temperature": 30}
    ).json()
    claim(job2["id"])
    assert run(pid, job2["id"]) == 0
    assert (
        s.job(pid, job2["id"])["manifest"]["stage_versions"]["geometry_cache_hit"]
        == "True"
    )
    assert s.project(pid)["name"] == "Test district"
    s.migrate()
    assert s.project(pid)["name"] == "Test district"


def test_missing_crs_and_alignment(client, project):
    pid = project["id"]
    uploaded(client, pid, crs=None)
    report = client.post(f"/api/projects/{pid}/validate", json={}).json()
    assert not report["valid"] and any(
        f["code"] == "missing_crs" for f in report["findings"]
    )
    p2 = client.post("/api/projects", json={"name": "Aligned"}).json()
    uploaded(client, p2["id"])
    uploaded(client, p2["id"], origin=691001)
    report = client.post(f"/api/projects/{p2['id']}/validate", json={}).json()
    assert any(f["code"] == "grid_alignment" for f in report["findings"])


def test_zero_is_not_nodata(client, project):
    a = uploaded(client, project["id"], zero=True)
    assert a["metadata"]["nodata_fraction"] == 0.01
    report = client.post(
        f"/api/projects/{project['id']}/validate", json={"vegetation": "unknown"}
    ).json()
    assert any(f["code"] == "vegetation_unknown" for f in report["findings"])


def test_weather_validation(tmp_path):
    p = tmp_path / "weather.csv"
    header = (
        "timestamp,air_temperature_c,relative_humidity_pct,global_horizontal_w_m2\n"
    )
    p.write_text(header + "2026-01-01T12:00:00,25,50,400\n")
    import pytest

    with pytest.raises(ValueError, match="UTC offset"):
        weather(p, "UTC")
    p.write_text(header + "2026-01-01T12:00:00Z,25,50,400\n" * 2)
    with pytest.raises(ValueError, match="Duplicate"):
        weather(p, "UTC")
    p.write_text(
        header + "2026-01-01T12:00:00Z,25,50,400\n2026-01-01T14:00:00Z,24,60,300\n"
    )
    assert weather(p, "UTC")["warnings"]


def test_path_and_project_isolation(client, project):
    pid = project["id"]
    for name in ("../x.tif", "..\\x.tif"):
        assert (
            client.post(
                f"/api/projects/{pid}/assets", files={"file": (name, raster_bytes())}
            ).status_code
            == 422
        )
    a = uploaded(client, pid)
    other = client.post("/api/projects", json={"name": "Other"}).json()
    assert (
        client.get(
            f"/api/projects/{other['id']}/assets/{a['id']}/preview.png"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/projects/{pid}/assets", files={"file": ("bad.tif", b"broken")}
        ).status_code
        == 422
    )


def test_scientific_request_fails_without_demo(client, project):
    pid = project["id"]
    j = client.post(f"/api/projects/{pid}/jobs", json={"engine": "umep"}).json()
    claim(j["id"])
    assert run(pid, j["id"]) == 1
    record = s.job(pid, j["id"])
    assert record["state"] == "failed" and record["manifest"] is None
    assert "Scientific execution is unsupported" in record["logs"][-1]
    assert (
        client.get(f"/api/projects/{pid}/jobs/{j['id']}/download/package").status_code
        == 409
    )
    assert not client.get("/api/capabilities").json()["umep"]["available"]


def test_checksum_failure_and_queued_cancellation(client, project):
    pid = project["id"]
    a = uploaded(client, pid)
    j = client.post(f"/api/projects/{pid}/jobs", json={}).json()
    s.managed_path(a["storage_location"]).write_bytes(b"changed")
    claim(j["id"])
    assert run(pid, j["id"]) == 1
    assert "checksum changed" in s.job(pid, j["id"])["logs"][-1]
    j = client.post(f"/api/projects/{pid}/jobs", json={}).json()
    assert (
        client.post(f"/api/projects/{pid}/jobs/{j['id']}/cancel").json()["state"]
        == "cancelled"
    )


def test_boundary_coverage_and_summary(client, project):
    pid = project["id"]
    uploaded(client, pid)
    g = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    assert (
        client.put(
            f"/api/projects/{pid}/study-area", json={"reporting": g, "processing": g}
        ).status_code
        == 200
    )
    report = client.post(f"/api/projects/{pid}/validate", json={}).json()
    assert any(f["code"] == "coverage" for f in report["findings"])
    invalid = {"type": "Point", "coordinates": [1, 2]}
    assert (
        client.put(
            f"/api/projects/{pid}/study-area",
            json={"reporting": invalid, "processing": invalid},
        ).status_code
        == 422
    )


def test_worker_process_and_restart_recovery(client, project):
    pid = project["id"]
    uploaded(client, pid)
    interrupted = client.post(f"/api/projects/{pid}/jobs", json={}).json()
    claim(interrupted["id"])
    j = client.post(f"/api/projects/{pid}/jobs", json={}).json()
    worker = subprocess.Popen(
        [sys.executable, "-m", "backend.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        end = time.monotonic() + 20
        while time.monotonic() < end and s.job(pid, j["id"])["state"] not in (
            "succeeded",
            "failed",
        ):
            time.sleep(0.1)
        assert s.job(pid, j["id"])["state"] == "succeeded"
        assert s.job(pid, interrupted["id"])["state"] == "interrupted"
        cancelled = client.post(f"/api/projects/{pid}/jobs", json={}).json()
        while (
            time.monotonic() < end and s.job(pid, cancelled["id"])["state"] == "queued"
        ):
            time.sleep(0.02)
        assert s.job(pid, cancelled["id"])["state"] == "running"
        client.post(f"/api/projects/{pid}/jobs/{cancelled['id']}/cancel")
        while (
            time.monotonic() < end and s.job(pid, cancelled["id"])["state"] == "running"
        ):
            time.sleep(0.02)
        record = s.job(pid, cancelled["id"])
        assert record["state"] == "cancelled" and record["manifest"] is None
    finally:
        worker.terminate()
        worker.communicate(timeout=10)


def test_integer_raster_demo(client, project):
    with MemoryFile() as f:
        with f.open(
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="int16",
            crs="EPSG:32632",
            transform=from_origin(691000, 5330000, 2, 2),
            nodata=-9999,
        ) as dst:
            dst.write(np.ones((10, 10), dtype="int16"), 1)
        data = f.read()
    pid = project["id"]
    a = client.post(
        f"/api/projects/{pid}/assets", files={"file": ("integer.tif", data)}
    ).json()
    client.put(
        f"/api/projects/{pid}/assets/{a['id']}",
        json={"role": "surface_dsm", "units": "m", "height_reference": "absolute"},
    )
    j = client.post(f"/api/projects/{pid}/jobs", json={}).json()
    claim(j["id"])
    assert run(pid, j["id"]) == 0


def test_related_height_consistency(client, project):
    pid = project["id"]
    uploaded(client, pid)
    a = uploaded(client, pid)
    client.put(
        f"/api/projects/{pid}/assets/{a['id']}",
        json={"role": "terrain", "units": "m", "height_reference": "absolute"},
    )
    with rasterio.open(s.managed_path(a["storage_location"]), "r+") as dst:
        values = dst.read(1)
        values[1:] += 100
        dst.write(values, 1)
    report = client.post(f"/api/projects/{pid}/validate", json={}).json()
    assert any(f["code"] == "surface_below_terrain" for f in report["findings"])


def test_weather_upload_kind_and_limit(client, project, monkeypatch):
    pid = project["id"]
    data = b"timestamp,air_temperature_c,relative_humidity_pct,global_horizontal_w_m2\n2026-06-01T12:00:00Z,25,50,600\n"
    r = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("weather.csv", data)},
        data={"timezone": "UTC", "weather_kind": "hypothetical"},
    )
    assert (
        r.status_code == 201 and r.json()["metadata"]["weather_kind"] == "hypothetical"
    )
    monkeypatch.setenv("UMEP_UPLOAD_LIMIT_MB", "0")
    assert (
        client.post(
            f"/api/projects/{pid}/assets",
            files={"file": ("surface.tif", raster_bytes())},
        ).status_code
        == 422
    )
