# DFS — Distributed File System (Educational Project)

A content-addressed, fault-tolerant distributed file system designed as a hands-on learning project. The system simulates a multi-node cluster running on a single host (e.g., Raspberry Pi partitions) using isolated FastAPI servers communicating exclusively via HTTP.

---

## 1. System Architecture

```
                       ┌──────────────┐
              Client ─►│ Coordinator  │ :8000
                       └──────┬───────┘
                              │
             ┌────────────────┼────────────────┐
             ▼ (HTTP)         ▼ (HTTP)         ▼ (HTTP)
        ┌─────────┐      ┌─────────┐      ┌─────────┐
        │Pi_Node_1│ :8001│Sandisk1 │ :8003│Tag_Node1│ :8005
        │ (Replica│      │ (USB)   │      │ (HDD)   │
        │ double- │      └─────────┘      └─────────┘
        │ encrypt)│      ┌─────────┐      ┌─────────┐
        └─────────┘      │Sandisk2 │ :8004│Tag_Node2│ :8006
        ┌─────────┐      │ (USB)   │      │ (HDD)   │
        │Pi_Node_2│ :8002└─────────┘      └─────────┘
        └─────────┘
```

- **Coordinator (Port 8000):** The single entry point for clients. It manages global metadata in SQLite (`metadata.db`), tracks chunk mappings, evaluates cluster telemetry, and coordinates writes, reads, self-healing, and garbage collection.
- **Storage Nodes (Ports 8001-8007):** Independent FastAPI processes. They know nothing about other nodes or the coordinator. They expose simple endpoints to `PUT`, `GET`, and `DELETE` content-addressed blobs, and report status/telemetry via `/health`.
- **Strict Separation Rule:** The coordinator talks to nodes *only* over HTTP. Nodes never access the coordinator's database, and the coordinator never reads/writes directly to node storage directories.

---

## 2. Distributed Systems Concepts Implemented

### A. Content-Addressable Storage (CAS) & 3-Part Chunking
Files are split into 3 chunks on upload. Each chunk is identified by its SHA-256 hash. If two files share identical chunks, they point to the exact same physical blob.
- **Deduplication:** Uploading the same data twice yields zero storage growth. Reference counts in metadata track usage.
- **Compression:** Transparent chunk compression using gzip (with deterministic `mtime=0` for hash stability).

### B. Pi_Node_1 Replica & Double Encryption
Every uploaded file triggers a full-file replica store on `Pi_Node_1` with an additional layer of AES-256-GCM encryption (double encryption) for dedicated backup and enhanced security.

### C. Storage-Based Chunk Placement & Replication
Chunks are placed on healthy storage nodes sorted by available free disk space (`free_space`). Each chunk is replicated to $N=3$ different nodes.

### D. Heartbeats & Failure Detection
The coordinator polls `/health` on all registered nodes every 5 seconds. If a node fails to respond, it is marked as `dead`/`unreachable`, and the coordinator stops routing new writes or reads to it.

### E. Self-Healing & Re-replication
A background thread periodically scans metadata. If the number of healthy replicas for any chunk falls below $N=3$ (due to a dead node), the coordinator fetches the chunk from a surviving healthy replica and re-replicates it to another healthy node.

### F. Load Balancing & Telemetry Routing
- **Writes:** Chunks are placed on healthy nodes sorted by free disk space.
- **Reads:** Downloads fetch chunks from replicas sorted by the least current total load (total bytes stored) to avoid hotspots.

### G. Background Integrity Scrubbing & Self-Repair
- **Scrubbing:** Every 10 seconds, each node runs a background sweep that re-computes the SHA-256 hash of its local blobs and compares it against their filename.
- **Self-Repair:** If corruption (bit-rot) is detected, the node deletes the corrupted blob and calls `/report-corruption` on the coordinator. The coordinator immediately repairs the node by pushing a fresh copy from a healthy replica.

### H. Garbage Collection
- **Soft Delete:** Deleting a file marks it `is_deleted = 1` in the database and returns immediately.
- **Asynchronous GC:** A background sweep periodically finds deleted files, checks if their chunks have an active reference count of 0, physically deletes unreferenced blobs from storage nodes, and then hard-deletes the metadata.

### I. Graceful Degradation & Parallelism
- **Parallelism:** All chunk uploads/downloads execute concurrently via `asyncio.gather()`.
- **Degradation:** Uploads/downloads continue working even if nodes fail or drives fill up (`507 Insufficient Storage`). If storage nodes are down, the coordinator can recover the file from the double-encrypted backup replica on `Pi_Node_1`.

### J. Removable-drive mount recovery
Each removable NTFS node is independently classified as `ok` (the expected filesystem is mounted), `unmounted` (that filesystem is present but not mounted), or `absent` (it is not connected). Only `unmounted` nodes are automatically repaired with `ntfsfix` and remounted; an absent drive is never guessed at or repaired.

Before enabling this on the Pi, set the real `fs_uuid` value for every removable node in `config.py` using `sudo blkid`. UUIDs remain stable when `/dev/sdaN` names change after reconnecting a drive. The node service account also needs passwordless access to only `ntfsfix`, `mkdir`, `mount`, and `umount`, because repair commands run as `sudo -n` and deliberately never prompt for a password.

---


## 3. Quick Start & Setup

1. **Virtual Environment & Dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

2. **Launch the Cluster:**
   ```bash
   python scripts/launch.py
   ```

3. **Start the Frontend Dashboard:**
   ```bash
   cd frontend
   npm run dev
   # Open http://localhost:5173
   ```

4. **Stop the Cluster:**
   ```bash
   python scripts/launch.py --stop
   ```

---

## 4. Failure Testing & Demos

We provide a dedicated CLI tool `scripts/fail_tool.py` to simulate failures and demonstrate the resilience of the system.

### Demo 1: Heartbeats & Self-Healing
1. Upload a file:
   ```bash
   curl -F "file=@README.md" http://127.0.0.1:8000/files
   ```
2. Kill a node process:
   ```bash
   python scripts/fail_tool.py kill node1
   ```
3. Watch the dashboard at `http://localhost:5173` (or poll `GET /cluster`). The node status changes to `unreachable`.
4. In about 10 seconds, check the logs or database. You will see self-healing kick in, removing dead replica references and recreating the missing replica on a healthy node.

### Demo 2: Bit-rot Detection & Self-Repair
1. Upload a file.
2. Intentionally corrupt one of its chunk replicas on disk:
   ```bash
   # Matches the uploaded filename, finds a chunk on disk, and overwrites bytes
   python scripts/fail_tool.py corrupt README.md
   ```
3. Wait up to 10 seconds. The node's background scrubber will detect the hash mismatch, delete the file, and notify the coordinator.
4. The coordinator downloads a good replica copy and repairs the block. Verify the file downloads with perfect integrity:
   ```bash
   curl http://127.0.0.1:8000/files/<file_id>
   ```

### Demo 3: Graceful Degradation (Disk Full & Offline Nodes)
1. Simulate a full drive on `node3`:
   ```bash
   python scripts/fail_tool.py fill node3
   ```
2. Kill `node2`:
   ```bash
   python scripts/fail_tool.py kill node2
   ```
3. Perform a file upload. The coordinator logs `[DEGRADED]` warning messages but successfully routes the writes to the remaining healthy, non-full nodes.
4. Clear the simulated full disk when done:
   ```bash
   python scripts/fail_tool.py clear-full node3
   ```
