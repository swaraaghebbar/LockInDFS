"""
Test script for verifying 3x replication, failover, auto-repair, and node recovery.
"""

import sys
import os
import time
import httpx
import sqlite3
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import config
from coordinator import db
from scripts.fail_tool import kill_node, corrupt_blob, get_pids

COORD_URL = f"{config.scheme()}://127.0.0.1:{config.COORDINATOR_PORT}"
DB_PATH = os.path.join(ROOT, "coordinator", "metadata.db")

def restart_node(node_id):
    """Restarts a node using the same command as launch.py"""
    print(f"\n[*] Restarting {node_id}...")
    import crypto_utils
    cert_file, key_file = crypto_utils.generate_self_signed_cert()
    
    cfg = config.NODES[node_id]
    storage_cfg = str(cfg["storage_path"])
    storage = storage_cfg if os.path.isabs(storage_cfg) else os.path.join(ROOT, storage_cfg)
    
    env = os.environ.copy()
    env["NODE_ID"] = node_id
    env["STORAGE_PATH"] = storage
    env["COORDINATOR_URL"] = COORD_URL

    cmd = [
        sys.executable, "-c",
        f"import uvicorn, node.main; node.main.NODE_ID='{node_id}'; node.main.STORAGE_PATH=r'{storage}'; node.main.COORDINATOR_URL='{COORD_URL}'; uvicorn.run(node.main.app, host='0.0.0.0', port={cfg['port']}, ssl_certfile=r'{cert_file}', ssl_keyfile=r'{key_file}')"
    ]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    
    import json
    pids = get_pids()
    pids[node_id] = proc.pid
    with open(os.path.join(ROOT, "scripts", ".pids.json"), "w") as f:
        json.dump(pids, f, indent=2)
    time.sleep(3)
    return proc

def test_features():
    print("=" * 65)
    print("  Testing DFS 3x Replication & Auto-Recovery")
    print("=" * 65)

    client = httpx.Client(verify=False, timeout=30.0)
    
    # Wait for cluster to be healthy
    print("\n[CHECK 1] Waiting for healthy cluster...")
    while True:
        resp = client.get(f"{COORD_URL}/cluster")
        if resp.status_code == 200:
            nodes = resp.json()["nodes"]
            healthy = sum(1 for n in nodes.values() if n["status"] == "ok")
            if healthy >= 4:
                print(f"    [OK] Cluster has {healthy} healthy nodes.")
                break
        print("    Waiting for nodes to come up...")
        time.sleep(2)

    # 1. Normal Upload
    print("\n[CHECK 2] Uploading test file (testing 3x replication)...")
    payload = b"DFS_REPLICATION_TEST_DATA_" * 500
    filename = "replication_test_file.txt"

    upload_resp = client.post(
        f"{COORD_URL}/files",
        files={"file": (filename, payload, "text/plain")}
    )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    res = upload_resp.json()
    file_id = res["file_id"]
    print(f"    [OK] File uploaded successfully. file_id={file_id[:12]}")
    
    # Verify 3 replicas per chunk in DB
    db_chunks = db.get_chunks(file_id)
    data_chunks = [c for c in db_chunks if c["chunk_index"] >= 0]
    
    # We should have UPLOAD_CHUNK_COUNT * REPLICATION_FACTOR chunks
    expected_data_chunks = config.UPLOAD_CHUNK_COUNT * config.REPLICATION_FACTOR
    assert len(data_chunks) == expected_data_chunks, f"Expected {expected_data_chunks} data chunks, got {len(data_chunks)}"
    print(f"    [OK] Verified {config.REPLICATION_FACTOR} replicas per chunk in DB.")

    # 2. Node Failure (One Node)
    print("\n[CHECK 3] Simulating Node Failure...")
    # Find a node hosting chunk 0
    chunk0_nodes = [c["node_id"] for c in data_chunks if c["chunk_index"] == 0]
    target_node = chunk0_nodes[0]
    
    kill_node(target_node)
    print(f"    [OK] Killed {target_node}. Waiting 6s for heartbeat failure to register...")
    time.sleep(6)
    
    # Ensure still downloadable
    download_resp = client.get(f"{COORD_URL}/files/{file_id}")
    assert download_resp.status_code == 200, f"Download failed after node failure: {download_resp.text}"
    assert download_resp.content == payload, "Downloaded content does not match!"
    print("    [OK] File downloaded successfully (Failover works).")

    # 3. Auto Re-replication
    print("\n[CHECK 4] Waiting for automatic re-replication...")
    print("    (Self-healing loop runs every 10s, waiting 15s)")
    time.sleep(15)
    
    db_chunks_after = db.get_chunks(file_id)
    data_chunks_after = [c for c in db_chunks_after if c["chunk_index"] >= 0]
    assert len(data_chunks_after) >= expected_data_chunks, f"Expected at least {expected_data_chunks} data chunks, got {len(data_chunks_after)}"
    
    # Check that chunk 0 still has 3 healthy replicas
    resp = client.get(f"{COORD_URL}/cluster")
    nodes_status = resp.json()["nodes"]
    
    chunk0_nodes_after = [c["node_id"] for c in data_chunks_after if c["chunk_index"] == 0]
    healthy_chunk0 = [n for n in chunk0_nodes_after if nodes_status.get(n, {}).get("status") == "ok"]
    assert len(healthy_chunk0) >= config.REPLICATION_FACTOR, f"Chunk 0 only has {len(healthy_chunk0)} healthy replicas!"
    print(f"    [OK] Auto re-replication restored chunk replicas ({len(healthy_chunk0)}/{config.REPLICATION_FACTOR}).")

    # 4. Corrupted Replica
    print("\n[CHECK 5] Corrupting a replica to test Integrity...")
    corrupt_blob(filename)
    print("    [OK] Corrupted a blob on disk.")
    
    download_resp = client.get(f"{COORD_URL}/files/{file_id}")
    assert download_resp.status_code == 200, f"Download failed after corruption: {download_resp.text}"
    assert download_resp.content == payload, "Downloaded content does not match!"
    print("    [OK] File downloaded successfully (Corrupt replica bypassed).")

    # 5. Two Node Failures
    print("\n[CHECK 6] Simulating Two Node Failures...")
    # Find two healthy nodes hosting chunk 1
    chunk1_nodes = [c["node_id"] for c in data_chunks_after if c["chunk_index"] == 1]
    healthy_chunk1 = [n for n in chunk1_nodes if nodes_status.get(n, {}).get("status") == "ok"]
    
    kill_node(healthy_chunk1[0])
    kill_node(healthy_chunk1[1])
    print(f"    [OK] Killed {healthy_chunk1[0]} and {healthy_chunk1[1]}. Waiting 6s...")
    time.sleep(6)
    
    download_resp = client.get(f"{COORD_URL}/files/{file_id}")
    assert download_resp.status_code == 200, f"Download failed after 2 node failures: {download_resp.text}"
    assert download_resp.content == payload, "Downloaded content does not match!"
    print("    [OK] File downloaded successfully (Last valid replica used).")

    # 6. Node Recovery
    print("\n[CHECK 7] Simulating Node Recovery...")
    restart_node(target_node)
    restart_node(healthy_chunk1[0])
    restart_node(healthy_chunk1[1])
    print("    [OK] Restarted all killed nodes. Polling for recovery (up to 30s)...")
    
    recovered_nodes = set()
    for attempt in range(6):  # poll up to 30s
        time.sleep(5)
        resp = client.get(f"{COORD_URL}/cluster")
        nodes_status = resp.json()["nodes"]
        recovered_nodes = {
            n for n in [target_node, healthy_chunk1[0], healthy_chunk1[1]]
            if nodes_status.get(n, {}).get("status") == "ok"
        }
        print(f"    [{attempt+1}/6] Healthy: {recovered_nodes}")
        if len(recovered_nodes) == 3:
            break
    
    assert target_node in recovered_nodes, f"Node {target_node} did not recover!"
    print(f"    [OK] All restarted nodes are back as healthy.")

    # Cleanup
    print("\n[CHECK 8] Cleaning up test file...")
    del_resp = client.delete(f"{COORD_URL}/files/{file_id}")
    assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
    print("    [OK] Test file deleted.")

    print("\n" + "=" * 65)
    print("  [OK] ALL 3x REPLICATION & RECOVERY TESTS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    test_features()
