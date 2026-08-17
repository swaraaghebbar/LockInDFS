"""
Storage Node – one instance per partition.

Each node is an independent FastAPI process that stores content-addressed blobs
on its own partition.  It knows nothing about other nodes.

## Content-addressing & checksums
Every blob is named by its SHA-256 hash.  This gives us three guarantees:
  1. Deduplication – identical data always produces the same hash, so we
     never store the same chunk twice on one node.
  2. Write verification – when a blob arrives via PUT, we recompute its
     SHA-256 and reject it if the hash doesn't match the URL.  This catches
     network corruption during upload.
  3. Read verification – when a blob is served via GET, we recompute the
     hash before sending.  This catches silent disk corruption (bit-rot).

Endpoints:
  PUT    /blob/{hash}    Store a chunk  (verifies hash on write)
  GET    /blob/{hash}    Retrieve chunk (verifies hash on read)
  DELETE /blob/{hash}    Delete a chunk
  GET    /health         Node health check
"""

import hashlib
import os
import sys
import time
import argparse
import asyncio
import httpx

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response

# Ensure project root is importable so `config` and `mount_manager` resolve
# whether the node is started via launch.py, uvicorn, or `python -m`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as app_config
import mount_manager

app = FastAPI(title="DFS Storage Node", version="0.1.0")

# ── Runtime state (set via CLI args at startup) ──────────────────────────────

NODE_ID: str = "unknown"
STORAGE_PATH: str = "./data"
COORDINATOR_URL: str = "http://127.0.0.1:8000"

# Tracks the most recent auto-repair attempt so we can (a) enforce a cooldown
# between attempts and (b) surface the outcome on /health for the dashboard.
_LAST_REPAIR: dict = {"ts": 0.0, "result": None}
_REPAIR_LOCK = asyncio.Lock()


def _node_cfg() -> dict:
    """
    Build the effective config for THIS node.

    Starts from the static metadata in config.NODES (removable, fs_type,
    fs_label, fs_uuid, device) and overlays the *actual* storage path this
    process was launched with, so mount detection always checks the real path.
    """
    cfg = dict(app_config.NODES.get(NODE_ID, {}))
    cfg["storage_path"] = STORAGE_PATH
    return cfg


def _check_mount():
    """
    Ensure the physical drive is mounted before allowing blob operations.

    Delegates to mount_manager.classify(), which returns one of:
      * "ok"        – mounted & usable                       -> allow
      * "unmounted" – device PRESENT but not mounted (repair)-> 503
      * "absent"    – device NOT present (unplugged)         -> 503

    Both failure states raise 503, but the detail spells out which one it is so
    the coordinator and dashboard can tell "needs repair" apart from "not even
    plugged in".  The node's watchdog handles the actual repair for "unmounted".
    """
    state = mount_manager.classify(_node_cfg())
    if state == mount_manager.MOUNTED:
        return
    if state == mount_manager.UNMOUNTED:
        raise HTTPException(
            status_code=503,
            detail=(f"Drive present but UNMOUNTED for {NODE_ID}: {STORAGE_PATH} "
                    f"(auto-repair will attempt ntfsfix + remount)"),
        )
    # ABSENT
    raise HTTPException(
        status_code=503,
        detail=(f"Drive ABSENT (not plugged in) for {NODE_ID}: {STORAGE_PATH} "
                f"— nothing to repair"),
    )


def _blob_path(blob_hash: str) -> str:
    """
    Return the filesystem path where a blob is stored.

    We use a flat directory layout:  <STORAGE_PATH>/<sha256_hex>
    A future optimisation could use fan-out directories (e.g. ab/cd/abcdef…)
    to avoid huge directory listings, but flat is fine for learning.
    """
    return os.path.join(STORAGE_PATH, blob_hash)


# ── Blob operations ─────────────────────────────────────────────────────────

@app.put("/blob/{blob_hash}")
async def put_blob(blob_hash: str, request: Request):
    _check_mount()
    """
    Store a blob whose SHA-256 must equal *blob_hash*.

    ## Write-verification flow
    1. Read the entire body into memory.
    2. Compute SHA-256 of the received bytes.
    3. Compare against the hash in the URL.
       - Match   → write to disk, return 201.
       - Mismatch → return 409 Conflict (data was corrupted in transit).

    This is the FIRST verification checkpoint in the end-to-end chain:
      client computes hash → coordinator forwards → NODE VERIFIES HERE.
    """
    # Check if a simulated full disk is active
    flag_path = os.path.join(STORAGE_PATH, ".disk_full")
    if os.path.exists(flag_path):
        raise HTTPException(
            status_code=507,
            detail=f"Insufficient storage on {NODE_ID}: simulated disk full."
        )

    body = await request.body()

    # Compute the SHA-256 of the received bytes.
    # hashlib.sha256() produces a 256-bit (32-byte) digest; .hexdigest()
    # gives us the standard 64-character lowercase hex string.
    computed_hash = hashlib.sha256(body).hexdigest()

    # ── Integrity check: does what we received match the claimed hash? ───
    if computed_hash != blob_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Hash mismatch on write: URL says {blob_hash}, "
                f"but received data hashes to {computed_hash}.  "
                "The data was likely corrupted in transit."
            ),
        )

    # ── Persist to disk ──────────────────────────────────────────────────
    # Graceful degradation: if this node's disk is full (ENOSPC, errno 28),
    # we return HTTP 507 Insufficient Storage instead of crashing with a 500.
    # The coordinator treats 507 as a signal to skip this node and try another,
    # keeping the upload alive even when a drive is at capacity.
    path = _blob_path(blob_hash)
    try:
        with open(path, "wb") as f:
            f.write(body)
    except OSError as e:
        import errno
        if e.errno == errno.ENOSPC:
            raise HTTPException(
                status_code=507,
                detail=f"Insufficient storage on {NODE_ID}: disk is full."
            )
        raise  # Re-raise unexpected OS errors

    return {
        "status": "stored",
        "hash": blob_hash,
        "size": len(body),
        "node_id": NODE_ID,
    }


@app.get("/blob/{blob_hash}")
async def get_blob(blob_hash: str):
    _check_mount()
    """
    Retrieve a blob and verify its integrity before serving.

    ## Read-verification flow
    1. Read the blob from disk.
    2. Recompute SHA-256 of the bytes on disk.
    3. Compare against the expected hash (from the URL).
       - Match   → serve the bytes with 200.
       - Mismatch → return 500 (disk corruption / bit-rot detected).

    This is the SECOND verification checkpoint:
      NODE VERIFIES ON READ → coordinator receives → coordinator verifies again.

    Why verify on read?
    Disks can silently corrupt data ("bit-rot").  USB sticks and SD cards
    are especially prone to this.  By hashing before serving, we catch
    corruption at the source instead of delivering bad data.
    """
    path = _blob_path(blob_hash)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Blob {blob_hash} not found")

    with open(path, "rb") as f:
        data = f.read()

    # ── Integrity check: does what's on disk still match the hash? ───────
    computed_hash = hashlib.sha256(data).hexdigest()

    if computed_hash != blob_hash:
        # This means the data on disk has been corrupted since it was
        # written (bit-rot, bad sector, etc.).  We raise a 500 because
        # it's the node's fault, not the client's.
        raise HTTPException(
            status_code=500,
            detail=(
                f"CORRUPTION DETECTED on read: expected {blob_hash}, "
                f"but data on disk hashes to {computed_hash}.  "
                "The blob may have suffered bit-rot."
            ),
        )

    # Return raw bytes with application/octet-stream so the coordinator
    # can reassemble the file exactly.
    return Response(content=data, media_type="application/octet-stream")


@app.delete("/blob/{blob_hash}")
async def delete_blob(blob_hash: str):
    _check_mount()
    """Delete a blob from this node's storage."""
    path = _blob_path(blob_hash)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Blob {blob_hash} not found")

    os.remove(path)
    return {"status": "deleted", "hash": blob_hash, "node_id": NODE_ID}


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    Return node identity, storage path, and per-node disk stats.

    Reports both:
      - total_bytes / blob_count: how much data THIS node stores (blobs only)
      - disk_total / free_space: real capacity of the PARTITION hosting this
        node's storage path (via shutil.disk_usage on the resolved path)

    When all nodes share the same partition (dev mode), disk_total and
    free_space will be identical — but total_bytes will differ per node.
    On the Pi with real mount points, each drive reports its own capacity.
    """
    # Classify the drive first — the status we report distinguishes a drive
    # that merely needs remounting ("unmounted", repairable) from one that is
    # simply not plugged in ("absent").  This is the distinction the whole
    # auto-repair feature hinges on.
    cfg = _node_cfg()
    snapshot = mount_manager.describe(cfg)

    if snapshot["state"] != mount_manager.MOUNTED:
        payload = {
            "node_id": NODE_ID,
            "status": snapshot["state"],   # "unmounted" or "absent"
            "storage_path": STORAGE_PATH,
            "blob_count": 0,
            "total_bytes": 0,
            "free_space": 0,
            "disk_total": 0,
            # Availability vs. failure — never repair what isn't connected.
            "present": snapshot["present"],
            "repairable": snapshot["repairable"],
            "removable": snapshot["removable"],
            "device": snapshot["device"],
        }
        if _LAST_REPAIR["result"] is not None:
            payload["last_repair"] = mount_manager.summarize_repair(_LAST_REPAIR["result"])
        return payload

    import shutil

    blob_count = 0
    total_bytes = 0

    if os.path.isdir(STORAGE_PATH):
        for entry in os.scandir(STORAGE_PATH):
            if entry.is_file() and not entry.name.startswith("."):
                blob_count += 1
                total_bytes += entry.stat().st_size

    usage = shutil.disk_usage(STORAGE_PATH)
    free_space = usage.free
    disk_total = usage.total

    # Handle simulated full disk flag
    flag_path = os.path.join(STORAGE_PATH, ".disk_full")
    if os.path.exists(flag_path):
        free_space = 0

    payload = {
        "node_id": NODE_ID,
        "status": "ok",
        "storage_path": STORAGE_PATH,
        "blob_count": blob_count,
        "total_bytes": total_bytes,   # bytes THIS node stores (blob data)
        "free_space": free_space,     # bytes free on the underlying partition
        "disk_total": disk_total,     # total capacity of the partition
        "present": True,
        "repairable": False,
        "removable": snapshot["removable"],
        "device": snapshot["device"],
    }
    if _LAST_REPAIR["result"] is not None:
        payload["last_repair"] = mount_manager.summarize_repair(_LAST_REPAIR["result"])
    return payload


# ── Background Scrubber ──────────────────────────────────────────────────────

async def scrubber_loop():
    """
    Periodically scan all local blobs. Recompute their SHA-256 and compare it
    to their filename (which is supposed to be their hash).
    If a mismatch is found (bit-rot), delete the local file and report the
    corruption to the coordinator so it can trigger a self-repair.
    """
    # Wait a bit before starting the first sweep
    await asyncio.sleep(5)
    
    async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
        while True:

            try:
                if os.path.isdir(STORAGE_PATH):
                    for entry in os.scandir(STORAGE_PATH):
                        if not entry.is_file():
                            continue
                            
                        blob_hash = entry.name
                        path = entry.path
                        
                        try:
                            with open(path, "rb") as f:
                                data = f.read()
                            
                            computed = hashlib.sha256(data).hexdigest()
                            if computed != blob_hash:
                                print(f"[{NODE_ID}] CORRUPTION DETECTED in {blob_hash}!")
                                
                                # 1. Delete the bad file locally
                                os.remove(path)
                                
                                # 2. Report to coordinator
                                try:
                                    await client.post(
                                        f"{COORDINATOR_URL}/report-corruption",
                                        json={"node_id": NODE_ID, "chunk_hash": blob_hash}
                                    )
                                    print(f"[{NODE_ID}] Reported corruption of {blob_hash} to coordinator.")
                                except Exception as e:
                                    print(f"[{NODE_ID}] Failed to report corruption: {e}")
                        except Exception as e:
                            print(f"[{NODE_ID}] Scrubber error reading {path}: {e}")
            except Exception as e:
                print(f"[{NODE_ID}] Scrubber sweep error: {e}")
                
            await asyncio.sleep(10)


# ── Drive auto-repair ────────────────────────────────────────────────────────

async def _run_repair() -> dict:
    """
    Run one repair attempt for THIS node's drive off the event loop.

    mount_manager.attempt_repair() shells out to ntfsfix/mount (blocking), so we
    push it to a worker thread to avoid stalling the async server.  The result
    is stored for /health and returned to callers.
    """
    # A dashboard request and the watchdog can arrive at the same time. Never
    # run two ntfsfix/mount sequences concurrently for one filesystem.
    async with _REPAIR_LOCK:
        result = await asyncio.to_thread(
            mount_manager.attempt_repair,
            _node_cfg(),
            NODE_ID,
            print,
            app_config.REPAIR_USE_SUDO,
        )
        _LAST_REPAIR["ts"] = time.monotonic()
        _LAST_REPAIR["result"] = result
        return result


async def mount_watchdog_loop():
    """
    Watch this node's removable drive and auto-repair it when it is
    PRESENT-but-UNMOUNTED — the signature of NTFS corruption after an unclean
    unplug.

    Crucially, this loop treats the three drive states completely differently:
      * "ok"        – healthy, do nothing.
      * "unmounted" – device is plugged in but won't mount → run ntfsfix+mount
                      (throttled by a cooldown so we never hammer a truly dead
                      disk).
      * "absent"    – device is not plugged in → do NOTHING.  There is nothing
                      to repair, and we must never act on a phantom device.

    Non-removable nodes (the Pi's own partitions) are skipped entirely.
    """
    await asyncio.sleep(7)  # let startup settle before first check

    cfg = _node_cfg()
    if not cfg.get("removable", False):
        # Pi root-FS nodes can never be unplugged; nothing to watch.
        return

    if not app_config.AUTO_REPAIR_ENABLED:
        print(f"[{NODE_ID}] Auto-repair disabled in config; watchdog idle.")
        return

    print(f"[{NODE_ID}] Mount watchdog active (removable NTFS drive).")

    while True:
        try:
            state = mount_manager.classify(_node_cfg())

            if state == mount_manager.UNMOUNTED:
                elapsed = time.monotonic() - _LAST_REPAIR["ts"]
                if elapsed >= app_config.AUTO_REPAIR_COOLDOWN_SECONDS:
                    print(f"[{NODE_ID}] Drive PRESENT but UNMOUNTED — "
                          f"starting automatic repair...")
                    result = await _run_repair()
                    if result["success"]:
                        print(f"[{NODE_ID}] Automatic repair SUCCESS: {result['message']}")
                    else:
                        print(f"[{NODE_ID}] Automatic repair did not succeed: "
                              f"{result['message']}")
                # else: still cooling down from the previous attempt — wait.

            # state == ABSENT  -> deliberately do nothing (not plugged in).
            # state == MOUNTED -> healthy.

        except Exception as e:
            print(f"[{NODE_ID}] Watchdog error: {e}")

        await asyncio.sleep(app_config.AUTO_REPAIR_INTERVAL_SECONDS)


@app.post("/repair-mount")
async def repair_mount():
    """
    Manually trigger a repair for this node's drive (used by the dashboard's
    Repair button, proxied through the coordinator).

    Honours the same safety rule as the watchdog: an ABSENT (unplugged) drive
    is reported back untouched rather than "repaired".
    """
    result = await _run_repair()
    return result


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(scrubber_loop())
    asyncio.create_task(mount_watchdog_loop())


# ── Run directly ────────────────────────────────────────────────────────────

def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Start a DFS storage node")
    parser.add_argument("--node-id", required=True, help="e.g. node1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--storage-path", required=True)
    parser.add_argument("--coordinator-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    global NODE_ID, STORAGE_PATH, COORDINATOR_URL
    NODE_ID = args.node_id
    STORAGE_PATH = args.storage_path
    COORDINATOR_URL = args.coordinator_url

    # Ensure storage directory exists
    os.makedirs(STORAGE_PATH, exist_ok=True)

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
