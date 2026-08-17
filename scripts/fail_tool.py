import argparse
import os
import json
import sqlite3
import random
import signal
import sys
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PID_FILE = os.path.join(ROOT, "scripts", ".pids.json")
DB_PATH = os.path.join(ROOT, "coordinator", "metadata.db")


def get_pids():
    if not os.path.exists(PID_FILE):
        return {}
    with open(PID_FILE) as f:
        return json.load(f)


def kill_node(node_name):
    pids = get_pids()
    pid = pids.get(node_name)
    if not pid:
        print(f"Error: Node {node_name} is not running or PID not found.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Successfully killed {node_name} (PID {pid}).")
    except Exception as e:
        print(f"Error killing {node_name}: {e}")


def corrupt_blob(filename):
    if not os.path.exists(DB_PATH):
        print("Error: Metadata database does not exist. Upload some files first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    file_row = conn.execute(
        "SELECT id, filename FROM files WHERE filename LIKE ? LIMIT 1",
        (f"%{filename}%",)
    ).fetchone()

    if not file_row:
        print(f"Error: No file found matching '{filename}'")
        conn.close()
        return

    file_id = file_row["id"]
    chunks = conn.execute(
        "SELECT chunk_hash, node_id FROM chunks WHERE file_id = ?",
        (file_id,)
    ).fetchall()

    if not chunks:
        print("Error: No chunks found for file.")
        conn.close()
        return

    # Corrupt a random chunk replica
    target = random.choice(chunks)
    chunk_hash = target["chunk_hash"]
    node_id = target["node_id"]

    blob_path = os.path.join(ROOT, "data", node_id, chunk_hash)
    if not os.path.exists(blob_path):
        print(f"Error: Physical blob path not found: {blob_path}")
        conn.close()
        return

    # Corrupt the file contents
    with open(blob_path, "r+b") as f:
        f.seek(0)
        f.write(b"BAD_DATA")

    print(f"Successfully corrupted chunk replica {chunk_hash[:12]} on {node_id}!")
    print("The node's background scrubber or coordinator verify-on-read will catch this.")
    conn.close()


def simulate_full_disk(node_name):
    # To simulate a full disk, we append a massive file to fill the directory,
    # or we can mock/patch the node's disk telemetry.
    # A cleaner programmatic way is writing a dummy file in the node's data path
    # or creating a flag file '.disk_full' that node health checks check.
    # Let's add a mechanism where if a file `.disk_full` exists in node's storage directory,
    # it reports 0 free space and returns 507 for any PUT.
    node_data_dir = os.path.join(ROOT, "data", node_name)
    os.makedirs(node_data_dir, exist_ok=True)
    flag_file = os.path.join(node_data_dir, ".disk_full")
    
    with open(flag_file, "w") as f:
        f.write("1")
    print(f"Simulating full disk on {node_name}. Flag file created at {flag_file}.")
    print("Node will now report 0 free space and reject writes with 507 Insufficient Storage.")


def clear_full_disk(node_name):
    flag_file = os.path.join(ROOT, "data", node_name, ".disk_full")
    if os.path.exists(flag_file):
        os.remove(flag_file)
        print(f"Cleared simulated full disk on {node_name}.")
    else:
        print(f"No simulated full disk flag found on {node_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DFS Failure Testing Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    kill_parser = subparsers.add_parser("kill", help="Kill a storage node process")
    kill_parser.add_argument("node", help="e.g. node1, node2")

    corrupt_parser = subparsers.add_parser("corrupt", help="Corrupt a chunk replica of a file")
    corrupt_parser.add_argument("filename", help="Filename substring to match")

    fill_parser = subparsers.add_parser("fill", help="Simulate a full disk on a node")
    fill_parser.add_argument("node", help="e.g. node1, node2")

    clear_parser = subparsers.add_parser("clear-full", help="Clear simulated full disk on a node")
    clear_parser.add_argument("node", help="e.g. node1, node2")

    args = parser.parse_args()

    if args.command == "kill":
        kill_node(args.node)
    elif args.command == "corrupt":
        corrupt_blob(args.filename)
    elif args.command == "fill":
        simulate_full_disk(args.node)
    elif args.command == "clear-full":
        clear_full_disk(args.node)
