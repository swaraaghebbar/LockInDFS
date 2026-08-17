"""
End-to-end test for Phase 7 (Scrubbing & Integrity Self-Repair).

Tests:
  1. Upload a file to the cluster.
  2. Query the DB to find exactly which physical node file holds its chunk.
  3. Corrupt that physical file on disk (simulate bit-rot).
  4. Wait ~15 seconds for the background scrubber to detect it and the coordinator to heal it.
  5. Verify the file can be successfully downloaded (i.e. the chunk was healed).
"""

import httpx
import os
import time
import sqlite3

COORD = "http://127.0.0.1:8000"
DB_PATH = "coordinator/metadata.db"

def main():
    print("=" * 60)
    print("  DFS Phase 7 – Scrubber & Self-Repair Test")
    print("=" * 60)

    test_data = b"Phase 7 Integrity Test Data. This is important."
    
    with httpx.Client(timeout=30) as client:
        # ── 1. Upload a file ─────────────────────────────────────────────
        print(f"\n[1] Uploading test file...")
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("important.txt", test_data, "text/plain")},
        )
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]
        print(f"    [OK] Uploaded. file_id={file_id[:12]}...")

        # ── 2. Find a physical chunk location ────────────────────────────
        print("\n[2] Finding a physical chunk on disk...")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Get one replica
        row = conn.execute(
            "SELECT chunk_hash, node_id FROM chunks WHERE file_id = ? LIMIT 1", 
            (file_id,)
        ).fetchone()
        chunk_hash = row["chunk_hash"]
        node_id = row["node_id"]
        
        print(f"    Target chunk {chunk_hash[:12]} located on node: {node_id}")
        
        # Determine physical path
        physical_path = os.path.join("data", node_id, chunk_hash)
        
        if not os.path.exists(physical_path):
            # Try to resolve tier directory structure if using launch.py defaults
            # Actually launch.py maps --storage-path to e.g. "./data/node1"
            print(f"    Expected path {physical_path} not found. Ensure nodes use ./data/nodeX")
            assert False, "Physical path not found!"

        print(f"    [OK] Physical path located: {physical_path}")

        # ── 3. Corrupt the chunk ─────────────────────────────────────────
        print("\n[3] Simulating bit-rot by overwriting the first 5 bytes...")
        
        with open(physical_path, "r+b") as f:
            f.seek(0)
            f.write(b"CORPT")
            
        print("    [OK] File is now corrupted!")

        # ── 4. Wait for Scrubber & Healer ────────────────────────────────
        print("\n[4] Waiting 15s for the node background scrubber to detect it...")
        # Scrubber runs every 10s. We wait 15s to be safe.
        time.sleep(15)
        
        # Check if the physical file exists again. The node deletes the corrupt one, 
        # and the coordinator immediately pushes a fresh copy.
        if os.path.exists(physical_path):
            print("    [OK] A file exists at the physical path.")
        else:
            print("    [!] File does not exist! Repair failed to push a new copy.")
            assert False, "File was deleted by scrubber but never repaired!"

        # ── 5. Verify download ───────────────────────────────────────────
        print("\n[5] Downloading file to verify integrity...")
        resp = client.get(f"{COORD}/files/{file_id}")
        assert resp.status_code == 200, f"Download failed: {resp.status_code}"
        
        downloaded = resp.content
        assert downloaded == test_data, "Data mismatch! Repair put the wrong data."
        print("    [OK] Download successful! Data matches original perfectly.")

        # Cleanup
        client.delete(f"{COORD}/files/{file_id}")

    print("\n" + "=" * 60)
    print("  [OK] ALL PHASE 7 TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
