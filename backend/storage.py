import os, sqlite3, json, uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(os.environ.get("UMEP_DATA_DIR", ".data")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return uuid.uuid4().hex


def connect():
    db = sqlite3.connect(ROOT / "studio.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def migrate():
    with connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY)"
        )
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if not db.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (path.name,)
            ).fetchone():
                db.executescript(path.read_text())
                db.execute("INSERT INTO schema_migrations VALUES(?)", (path.name,))


def rows(sql, args=()):
    with connect() as db:
        return [dict(x) for x in db.execute(sql, args).fetchall()]


def execute(sql, args=()):
    with connect() as db:
        db.execute(sql, args)


def project(pid):
    result = rows("SELECT * FROM projects WHERE id=?", (pid,))
    if not result:
        raise KeyError("Project not found")
    value = result[0]
    for key in ("study_area", "grid"):
        value[key] = json.loads(value[key]) if value[key] else None
    return value


def assets(pid):
    return [
        json.loads(x["data"])
        for x in rows("SELECT data FROM assets WHERE project_id=?", (pid,))
    ]


def asset(pid, aid):
    result = rows("SELECT data FROM assets WHERE project_id=? AND id=?", (pid, aid))
    if not result:
        raise KeyError("Asset not found in project")
    return json.loads(result[0]["data"])


def job(pid, jid):
    result = rows("SELECT * FROM jobs WHERE project_id=? AND id=?", (pid, jid))
    if not result:
        raise KeyError("Job not found in project")
    value = result[0]
    for key in ("config", "snapshot", "logs", "manifest"):
        value[key] = json.loads(value[key]) if value[key] else None
    return value


def managed_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Invalid storage path")
    return path
