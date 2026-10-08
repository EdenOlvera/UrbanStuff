import json, os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import numpy as np
import rasterio
from rasterio.warp import transform
from rasterio.features import geometry_mask
from shapely.geometry import shape
from shapely.ops import transform as shape_transform
from pyproj import Transformer
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from . import storage as s
from .models import Project, StudyArea, Asset, AssetDeclaration, SimulationConfiguration
from .geo import (
    inspect_raster,
    checksum,
    grid_from,
    validate_geometry,
    weather,
    validate,
    preview,
    LABEL,
)
from .adapters import DemoAdapter, QgisUmepAdapter, LidarProcessor


@asynccontextmanager
async def lifespan(app):
    s.migrate()
    yield


app = FastAPI(title="UMEP Studio", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "UMEP_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(","),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(KeyError)
async def not_found(request, exc):
    return Response(
        json.dumps({"detail": str(exc)}), status_code=404, media_type="application/json"
    )


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return Response(
        json.dumps({"detail": str(exc)}), status_code=422, media_type="application/json"
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/capabilities")
def capabilities():
    return {
        "demo": DemoAdapter().capabilities(),
        "umep": QgisUmepAdapter().capabilities(),
        "lidar": LidarProcessor().capabilities(),
        "urock": {"available": False},
        "spatialtc": {"available": False},
    }


@app.get("/api/projects")
def projects():
    return s.rows("SELECT id,name,created_at FROM projects ORDER BY created_at DESC")


@app.post("/api/projects", status_code=201)
def create_project(value: Project):
    pid = s.identifier()
    study = None
    if value.study_area:
        study = checked_study(value.study_area)
    s.execute(
        "INSERT INTO projects VALUES(?,?,?,?,?)",
        (
            pid,
            value.name,
            s.now(),
            json.dumps(study) if study else None,
            value.grid.model_dump_json() if value.grid else None,
        ),
    )
    return s.project(pid)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return {
        **s.project(pid),
        "assets": s.assets(pid),
        "jobs": [
            s.job(pid, r["id"])
            for r in s.rows(
                "SELECT id FROM jobs WHERE project_id=? ORDER BY created_at DESC",
                (pid,),
            )
        ],
    }


def checked_study(value):
    reporting = validate_geometry(value.reporting)
    processing = validate_geometry(value.processing)
    if not shape(processing).covers(shape(reporting)):
        raise ValueError("Processing boundary must include the reporting boundary")
    return {"reporting": reporting, "processing": processing}


@app.put("/api/projects/{pid}/study-area")
def study(pid: str, value: StudyArea):
    s.project(pid)
    area = checked_study(value)
    s.execute("UPDATE projects SET study_area=? WHERE id=?", (json.dumps(area), pid))
    return area


@app.post("/api/projects/{pid}/assets", status_code=201)
async def upload(
    pid: str,
    file: UploadFile = File(...),
    timezone: str = Form("UTC"),
    weather_kind: Literal["observed", "typical-year", "hypothetical"] = Form(
        "observed"
    ),
):
    s.project(pid)
    name = file.filename or "upload"
    if "/" in name or "\\" in name or name in (".", "..") or len(name) > 200:
        raise ValueError("Use a plain filename without directory components")
    extension = Path(name).suffix.lower()
    if extension not in (".tif", ".tiff", ".csv", ".las", ".laz"):
        raise ValueError(
            "Supported uploads: GeoTIFF, documented weather CSV, LAS/LAZ registration"
        )
    aid = s.identifier()
    directory = s.ROOT / "assets" / pid / aid
    directory.mkdir(parents=True)
    path = directory / name
    size = 0
    maximum = int(os.environ.get("UMEP_UPLOAD_LIMIT_MB", "100")) * 1024 * 1024
    try:
        with path.open("wb") as f:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > maximum:
                    raise ValueError(
                        f"Upload exceeds {maximum // 1024 // 1024} MB limit"
                    )
                f.write(data)
        if extension in (".tif", ".tiff"):
            metadata = inspect_raster(path)
        elif extension == ".csv":
            metadata = weather(path, timezone)
            metadata["weather_kind"] = weather_kind
        else:
            metadata = {
                "kind": "lidar",
                "supported": False,
                "reason": LidarProcessor().capabilities()["reason"],
            }
        role = "weather" if extension == ".csv" else "unassigned"
        value = Asset(
            id=aid,
            project_id=pid,
            filename=name,
            storage_location=str(path.relative_to(s.ROOT)),
            role=role,
            nature=(
                "synthetic"
                if weather_kind == "hypothetical"
                else "estimated"
                if weather_kind == "typical-year"
                else "observed"
            )
            if extension == ".csv"
            else "observed",
            checksum=checksum(path),
            metadata=metadata,
            history=[
                {
                    "stage": "ingest",
                    "version": "1",
                    "timestamp": s.now(),
                    "operation": "Inspected without modifying source",
                }
            ],
        ).model_dump()
        s.execute("INSERT INTO assets VALUES(?,?,?)", (aid, pid, json.dumps(value)))
    except Exception as e:
        path.unlink(missing_ok=True)
        if isinstance(e, (ValueError, HTTPException)):
            raise
        raise ValueError(f"Cannot inspect uploaded file: {e}") from e
    finally:
        await file.close()
    return value


@app.put("/api/projects/{pid}/assets/{aid}")
def declare(pid: str, aid: str, value: AssetDeclaration):
    asset = s.asset(pid, aid)
    if asset["metadata"]["kind"] == "weather" and value.role != "weather":
        raise ValueError("Weather CSV must keep its weather role")
    asset.update(value.model_dump())
    asset["history"].append(
        {
            "stage": "declaration",
            "version": "1",
            "timestamp": s.now(),
            "declaration": value.model_dump(),
        }
    )
    s.execute(
        "UPDATE assets SET data=? WHERE id=? AND project_id=?",
        (json.dumps(asset), aid, pid),
    )
    p = s.project(pid)
    if (
        value.role in ("surface_dsm", "building_dsm")
        and asset["metadata"].get("crs")
        and not p["grid"]
    ):
        s.execute(
            "UPDATE projects SET grid=? WHERE id=?",
            (json.dumps(grid_from(asset["metadata"])), pid),
        )
    return asset


@app.post("/api/projects/{pid}/validate")
def validation(pid: str, config: SimulationConfiguration):
    return validate(s.project(pid), s.assets(pid), config.model_dump())


@app.post("/api/projects/{pid}/jobs", status_code=201)
def submit(pid: str, config: SimulationConfiguration):
    p = s.project(pid)
    assets = s.assets(pid)
    # Immutable snapshot; scenario overrides are limited to an explicitly selected project asset per role.
    for role, aid in config.input_overrides.items():
        replacement = s.asset(pid, aid)
        if replacement["role"] != role:
            raise ValueError("Scenario override role does not match the selected asset")
        assets = [a for a in assets if a["role"] != role] + [replacement]
    # Unsupported scientific requests become honest failed jobs with useful logs, never demo output.
    if config.engine == "demo":
        report = validate(p, assets, config.model_dump())
        if not report["valid"]:
            raise HTTPException(422, detail=report)
    jid = s.identifier()
    s.execute(
        "INSERT INTO jobs(id,project_id,state,config,snapshot,created_at) VALUES(?,?,?,?,?,?)",
        (
            jid,
            pid,
            "queued",
            config.model_dump_json(),
            json.dumps({"project": p, "assets": assets}),
            s.now(),
        ),
    )
    return s.job(pid, jid)


@app.get("/api/projects/{pid}/jobs/{jid}")
def get_job(pid: str, jid: str):
    return s.job(pid, jid)


@app.post("/api/projects/{pid}/jobs/{jid}/cancel")
def cancel(pid: str, jid: str):
    job = s.job(pid, jid)
    if job["state"] not in ("queued", "running"):
        raise HTTPException(409, detail="Only queued or running jobs can be cancelled")
    with s.connect() as db:
        db.execute(
            "UPDATE jobs SET cancel_requested=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,finished_at=CASE WHEN state='queued' THEN ? ELSE finished_at END WHERE id=? AND state IN ('queued','running')",
            (s.now(), jid),
        )
    return s.job(pid, jid)


@app.get("/api/projects/{pid}/jobs/{jid}/process-log")
def process_log(pid: str, jid: str):
    s.job(pid, jid)
    path = s.ROOT / "runs" / jid / "process.log"
    return {"log": path.read_text(errors="replace")[-50000:] if path.exists() else ""}


def output_path(pid, jid, oid):
    job = s.job(pid, jid)
    if job["state"] != "succeeded" or not job["manifest"]:
        raise HTTPException(409, detail="Successful outputs are not available")
    output = next((o for o in job["manifest"]["outputs"] if o["id"] == oid), None)
    if not output:
        raise KeyError("Output not found")
    return s.ROOT / "runs" / jid / output["filename"], output


@app.get("/api/projects/{pid}/assets/{aid}/preview.png")
def asset_preview(pid: str, aid: str):
    a = s.asset(pid, aid)
    if a["metadata"]["kind"] != "raster":
        raise ValueError("Only raster assets have previews")
    return Response(
        preview(s.managed_path(a["storage_location"])), media_type="image/png"
    )


@app.get("/api/projects/{pid}/jobs/{jid}/outputs/{oid}/preview.png")
def output_preview(pid: str, jid: str, oid: str):
    path, out = output_path(pid, jid, oid)
    return Response(preview(path), media_type="image/png")


@app.get("/api/projects/{pid}/jobs/{jid}/outputs/{oid}/download")
def output_download(pid: str, jid: str, oid: str):
    path, out = output_path(pid, jid, oid)
    return FileResponse(path, filename=out["filename"], media_type="image/tiff")


@app.get("/api/projects/{pid}/jobs/{jid}/download/{kind}")
def download_run(pid: str, jid: str, kind: Literal["manifest", "package"]):
    job = s.job(pid, jid)
    if job["state"] != "succeeded":
        raise HTTPException(409, detail="Only completed runs are downloadable")
    filename = "manifest.json" if kind == "manifest" else "run-package.zip"
    return FileResponse(s.ROOT / "runs" / jid / filename, filename=filename)


def sample(path, lon, lat):
    with rasterio.open(path) as src:
        if not src.crs:
            raise ValueError("Cannot locate pixels without CRS")
        x, y = transform("EPSG:4326", src.crs, [lon], [lat])
        row, col = src.index(x[0], y[0])
        if row < 0 or col < 0 or row >= src.height or col >= src.width:
            return {"value": None, "reason": "outside raster"}
        val = src.read(1, window=((row, row + 1), (col, col + 1)), masked=True)
        return {
            "value": float(val[0, 0])
            if val.count() and np.isfinite(val[0, 0])
            else None,
            "row": row,
            "column": col,
        }


@app.get("/api/projects/{pid}/assets/{aid}/pixel")
def asset_pixel(pid: str, aid: str, lon: float, lat: float):
    a = s.asset(pid, aid)
    return sample(s.managed_path(a["storage_location"]), lon, lat)


@app.get("/api/projects/{pid}/jobs/{jid}/outputs/{oid}/pixel")
def output_pixel(pid: str, jid: str, oid: str, lon: float, lat: float):
    path, out = output_path(pid, jid, oid)
    return {
        **sample(path, lon, lat),
        "units": out["units"],
        "label": LABEL if out["synthetic"] else "",
    }


@app.get("/api/projects/{pid}/jobs/{jid}/outputs/{oid}/summary")
def summary(pid: str, jid: str, oid: str):
    path, out = output_path(pid, jid, oid)
    p = s.job(pid, jid)["snapshot"]["project"]
    with rasterio.open(path) as src:
        values = src.read(1, masked=True)
        if p.get("study_area"):
            geom = shape_transform(
                Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform,
                shape(p["study_area"]["reporting"]),
            )
            mask = geometry_mask(
                [geom.__geo_interface__],
                out_shape=values.shape,
                transform=src.transform,
                invert=True,
            )
            values = np.ma.array(values, mask=np.ma.getmaskarray(values) | ~mask)
        data = values.compressed()
        data = data[np.isfinite(data)]
        return {
            "count": len(data),
            "minimum": float(data.min()) if len(data) else None,
            "maximum": float(data.max()) if len(data) else None,
            "mean": float(data.mean()) if len(data) else None,
            "units": out["units"],
            "scope": "reporting boundary" if p.get("study_area") else "raster extent",
            "label": LABEL,
        }


@app.post("/api/projects/{pid}/demo-fixture", status_code=201)
def demo_fixture(pid: str):
    s.project(pid)
    from .fixtures import create_fixture

    aid = s.identifier()
    directory = s.ROOT / "assets" / pid / aid
    directory.mkdir(parents=True)
    path = directory / "demo-surface.tif"
    create_fixture(path)
    m = inspect_raster(path)
    asset = Asset(
        id=aid,
        project_id=pid,
        filename=path.name,
        storage_location=str(path.relative_to(s.ROOT)),
        role="surface_dsm",
        units="m",
        height_reference="absolute",
        vertical_reference="synthetic local datum",
        source=LABEL,
        nature="synthetic",
        checksum=checksum(path),
        metadata=m,
        history=[
            {"stage": "fixture", "version": "1", "timestamp": s.now(), "label": LABEL}
        ],
    ).model_dump()
    s.execute("INSERT INTO assets VALUES(?,?,?)", (aid, pid, json.dumps(asset)))
    s.execute(
        "UPDATE projects SET grid=COALESCE(grid,?) WHERE id=?",
        (json.dumps(grid_from(m)), pid),
    )
    return asset
