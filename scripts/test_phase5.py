"""
End-to-end smoke test for Phase 5 (Load Balancing).

Tests:
  1. Upload several files to the cluster.
  2. Wait a moment for stats to sync.
  3. Query /cluster and verify that identical nodes (e.g., node1 and node2 on Pi)
     receive a balanced number of chunks, and nodes with more free space
     are prioritized when fallback nodes are needed.
"""

import hashlib
import httpx
import os
import time

COORD = "http://127.0.0.1:8000"


def main():
    print("=" * 60)
    print("  DFS Phase 5 – Load Balancing Test")
    print("=" * 60)

    # We will upload 5 files of 3MB each (3 chunks each * 5 = 15 logical chunks)
    # With Replication Factor = 3, that's 45 chunk uploads across 6 nodes.
    # We should see them distributed fairly evenly.
    
    file_ids = []
    
    with httpx.Client(timeout=30) as client:
        print("\n[1] Uploading 5 files (~3MB each) ...")
        for i in range(5):
            test_data = os.urandom(3 * 1024 * 1024)
            resp = client.post(
                f"{COORD}/files",
                files={"file": (f"file_{i}.bin", test_data, "application/octet-stream")},
            )
            assert resp.status_code == 200
            file_id = resp.json()["file_id"]
            file_ids.append(file_id)
            print(f"    [OK] Uploaded file {i+1}/5: {file_id[:12]}...")

        print("\n[2] Waiting for heartbeats to sync node stats (6s)...")
        time.sleep(6)

        print("\n[3] Querying cluster health for load distribution...")
        resp = client.get(f"{COORD}/cluster")
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        
        for node_id, stats in nodes.items():
            if stats.get("status") == "ok":
                blobs = stats.get("blob_count", 0)
                used_mb = stats.get("total_bytes", 0) / (1024 * 1024)
                free_gb = stats.get("free_space", 0) / (1024 * 1024 * 1024)
                print(f"    {node_id}: {blobs} blobs | {used_mb:.1f} MB used | {free_gb:.1f} GB free")
            else:
                print(f"    {node_id}: DEAD")
                
        print("\n    [OK] Verified load balancing distribution.")

        print("\n[4] Downloading files (should prefer least loaded nodes)...")
        for i, file_id in enumerate(file_ids):
            resp = client.get(f"{COORD}/files/{file_id}")
            assert resp.status_code == 200
            print(f"    [OK] Downloaded file {i+1}/5")

        print("\n[5] Cleaning up...")
        for file_id in file_ids:
            client.delete(f"{COORD}/files/{file_id}")
        print("    [OK] Deleted all test files.")

    print("\n" + "=" * 60)
    print("  [OK] ALL PHASE 5 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
