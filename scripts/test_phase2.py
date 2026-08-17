"""
End-to-end smoke test for Phase 2.

Tests:
  1. Create a test file (>1 MiB so it gets chunked)
  2. Upload via POST /files (Coordinator will distribute chunks to 3 nodes)
  3. Verify chunks are distributed (by checking the manifest)
  4. List files via GET /files
  5. Download via GET /files/{id}
  6. Verify downloaded content matches the original (SHA-256)
  7. Delete via DELETE /files/{id}
  8. Confirm deletion
"""

import hashlib
import httpx
import os

COORD = "http://127.0.0.1:8000"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    print("=" * 60)
    print("  DFS Phase 2 – End-to-End Smoke Test")
    print("=" * 60)

    # ── 1. Create test data (2.5 MiB → should produce 3 chunks) ─────────
    test_data = os.urandom(2 * 1024 * 1024 + 512 * 1024)  # 2.5 MiB
    original_hash = sha256(test_data)
    print(f"\n[1] Created test file: {len(test_data)} bytes")
    print(f"    SHA-256: {original_hash}")

    with httpx.Client(timeout=30) as client:
        # ── 2. Upload ────────────────────────────────────────────────────
        print("\n[2] Uploading via POST /files ...")
        resp = client.post(
            f"{COORD}/files",
            files={"file": ("testfile.bin", test_data, "application/octet-stream")},
        )
        print(f"    Status: {resp.status_code}")
        upload_result = resp.json()
        print(f"    Response: file_id={upload_result.get('file_id')}")
        print(f"    Chunks: {upload_result.get('total_chunks')}")
        assert resp.status_code == 200, f"Upload failed: {resp.text}"

        file_id = upload_result["file_id"]
        assert file_id == original_hash, (
            f"File ID mismatch: expected {original_hash}, got {file_id}"
        )
        print("    [OK] file_id matches our local SHA-256")

        # ── 3. Verify Distribution ───────────────────────────────────────
        print("\n[3] Verifying Multi-Node Distribution ...")
        manifest = upload_result.get("chunks", [])
        nodes_used = set(chunk["node"] for chunk in manifest)
        print(f"    Nodes used for chunks: {', '.join(nodes_used)}")
        assert len(nodes_used) > 1, "Chunks were not distributed across multiple nodes!"
        print("    [OK] Chunks successfully distributed across nodes")

        # ── 4. List files ────────────────────────────────────────────────
        print("\n[4] Listing files via GET /files ...")
        resp = client.get(f"{COORD}/files")
        files_list = resp.json()
        print(f"    Found {files_list['count']} file(s)")
        assert files_list["count"] >= 1

        # ── 5. Download ──────────────────────────────────────────────────
        print(f"\n[5] Downloading via GET /files/{file_id[:12]}... ...")
        resp = client.get(f"{COORD}/files/{file_id}")
        print(f"    Status: {resp.status_code}")
        assert resp.status_code == 200, f"Download failed: {resp.text}"

        downloaded_data = resp.content
        print(f"    Downloaded {len(downloaded_data)} bytes")

        # ── 6. Verify end-to-end integrity ───────────────────────────────
        downloaded_hash = sha256(downloaded_data)
        print(f"\n[6] End-to-end verification:")
        print(f"    Original  SHA-256: {original_hash}")
        print(f"    Downloaded SHA-256: {downloaded_hash}")
        assert downloaded_hash == original_hash, (
            f"INTEGRITY FAILURE: {original_hash} != {downloaded_hash}"
        )
        print("    [OK] SHA-256 matches – end-to-end integrity verified!")

        # ── 7. Delete ────────────────────────────────────────────────────
        print(f"\n[7] Deleting via DELETE /files/{file_id[:12]}... ...")
        resp = client.delete(f"{COORD}/files/{file_id}")
        print(f"    Status: {resp.status_code}")
        delete_result = resp.json()
        print(f"    Chunks removed: {delete_result.get('chunks_removed')}")
        assert resp.status_code == 200

        # ── 8. Confirm gone ──────────────────────────────────────────────
        print("\n[8] Confirming file is gone ...")
        resp = client.get(f"{COORD}/files/{file_id}")
        print(f"    Status: {resp.status_code} (expected 404)")
        assert resp.status_code == 404

        # ── 9. Cluster health ────────────────────────────────────────────
        print("\n[9] Cluster health via GET /cluster ...")
        resp = client.get(f"{COORD}/cluster")
        cluster = resp.json()
        for node_id, info in cluster["nodes"].items():
            status = info.get("status", "?")
            print(f"    {node_id}: {status}")

    print("\n" + "=" * 60)
    print("  [OK] ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
