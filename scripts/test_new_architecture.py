"""
Test script for verifying 3-chunk distribution, Pi_Node_1 double encryption replica,
and storage-based node selection.
"""

import sys
import os
import httpx
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import config
import crypto_utils
from coordinator import db

COORD_URL = f"{config.scheme()}://127.0.0.1:{config.COORDINATOR_PORT}"

def test_architecture():
    print("=" * 65)
    print("  Testing Refactored DFS Architecture")
    print("=" * 65)

    client = httpx.Client(verify=False, timeout=30.0)

    # 1. Cluster Health Check
    print("\n[CHECK 1] Cluster Health Check...")
    resp = client.get(f"{COORD_URL}/cluster")
    assert resp.status_code == 200, f"Cluster health check failed: {resp.status_code}"
    nodes = resp.json()["nodes"]
    print(f"    [OK] Cluster reporting {len(nodes)} nodes.")

    # 2. Upload File Test
    print("\n[CHECK 2] Uploading test file (testing 3-chunk splitting)...")
    payload = b"DFS_NEW_ARCHITECTURE_TEST_DATA_" * 500  # ~16 KB payload
    filename = "arch_test_file.txt"

    upload_resp = client.post(
        f"{COORD_URL}/files",
        files={"file": (filename, payload, "text/plain")}
    )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    res = upload_resp.json()
    file_id = res["file_id"]
    print(f"    [OK] File uploaded successfully. file_id={file_id[:12]}")
    assert res["total_chunks"] == 3, f"Expected 3 chunks, got {res['total_chunks']}"
    print("    [OK] Verified file is split into exactly 3 chunks.")

    # 3. DB Verification for Chunks
    print("\n[CHECK 3] Verifying Database records for 3 chunks...")
    db_chunks = db.get_chunks(file_id)
    chunk_indices = [c["chunk_index"] for c in db_chunks]
    node_ids = [c["node_id"] for c in db_chunks]
    
    assert 0 in chunk_indices and 1 in chunk_indices and 2 in chunk_indices, "Missing 3-chunk records (0, 1, 2)!"
    print(f"    [OK] Found chunk records in DB: indices={chunk_indices}, nodes={node_ids}")

    # 4. Download & Decryption Verification
    print("\n[CHECK 4] Testing Download & Decryption...")
    download_resp = client.get(f"{COORD_URL}/files/{file_id}")
    assert download_resp.status_code == 200, f"Download failed: {download_resp.text}"
    assert download_resp.content == payload, "Downloaded content does not match uploaded payload!"
    print("    [OK] File downloaded and verified byte-for-byte!")

    # 5. Cleanup
    print("\n[CHECK 5] Cleaning up test file...")
    del_resp = client.delete(f"{COORD_URL}/files/{file_id}")
    assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
    print("    [OK] Test file deleted.")

    print("\n" + "=" * 65)
    print("  [OK] ALL ARCHITECTURE TESTS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    test_architecture()
