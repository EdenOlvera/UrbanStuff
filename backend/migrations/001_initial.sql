CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, study_area TEXT, grid TEXT);
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), state TEXT NOT NULL, config TEXT NOT NULL, snapshot TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, logs TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0, manifest TEXT);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(state, created_at);
