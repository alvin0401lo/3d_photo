"""Separate durable CPU worker with a persistent model process and hard job deadline."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import signal
import time
import traceback

from . import store


def inference_process(pipe):
    model = None
    while True:
        job = pipe.recv()
        if job is None:
            return
        try:
            if job.get("job_type") == "object":
                from .objects import run as generate_object
                result = generate_object(job, pipe.send)
            elif job.get("job_type") == "panorama":
                from .panorama import run as generate_panorama
                result = generate_panorama(job, pipe.send)
            else:
                if model is None:
                    pipe.send({"stage": "Loading CPU depth model", "progress": 10})
                    from .depth import DepthModel
                    model = DepthModel()
                result = model.run(job, pipe.send)
            pipe.send({"done": True, "result": result})
        except BaseException as exc:
            traceback.print_exc()
            pipe.send({"done": True, "error": str(exc)[:500] or type(exc).__name__})


def acquire_lock():
    store.DATA.mkdir(parents=True, exist_ok=True)
    handle = (store.DATA / "worker.lock").open("a+b")
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


def run():
    store.init()
    lock = acquire_lock()
    # The singleton lock proves no previous supervisor is still publishing.
    store.recover_stale(seconds=0)
    store.cleanup_deleted()
    stop = False

    def request_stop(*args):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    process = None
    pipe = None
    current = None
    deadline = int(os.environ.get("DEPTHFRAME_JOB_TIMEOUT", "300"))
    stop_file = store.DATA / "stop-worker"
    stop_file.unlink(missing_ok=True)
    print("DepthFrame CPU worker ready; one inference at a time.", flush=True)
    try:
        while not stop and not stop_file.exists():
            store.heartbeat("processing" if current else "ready")
            store.cleanup_deleted()
            if not current:
                current = store.claim()
                if not current:
                    time.sleep(1)
                    continue
                if not process or not process.is_alive():
                    pipe, child_pipe = mp.Pipe()
                    process = mp.Process(target=inference_process, args=(child_pipe,), daemon=True)
                    process.start()
                pipe.send(current)
                start = time.monotonic()
                active_deadline = current.get("parameters", {}).get("deadline_seconds", 330) if current.get("job_type") in {"panorama", "object"} else deadline
            store.update_job(current["id"])
            output_group = current.get("job_type", "depth")
            if time.monotonic() - start > active_deadline or not process.is_alive():
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                cancelled = store.cancel_requested(current["id"])
                store.update_job(current["id"], status="cancelled" if cancelled else "failed", stage="Cancelled" if cancelled else "Processing interrupted", error=None if cancelled else ("Remote processing stopped or exceeded its deadline. Check your provider account before starting another task; a saved Meshy task can be resumed." if output_group in {"panorama", "object"} else "CPU inference exceeded its deadline or stopped unexpectedly. Retry with a smaller inference size."))
                process = None
                shutil.rmtree(store.project_dir(current["project_id"]) / output_group / (current["id"] + ".tmp"), ignore_errors=True)
                current = None
                continue
            if pipe.poll(0.5):
                try:
                    message = pipe.recv()
                except (EOFError, OSError):
                    store.update_job(current["id"], status="failed", stage="Processing interrupted", error="The inference process disconnected. Retry this project.")
                    process.join(timeout=2)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                    process = None
                    current = None
                    continue
                if not message.get("done"):
                    store.update_job(current["id"], **message)
                    continue
                if store.cancel_requested(current["id"]):
                    store.update_job(current["id"], status="cancelled", stage="Cancelled")
                    shutil.rmtree(store.project_dir(current["project_id"]) / output_group / current["id"], ignore_errors=True)
                elif message.get("error"):
                    store.update_job(current["id"], status="failed", stage="Processing failed", error=message["error"])
                    shutil.rmtree(store.project_dir(current["project_id"]) / output_group / (current["id"] + ".tmp"), ignore_errors=True)
                else:
                    # Recheck deletion/cancellation inside the publication transaction.
                    with store.connection() as db:
                        db.execute("BEGIN IMMEDIATE")
                        row = db.execute("SELECT p.deleting,j.cancel FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=?", (current["id"],)).fetchone()
                        if row and not row["deleting"] and not row["cancel"]:
                            db.execute("UPDATE jobs SET status='completed',stage='Ready',progress=100,result=?,updated=? WHERE id=?", (json.dumps(message["result"]), time.time(), current["id"]))
                        elif row:
                            db.execute("UPDATE jobs SET status='cancelled',stage='Cancelled',updated=? WHERE id=?", (time.time(), current["id"]))
                print(f"Finished attempt {current['id']}", flush=True)
                current = None
    finally:
        if process and process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if current:
            store.update_job(current["id"], status="failed", stage="Worker stopped", error="The worker was shut down. Retry to continue.")
        store.heartbeat("offline")
        stop_file.unlink(missing_ok=True)
        lock.close()


if __name__ == "__main__":
    mp.freeze_support()
    run()
