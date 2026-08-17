"""
End-to-end test for Phase 9 (Hot/Cold Tiering).

Tests:
  1. Upload a file.
  2. Verify chunks are initially on the 'hot' tier (node1, node2) because of temperature.
  3. Wait 16s so the file becomes 'cold'.
  4. Wait for tiering_loop to migrate chunks.
  5. Verify chunks are now on the 'cold' tier (node3, node4).
  6. Read the file (updates last_accessed, making it 'hot' again).
  7. Wait for tiering_loop to migrate chunks back.
  8. Verify chunks are back on the 'hot' tier.
"""

import httpx
import sqlite3
import time

COORD = "http://127.0.0.1:8000"
DB_PATH = "coordinator/metadata.db"


def get_chunk_nodes(file_id: str) -> list[str]:
    """Return a list of all node_ids currently holding chunks for this file."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT DISTINCT node_id FROM chunks WHERE file_id = ?", (file_id,)).fetchall()
    conn.close()
    return [r["node_id"] for r in rows]


def main():
    print("=" * 60)
    print("  DFS Phase 9 – Hot/Cold Tiering Test")
    print("=" * 60)

    test_data = b"T" * (1024 * 1024)

    with httpx.Client(timeout=30) as client:
        # ── 1. Upload File ───────────────────────────────────────────────
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("tiering_test.txt", test_data, "text/plain")},
        )
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]
        print(f"\n[1] Uploaded file. file_id={file_id[:12]}...")

        # ── 2. Verify Initial Placement (Hot) ────────────────────────────
        time.sleep(2)
        initial_nodes = get_chunk_nodes(file_id)
        print(f"    Initial chunk nodes: {initial_nodes}")
        
        # It should prioritize hot > warm > cold.
        # With RF=3, it should be on hot (node1, node2) and warm (node5 or node6).
        has_hot = any(n in ("node1", "node2") for n in initial_nodes)
        assert has_hot, "File was not placed on hot nodes initially!"
        print("    [OK] File placed on hot tier.")

        # ── 3. Wait for file to become Cold ──────────────────────────────
        print("\n[2] Waiting 16s for file to become cold...")
        time.sleep(16)
        
        # ── 4. Wait for Tiering Loop ─────────────────────────────────────
        print("[3] Waiting 12s for tiering loop to migrate chunks to cold tier...")
        time.sleep(12)
        
        # ── 5. Verify Cold Placement ─────────────────────────────────────
        cold_nodes = get_chunk_nodes(file_id)
        print(f"    Nodes after cooling: {cold_nodes}")
        has_hot_after_cool = any(n in ("node1", "node2") for n in cold_nodes)
        assert not has_hot_after_cool, "File is still on hot nodes after cooling!"
        print("    [OK] File successfully migrated to cold/warm tiers!")

        # ── 6. Read File (Make it Hot) ───────────────────────────────────
        print("\n[4] Downloading file (simulating user access)...")
        resp = client.get(f"{COORD}/files/{file_id}")
        assert resp.status_code == 200
        print("    [OK] File downloaded, last_accessed updated.")

        # ── 7. Wait for Tiering Loop (Back to Hot) ───────────────────────
        print("[5] Waiting 12s for tiering loop to migrate chunks back to hot tier...")
        time.sleep(12)
        
        # ── 8. Verify Hot Placement ──────────────────────────────────────
        hot_nodes = get_chunk_nodes(file_id)
        print(f"    Nodes after warming: {hot_nodes}")
        has_hot_after_warm = any(n in ("node1", "node2") for n in hot_nodes)
        assert has_hot_after_warm, "File was not migrated back to hot nodes!"
        print("    [OK] File successfully migrated back to hot tier!")
        
        # Cleanup
        client.delete(f"{COORD}/files/{file_id}")

    print("\n" + "=" * 60)
    print("  [OK] ALL PHASE 9 TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
