"""
End-to-end test for Phase 10 (Graceful Degradation + Performance).

Tests:
  1. Upload a file while all nodes are healthy → baseline success.
  2. Kill node1 process, upload another file → succeeds on remaining nodes.
  3. Kill node2 process too, download file 1 → still succeeds using replicas.
  4. Upload yet another file with 2 dead nodes → still works.
"""

import httpx
import time
import os
import json
import signal

COORD = "http://127.0.0.1:8000"
PID_FILE = os.path.join(os.path.dirname(__file__), ".pids.json")


def kill_node(node_id):
    """Kill a node process using the PID file written by launch.py."""
    if not os.path.exists(PID_FILE):
        print(f"    [!] PID file not found at {PID_FILE}")
        return False

    with open(PID_FILE) as f:
        pids = json.load(f)

    pid = pids.get(node_id)
    if not pid:
        print(f"    [!] No PID entry for {node_id}")
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"    Killed {node_id} (PID {pid})")
        return True
    except (ProcessLookupError, OSError) as e:
        print(f"    [!] Could not kill {node_id} (PID {pid}): {e}")
        return False


def wait_for_heartbeat():
    """Wait for heartbeat loop to detect the dead node."""
    print("    Waiting 8s for heartbeat detection...")
    time.sleep(8)


def main():
    print("=" * 60)
    print("  DFS Phase 10 — Graceful Degradation & Performance Test")
    print("=" * 60)

    test_data_1 = b"A" * (2 * 1024 * 1024 + 500)  # ~2 MiB (3 chunks)
    test_data_2 = b"B" * (1024 * 1024 + 100)       # ~1 MiB (2 chunks)

    with httpx.Client(timeout=30) as client:
        # ── 1. Baseline: Upload with all nodes healthy ───────────────────
        print("\n[1] Uploading file_1 with ALL nodes healthy...")
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("test_degraded_1.bin", test_data_1, "application/octet-stream")},
        )
        assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
        file_1_id = resp.json()["file_id"]
        print(f"    [OK] Uploaded file_1. id={file_1_id[:12]}...")

        # Verify download works
        resp = client.get(f"{COORD}/files/{file_1_id}")
        assert resp.status_code == 200
        assert resp.content == test_data_1
        print("    [OK] Download verified.")

        # ── 2. Kill node1 and upload a NEW file ──────────────────────────
        print("\n[2] Killing node1...")
        killed = kill_node("node1")
        assert killed, "Failed to kill node1"
        wait_for_heartbeat()

        # Check cluster status
        resp = client.get(f"{COORD}/cluster")
        nodes = resp.json()["nodes"]
        node1_status = nodes.get("node1", {}).get("status", "unknown")
        print(f"    node1 status: {node1_status}")
        assert node1_status in ("dead", "unreachable"), f"node1 should be dead/unreachable, got: {node1_status}"

        print("    Uploading file_2 in DEGRADED mode (node1 down)...")
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("test_degraded_2.bin", test_data_2, "application/octet-stream")},
        )
        assert resp.status_code == 200, f"Upload failed in degraded mode: {resp.status_code} {resp.text}"
        file_2_id = resp.json()["file_id"]
        print(f"    [OK] Uploaded file_2 despite node1 being down. id={file_2_id[:12]}...")

        # ── 3. Kill node2 AND download file_1 ────────────────────────────
        print("\n[3] Killing node2...")
        killed = kill_node("node2")
        assert killed, "Failed to kill node2"
        wait_for_heartbeat()

        resp = client.get(f"{COORD}/cluster")
        node2_status = resp.json()["nodes"].get("node2", {}).get("status", "unknown")
        print(f"    node2 status: {node2_status}")
        assert node2_status in ("dead", "unreachable"), f"node2 should be dead/unreachable, got: {node2_status}"

        # Download file_1 — it has replicas on 3 nodes; with 2 dead,
        # it should still succeed via the surviving replica(s).
        print("    Downloading file_1 with 2 nodes dead...")
        resp = client.get(f"{COORD}/files/{file_1_id}")
        assert resp.status_code == 200, f"Download failed: {resp.status_code} {resp.text}"
        assert resp.content == test_data_1, "Data mismatch!"
        print("    [OK] Download succeeded despite 2 dead nodes!")

        # ── 4. Download file_2 in degraded mode ──────────────────────────
        print("\n[4] Downloading file_2 with 2 nodes dead...")
        resp = client.get(f"{COORD}/files/{file_2_id}")
        assert resp.status_code == 200, f"Download failed: {resp.status_code} {resp.text}"
        assert resp.content == test_data_2, "Data mismatch!"
        print("    [OK] Download succeeded!")

        # ── 5. Upload ANOTHER file with 2 dead nodes ────────────────────
        print("\n[5] Uploading file_3 with 2 dead nodes...")
        test_data_3 = b"C" * 500_000
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("test_degraded_3.bin", test_data_3, "application/octet-stream")},
        )
        assert resp.status_code == 200, f"Upload failed: {resp.status_code}"
        file_3_id = resp.json()["file_id"]
        print(f"    [OK] Upload succeeded. id={file_3_id[:12]}...")

        # Download it back
        resp = client.get(f"{COORD}/files/{file_3_id}")
        assert resp.status_code == 200
        assert resp.content == test_data_3
        print("    [OK] Download verified!")

        # Cleanup
        for fid in [file_1_id, file_2_id, file_3_id]:
            client.delete(f"{COORD}/files/{fid}")

    print("\n" + "=" * 60)
    print("  [OK] ALL PHASE 10 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
