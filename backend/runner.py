"""One isolated subprocess per job; called only by the separate worker."""

import sys, json, traceback, zipfile
from .storage import job, managed_path, now, ROOT, connect
from .adapters import DemoAdapter, QgisUmepAdapter, versions
from .geo import LABEL
from .models import RunManifest


def progress(jid, percent, message):
    with connect() as db:
        r = db.execute(
            "SELECT logs,cancel_requested FROM jobs WHERE id=?", (jid,)
        ).fetchone()
        if r["cancel_requested"]:
            raise RuntimeError("Cancellation requested")
        logs = json.loads(r["logs"])
        logs.append(f"{now()}  {message}")
        db.execute(
            "UPDATE jobs SET progress=?,logs=? WHERE id=?",
            (percent, json.dumps(logs), jid),
        )


def run(pid, jid):
    record = job(pid, jid)
    snapshot = record["snapshot"]
    config = record["config"]
    work = ROOT / "runs" / jid
    work.mkdir(parents=True, exist_ok=True)
    try:
        adapter = DemoAdapter() if config["engine"] == "demo" else QgisUmepAdapter()
        errors = adapter.validate_inputs(snapshot)
        if errors:
            raise RuntimeError("; ".join(errors))
        progress(jid, 15, "Checking immutable input snapshot and checksums")
        from .geo import checksum, validate, grid_from

        for asset in snapshot["assets"]:
            if checksum(managed_path(asset["storage_location"])) != asset["checksum"]:
                raise RuntimeError("Input checksum changed since submission")
        report = validate(snapshot["project"], snapshot["assets"], config)
        if not report["valid"]:
            raise RuntimeError(
                "; ".join(
                    x["message"] for x in report["findings"] if x["severity"] == "error"
                )
            )
        progress(jid, 30, "Preparing geometry cache")
        prepared = adapter.prepare(snapshot, work)
        progress(
            jid,
            55,
            f"Geometry cache {'hit' if prepared['cache_hit'] else 'created'}; executing explicit synthetic demo",
        )
        outputs = adapter.collect_outputs(adapter.run(prepared, config, work))
        progress(jid, 85, "Packaging georeferenced outputs and provenance")
        surface = next(
            a
            for a in snapshot["assets"]
            if a["role"] in ("surface_dsm", "building_dsm")
        )
        manifest = RunManifest(
            job_id=jid,
            project_id=pid,
            synthetic=True,
            label=LABEL,
            inputs=[
                {
                    k: a.get(k)
                    for k in (
                        "id",
                        "filename",
                        "checksum",
                        "role",
                        "source",
                        "units",
                        "height_reference",
                        "vertical_reference",
                        "nature",
                        "history",
                    )
                }
                for a in snapshot["assets"]
            ],
            configuration=config,
            study_area=snapshot["project"].get("study_area"),
            grid=snapshot["project"].get("grid") or grid_from(surface["metadata"]),
            versions=versions(),
            stage_versions={
                "geometry": "1",
                "demo": "1",
                "geometry_cache_key": prepared["cache_key"],
                "geometry_cache_hit": str(prepared["cache_hit"]),
            },
            started_at=record["started_at"],
            finished_at=now(),
            warnings=[
                f["message"] for f in report["findings"] if f["severity"] == "warning"
            ],
            assumptions=[
                "Synthetic illustrative shade and temperature patterns; no scientific validity.",
                "Demo air temperature parameter is hypothetical; uploaded weather is recorded but not used by the demo.",
                "Input grid preserved. No automatic resampling or repairs.",
            ],
            outputs=outputs,
        ).model_dump()
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        # Include source files so a package remains reproducible independently of server storage.
        with zipfile.ZipFile(work / "run-package.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in ["manifest.json"] + [o["filename"] for o in outputs]:
                z.write(work / f, f)
            for a in snapshot["assets"]:
                z.write(
                    managed_path(a["storage_location"]),
                    f"inputs/{a['id']}/{a['filename']}",
                )
        progress(jid, 100, "Completed — " + LABEL)
        with connect() as db:
            db.execute(
                "UPDATE jobs SET state=CASE WHEN cancel_requested=1 THEN 'cancelled' ELSE 'succeeded' END,manifest=CASE WHEN cancel_requested=1 THEN NULL ELSE ? END,finished_at=? WHERE id=? AND state='running'",
                (json.dumps(manifest), now(), jid),
            )
    except Exception as e:
        with connect() as db:
            r = db.execute(
                "SELECT logs,cancel_requested FROM jobs WHERE id=?", (jid,)
            ).fetchone()
            logs = json.loads(r["logs"])
            logs.append(f"{now()} ERROR: {type(e).__name__}: {e}")
            db.execute(
                'UPDATE jobs SET state=?,logs=?,finished_at=?,manifest=NULL WHERE id=? AND state="running"',
                (
                    "cancelled" if r["cancel_requested"] else "failed",
                    json.dumps(logs),
                    now(),
                    jid,
                ),
            )
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    # Linux parent-death signal prevents orphan processing after a worker crash.
    import ctypes, signal, os

    parent = os.getppid()
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    if len(sys.argv) > 3 and (parent != int(sys.argv[3]) or os.getppid() != parent):
        sys.exit(1)
    sys.exit(run(sys.argv[1], sys.argv[2]))
