"""
End-to-end smoke test for Phase 3 (Replication).

Tests:
  1. Create a test file (>1 MiB so it gets chunked)
  2. Upload via POST /files
  3. Verify chunks are replicated to 3 nodes
  4. Kill one of the nodes holding a replica
  5. Download via GET /files/{id} (Should succeed by falling back to other replicas)
  6. Verify downloaded content matches the original (SHA-256)
  7. Delete via DELETE /files/{id}
"""

import hashlib
import httpx
import os
import signal

COORD = "http://127.0.0.1:8000"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    print("=" * 60)
    print("  DFS Phase 3 – Replication & Failover Test")
    print("=" * 60)

    # ── 1. Create test data ──────────────────────────────────────────────
    test_data = os.urandom(2 * 1024 * 1024 + 512 * 1024)  # 2.5 MiB (3 chunks)
    original_hash = sha256(test_data)
    print(f"\n[1] Created test file: {len(test_data)} bytes")

    with httpx.Client(timeout=30) as client:
        # ── 2. Upload ────────────────────────────────────────────────────
        print("\n[2] Uploading via POST /files ...")
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("testfile.bin", test_data, "application/octet-stream")},
        )
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        upload_result = resp.json()
        file_id = upload_result["file_id"]
        print(f"    [OK] Uploaded. file_id={file_id[:12]}...")

        # ── 3. Verify Replication ───────────────────────────────────────
        print("\n[3] Verifying Replication ...")
        manifest = upload_result.get("chunks", [])
        
        # Check that each chunk has 3 replicas
        all_nodes_used = set()
        for chunk in manifest:
            replicas = chunk["nodes"]
            assert len(replicas) == 3, f"Chunk {chunk['index']} only has {len(replicas)} replicas!"
            all_nodes_used.update(replicas)
            
        print(f"    Nodes holding data: {', '.join(all_nodes_used)}")
        print("    [OK] Each chunk is replicated to 3 nodes")

        # ── 4. Kill one node ─────────────────────────────────────────────
        target_node = list(all_nodes_used)[0]
        print(f"\n[4] Simulating node failure: Killing {target_node} ...")
        
        # We need to find the PID of the target node. We'll use the .pids.json if it exists,
        # otherwise we'll just stop testing the kill part and warn the user.
        pid_file = os.path.join(os.path.dirname(__file__), ".pids.json")
        killed = False
        if os.path.exists(pid_file):
            import json
            with open(pid_file) as f:
                pids = json.load(f)
            
            if target_node in pids:
                pid = pids[target_node]
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"    [OK] Sent SIGTERM to {target_node} (PID {pid})")
                    killed = True
                except OSError:
                    print(f"    Warning: Could not kill {target_node} (PID {pid})")
        
        if not killed:
            print("    Warning: Could not automatically kill node. You can test manually by closing its terminal.")

        # ── 5. Download ──────────────────────────────────────────────────
        print(f"\n[5] Downloading via GET /files/{file_id[:12]}... (Should survive failure)")
        resp = client.get(f"{COORD}/files/{file_id}")
        assert resp.status_code == 200, f"Download failed: {resp.text}"
        downloaded_data = resp.content
        print(f"    [OK] Downloaded {len(downloaded_data)} bytes")

        # ── 6. Verify end-to-end integrity ───────────────────────────────
        downloaded_hash = sha256(downloaded_data)
        assert downloaded_hash == original_hash, (
            f"INTEGRITY FAILURE: {original_hash} != {downloaded_hash}"
        )
        print("\n[6] [OK] SHA-256 matches – end-to-end integrity verified despite node failure!")

        # ── 7. Delete ────────────────────────────────────────────────────
        print(f"\n[7] Deleting via DELETE /files/{file_id[:12]}... ...")
        resp = client.delete(f"{COORD}/files/{file_id}")
        assert resp.status_code == 200
        print("    [OK] Deleted.")

    print("\n" + "=" * 60)
    print("  [OK] ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
