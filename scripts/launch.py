"""
Launch script – starts all 6 storage-node processes + the coordinator.

Usage:
    python scripts/launch.py          # start everything
    python scripts/launch.py --stop   # kill all child processes

On Windows this uses subprocess; on Linux it can be swapped for systemd units.
"""

import subprocess
import sys
import os
import signal
import time
import json

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from config import NODES, COORDINATOR_PORT

PID_FILE = os.path.join(ROOT, "scripts", ".pids.json")


def start_all():
    """Spawn each node and the coordinator as separate processes."""
    pids = {}

    import config
    import crypto_utils
    cert_file, key_file = crypto_utils.generate_self_signed_cert()

    # ── Start storage nodes ──────────────────────────────────────────────
    for node_id, cfg in NODES.items():
        storage_cfg = str(cfg["storage_path"])
        # If absolute path (e.g. /media/pi/...), use it directly; otherwise join with ROOT
        if os.path.isabs(storage_cfg):
            storage = storage_cfg
        else:
            storage = os.path.join(ROOT, storage_cfg)
            os.makedirs(storage, exist_ok=True)

        cmd = [
            sys.executable, "-m", "uvicorn", "node.main:app",
            "--host", "0.0.0.0",
            "--port", str(cfg["port"]),
            "--ssl-certfile", cert_file,
            "--ssl-keyfile", key_file,
        ]
        # Pass custom node CLI args via env or custom run
        env = os.environ.copy()
        env["NODE_ID"] = node_id
        env["STORAGE_PATH"] = storage
        env["COORDINATOR_URL"] = f"{config.scheme()}://127.0.0.1:{COORDINATOR_PORT}"

        # Modify command to run uvicorn with node main app directly
        cmd = [
            sys.executable, "-c",
            f"import uvicorn, node.main; node.main.NODE_ID='{node_id}'; node.main.STORAGE_PATH=r'{storage}'; node.main.COORDINATOR_URL='{config.scheme()}://127.0.0.1:{COORDINATOR_PORT}'; uvicorn.run(node.main.app, host='0.0.0.0', port={cfg['port']}, ssl_certfile=r'{cert_file}', ssl_keyfile=r'{key_file}')"
        ]
        print(f"  Starting {node_id} on HTTPS :{cfg['port']}  ->  {storage}")
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
        pids[node_id] = proc.pid

    # Small delay so nodes are up before coordinator tries to reach them
    time.sleep(2)

    # ── Start coordinator ────────────────────────────────────────────────
    cmd = [sys.executable, "-m", "uvicorn", "coordinator.main:app",
           "--host", "0.0.0.0", "--port", str(COORDINATOR_PORT),
           "--ssl-certfile", cert_file, "--ssl-keyfile", key_file]
    print(f"  Starting coordinator on HTTPS :{COORDINATOR_PORT}")
    proc = subprocess.Popen(cmd, cwd=ROOT)
    pids["coordinator"] = proc.pid


    # Save PIDs for later cleanup
    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)

    print(f"\n[*] All processes started. PIDs saved to {PID_FILE}")
    print("  Press Ctrl+C to stop all processes.\n")

    # Wait and forward Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


def stop_all():
    """Kill all processes recorded in the PID file."""
    if not os.path.exists(PID_FILE):
        print("No PID file found – nothing to stop.")
        return

    with open(PID_FILE) as f:
        pids = json.load(f)

    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Stopped {name} (PID {pid})")
        except (ProcessLookupError, OSError):
            print(f"  {name} (PID {pid}) already exited")

    os.remove(PID_FILE)
    print("[*] All processes stopped.")


if __name__ == "__main__":
    if "--stop" in sys.argv:
        stop_all()
    else:
        print("\n[*] Launching DFS cluster ...\n")
        start_all()
