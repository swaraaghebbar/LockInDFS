"""
End-to-end test for Phase 8 (Garbage Collection).

Tests:
  1. Upload File A.
  2. Upload File B (duplicate).
  3. Soft delete File A.
  4. Wait for GC. Verify physical chunks remain (because File B uses them).
  5. Soft delete File B.
  6. Wait for GC. Verify physical chunks are deleted and DB is clean.
"""

import httpx
import os
import time

COORD = "http://127.0.0.1:8000"


def get_cluster_usage(client: httpx.Client) -> int:
    """Return total bytes used across all nodes."""
    resp = client.get(f"{COORD}/cluster")
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    return sum(n.get("total_bytes", 0) for n in nodes.values() if n.get("status") == "ok")


def main():
    print("=" * 60)
    print("  DFS Phase 8 – GC & Soft Delete Test")
    print("=" * 60)

    # 1MB file so it fits in one chunk (less noise)
    test_data = b"G" * (1024 * 1024)

    with httpx.Client(timeout=30) as client:
        initial_usage = get_cluster_usage(client)
        print(f"[0] Initial cluster storage usage: {initial_usage} bytes")

        # ── 1. Upload File A ─────────────────────────────────────────────
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("file_A.txt", test_data, "text/plain")},
        )
        assert resp.status_code == 200
        file_a_id = resp.json()["file_id"]
        print(f"\n[1] Uploaded File A. file_id={file_a_id[:12]}...")

        time.sleep(1)
        usage_after_a = get_cluster_usage(client)
        print(f"    Total cluster storage grew by: {usage_after_a - initial_usage} bytes")

        # ── 2. Upload File B (Duplicate) ─────────────────────────────────
        # Note: exactly the same content, so it will be deduplicated.
        # Wait, if it's EXACTLY the same content, upload_file just returns 200 File already exists.
        # To test chunk-level deduplication, let's append one byte.
        test_data_b = test_data + b"X"
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("file_B.txt", test_data_b, "text/plain")},
        )
        assert resp.status_code == 200
        file_b_id = resp.json()["file_id"]
        print(f"\n[2] Uploaded File B (shares chunk 0). file_id={file_b_id[:12]}...")

        time.sleep(1)
        usage_after_b = get_cluster_usage(client)
        print(f"    Total cluster storage grew by: {usage_after_b - usage_after_a} bytes")

        # ── 3. Soft Delete File A ────────────────────────────────────────
        print(f"\n[3] Soft Deleting File A ({file_a_id[:12]})...")
        resp = client.delete(f"{COORD}/files/{file_a_id}")
        assert resp.status_code == 200
        assert "soft_deleted" in resp.json()["status"]

        # ── 4. Wait for GC ───────────────────────────────────────────────
        print("\n[4] Waiting 15s for Background GC...")
        time.sleep(15)

        usage_after_gc_a = get_cluster_usage(client)
        print(f"    Storage used after GC for A: {usage_after_gc_a} bytes")
        assert usage_after_gc_a == usage_after_b, "Storage dropped! GC deleted shared chunks!"
        print("    [OK] Shared chunks safely preserved by GC.")

        # ── 5. Soft Delete File B ────────────────────────────────────────
        print(f"\n[5] Soft Deleting File B ({file_b_id[:12]})...")
        resp = client.delete(f"{COORD}/files/{file_b_id}")
        assert resp.status_code == 200

        # ── 6. Wait for GC ───────────────────────────────────────────────
        print("\n[6] Waiting 15s for Final GC...")
        time.sleep(15)

        usage_after_gc_b = get_cluster_usage(client)
        print(f"    Storage used after GC for B: {usage_after_gc_b} bytes")
        assert usage_after_gc_b == initial_usage, "Storage leak! GC did not clean up unshared chunks."
        print("    [OK] Final cleanup successful! All physical chunks reclaimed.")

    print("\n" + "=" * 60)
    print("  [OK] ALL PHASE 8 TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
