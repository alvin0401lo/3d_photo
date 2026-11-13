"""Local metadata and immutable asset revisions. One host, one CPU worker."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DEPTHFRAME_STORAGE", ROOT / "storage")).resolve()
DEFAULT_SETTINGS = {"strength": 0.38, "motion": 0.45, "zoom": 1.0, "quality": "balanced", "autoOrbit": False}


@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "depthframe.sqlite3", timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL, settings TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, deleting INTEGER NOT NULL DEFAULT 0,
            source_ext TEXT NOT NULL, source_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL, updated REAL NOT NULL, cancel INTEGER NOT NULL DEFAULT 0,
            error TEXT, result TEXT, request_key TEXT, inference_size INTEGER NOT NULL DEFAULT 384,
            UNIQUE(project_id, request_key)
        );
        CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY CHECK (id=1), heartbeat REAL NOT NULL, state TEXT NOT NULL);
        """)
        # API and worker may start together. Serialize schema inspection and changes.
        db.execute("BEGIN IMMEDIATE")
        # Additive migrations preserve existing photographs and completed depth revisions.
        project_columns = {row["name"] for row in db.execute("PRAGMA table_info(projects)")}
        if "kind" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN kind TEXT NOT NULL DEFAULT 'photo'")
        if "subject" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN subject TEXT")
        job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "job_type" not in job_columns:
            db.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'depth'")
        if "parameters" not in job_columns:
            db.execute("ALTER TABLE jobs ADD COLUMN parameters TEXT NOT NULL DEFAULT '{}'")
        if "remote_id" not in job_columns:
            db.execute("ALTER TABLE jobs ADD COLUMN remote_id TEXT")
        db.execute("PRAGMA user_version=3")


def project_dir(project_id: str) -> Path:
    # Database-generated UUIDs only, including requests resolved through asset endpoints.
    if len(project_id) != 32 or any(c not in "0123456789abcdef" for c in project_id):
        raise ValueError("Invalid project identifier")
    return DATA / "projects" / project_id


def get_project(project_id: str):
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id=? AND deleting=0", (project_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["settings"] = json.loads(result["settings"])
        latest = db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC LIMIT 1", (project_id,)).fetchone()
        ready = db.execute("SELECT result FROM jobs WHERE project_id=? AND status='completed' AND job_type='depth' ORDER BY created DESC LIMIT 1", (project_id,)).fetchone()
        panorama = db.execute("SELECT result FROM jobs WHERE project_id=? AND status='completed' AND job_type='panorama' ORDER BY created DESC LIMIT 1", (project_id,)).fetchone()
        object_result = db.execute("SELECT result FROM jobs WHERE project_id=? AND status='completed' AND job_type='object' ORDER BY created DESC LIMIT 1", (project_id,)).fetchone()
        result["job"] = job_dict(latest) if latest else None
        result["depth"] = json.loads(ready["result"]) if ready else None
        result["assets"] = {kind: f"/api/projects/{project_id}/files/{kind}" for kind in ("original", "image", "thumbnail")}
        result["panorama"] = json.loads(panorama["result"]) if panorama else None
        result["object"] = json.loads(object_result["result"]) if object_result else None
        result["subject"] = json.loads(result["subject"]) if result["subject"] else None
        if result["kind"] == "panorama":
            result["panorama"] = {"job_id": None, "projection": "equirectangular", "width": result["width"], "height": result["height"], "ai_generated": False, "provider": "imported", "assets": {"panorama": result["assets"]["image"]}}
        result.pop("deleting", None)
        return result


def job_dict(row):
    if not row:
        return None
    result = dict(row)
    result["result"] = json.loads(result["result"]) if result["result"] else None
    result["parameters"] = json.loads(result.get("parameters", "{}"))
    return result


def get_job(job_id):
    with connection() as db:
        return job_dict(db.execute("SELECT j.* FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=? AND p.deleting=0", (job_id,)).fetchone())


def enqueue(project_id, request_key=None, inference_size=384, job_type="depth", parameters=None):
    if job_type not in {"depth", "panorama", "object"}:
        raise ValueError("Unsupported job type")
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT id FROM projects WHERE id=? AND deleting=0", (project_id,)).fetchone():
            raise LookupError("Project not found")
        if request_key:
            old = db.execute("SELECT * FROM jobs WHERE project_id=? AND request_key=?", (project_id, request_key)).fetchone()
            if old:
                if old["job_type"] != job_type:
                    raise ValueError("This request key already belongs to another job type.")
                return job_dict(old)
        active = db.execute("SELECT * FROM jobs WHERE project_id=? AND status IN ('queued','running')", (project_id,)).fetchone()
        if active:
            if active["job_type"] != job_type:
                raise ValueError("Wait for this project's current processing job to finish.")
            return job_dict(active)
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 5:
            raise OverflowError("The queue is full. Wait for a project to finish.")
        job_id = uuid.uuid4().hex
        now = time.time()
        stage = {"depth": "Waiting for CPU", "panorama": "Waiting for OpenAI", "object": "Waiting for Meshy"}[job_type]
        db.execute("INSERT INTO jobs (id,project_id,status,stage,created,updated,request_key,inference_size,job_type,parameters) VALUES (?,?,?,?,?,?,?,?,?,?)", (job_id, project_id, "queued", stage, now, now, request_key, inference_size, job_type, json.dumps(parameters or {})))
        return job_dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def claim():
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT j.* FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.status='queued' AND p.deleting=0 ORDER BY j.created LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE jobs SET status='running',stage='Preparing image',progress=5,updated=? WHERE id=?", (time.time(), row["id"]))
            return job_dict(row)
    return None


def update_job(job_id, **fields):
    allowed = {"status", "stage", "progress", "error", "result", "cancel", "remote_id"}
    if not fields.keys() <= allowed:
        raise ValueError("Invalid job fields")
    fields["updated"] = time.time()
    with connection() as db:
        db.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in fields)} WHERE id=?", (*fields.values(), job_id))


def cancel_requested(job_id):
    with connection() as db:
        row = db.execute("SELECT j.cancel,p.deleting FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=?", (job_id,)).fetchone()
        return not row or bool(row["cancel"] or row["deleting"])


def heartbeat(state):
    with connection() as db:
        db.execute("INSERT INTO worker VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,state=excluded.state", (time.time(), state))


def cleanup_deleted():
    with connection() as db:
        rows = db.execute("SELECT id FROM projects WHERE deleting=1 AND id NOT IN (SELECT project_id FROM jobs WHERE status='running')").fetchall()
        for row in rows:
            try:
                if project_dir(row["id"]).exists():
                    shutil.rmtree(project_dir(row["id"]))
            except OSError:
                # A Windows download or antivirus may still hold a file. Keep the tombstone and retry.
                continue
            db.execute("DELETE FROM projects WHERE id=?", (row["id"],))


def recover_stale(seconds=45):
    with connection() as db:
        db.execute("UPDATE jobs SET status=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'failed' END,stage='Worker interrupted',error='The worker stopped before this attempt finished. Retry to continue.',updated=? WHERE status='running' AND updated<?", (time.time(), time.time() - seconds))
