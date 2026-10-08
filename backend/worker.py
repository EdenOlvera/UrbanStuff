import os, sys, time, signal, subprocess, json
from .storage import connect, migrate, now, ROOT

STOP = False
CHILD = None


def stop(*_):
    global STOP
    STOP = True
    if CHILD and CHILD.poll() is None:
        os.killpg(CHILD.pid, signal.SIGTERM)


def serve():
    global CHILD
    import fcntl

    lock = (ROOT / "worker.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("A worker already owns this data directory")
    migrate()
    with connect() as db:
        for r in db.execute(
            "SELECT id,logs FROM jobs WHERE state='running'"
        ).fetchall():
            logs = json.loads(r["logs"]) + [
                f"{now()} Worker restarted; previous process interrupted. Resubmit explicitly."
            ]
            db.execute(
                "UPDATE jobs SET state='interrupted',finished_at=?,logs=? WHERE id=?",
                (now(), json.dumps(logs), r["id"]),
            )
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("UMEP worker ready", flush=True)
    while not STOP:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE jobs SET state='running',started_at=? WHERE id=?",
                    (now(), row["id"]),
                )
        if not row:
            time.sleep(0.4)
            continue
        work = ROOT / "runs" / row["id"]
        work.mkdir(parents=True, exist_ok=True)
        with (work / "process.log").open("ab") as log:
            CHILD = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "backend.runner",
                    row["project_id"],
                    row["id"],
                    str(os.getpid()),
                ],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            while CHILD.poll() is None:
                with connect() as db:
                    cancelled = db.execute(
                        "SELECT cancel_requested FROM jobs WHERE id=?", (row["id"],)
                    ).fetchone()[0]
                if cancelled or STOP:
                    os.killpg(CHILD.pid, signal.SIGTERM)
                    try:
                        CHILD.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(CHILD.pid, signal.SIGKILL)
                        CHILD.wait()
                    break
                time.sleep(0.2)
        with connect() as db:
            r = db.execute(
                "SELECT state,logs,cancel_requested FROM jobs WHERE id=?", (row["id"],)
            ).fetchone()
            if r["state"] == "running":
                state = (
                    "cancelled"
                    if r["cancel_requested"]
                    else "interrupted"
                    if STOP
                    else "failed"
                )
                logs = json.loads(r["logs"]) + [
                    f"{now()} Processing exited ({CHILD.returncode}); state={state}. See process log."
                ]
                db.execute(
                    "UPDATE jobs SET state=?,logs=?,finished_at=?,manifest=NULL WHERE id=?",
                    (state, json.dumps(logs), now(), row["id"]),
                )
        CHILD = None


if __name__ == "__main__":
    serve()
