"""
Coordinator – the single entry-point for clients.

## Metadata / Blob separation  (Phase 2 – key design concept)

The coordinator stores METADATA (which file → which chunks → which nodes)
in a local SQLite database.  The actual blob DATA lives on the storage nodes.

Why separate them?
  1. The coordinator never touches node filesystems directly – it only talks
     HTTP.  This means a node could be on a different machine and nothing
     changes (just swap 127.0.0.1 for its real IP in config.py).
  2. Metadata is tiny (a few KB per file) and fast to query.  Blobs can be
     huge and slow.  Keeping them apart
     lets us scale each concern independently.
  3. A single metadata DB gives us a global view of where every chunk lives,
     even though no individual node knows about any other node.

Think of it like a library catalogue vs. the actual bookshelves:
  - Catalogue (SQLite)  → "Book X, chapter 3 is on shelf node2"
  - Bookshelves (nodes) → store the actual pages, nothing more

## Multi-node chunk distribution  (Phase 2)

On upload the coordinator spreads chunks across all HEALTHY nodes using
round-robin.  Example with 5 chunks and 3 healthy nodes:

  chunk 0 → node1,  chunk 1 → node2,  chunk 2 → node3,
  chunk 3 → node1,  chunk 4 → node2

On download the coordinator reads the metadata DB to find out which node
holds each chunk, then fetches from the correct node.  Each node is
independent – it doesn't know (or care) that other nodes exist.

## End-to-end verification chain  (Phase 1, still active)

  1. COORDINATOR ON UPLOAD  – hashes each chunk and the whole file.
  2. NODE ON WRITE          – re-hashes, rejects on mismatch (transit error).
  3. NODE ON READ           – re-hashes, rejects on mismatch (bit-rot).
  4. COORDINATOR ON DOWNLOAD– re-hashes each chunk AND the reassembled file.

Endpoints:
  POST   /files          Upload a file  (chunk + distribute + record metadata)
  GET    /files/{id}     Download a file (fetch chunks + reassemble + verify)
  GET    /files          List all files
  DELETE /files/{id}     Delete a file and its chunks
  GET    /cluster        Cluster health overview
"""

import asyncio
import hashlib
import sys
import os
import random
import secrets

# Ensure project root is on the path so `config` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Cookie
from fastapi.responses import JSONResponse, Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta

import config
from config import (
    COORDINATOR_PORT, NODES, node_url, REPLICATION_FACTOR,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    SESSION_SECRET, ADMIN_EMAILS, USER_STORAGE_QUOTA_BYTES,
)
from coordinator import db
import crypto_utils

def _get_http_client(timeout: float = 10.0) -> httpx.AsyncClient:
    """Helper to return an httpx.AsyncClient with SSL verify=False for dev self-signed certs."""
    return httpx.AsyncClient(timeout=timeout, verify=False)


# ── App setup ────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    asyncio.create_task(heartbeat_loop())
    asyncio.create_task(self_healing_loop())
    asyncio.create_task(gc_loop())
    yield

app = FastAPI(title="DFS Coordinator", version="0.1.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth dependencies ────────────────────────────────────────────────────────

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SESSION_COOKIE = "dfs_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days


async def get_current_user(request: Request) -> dict | None:
    """Extract and validate the session cookie. Returns user dict or None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = await db.get_session(token)
    if not session:
        return None
    # Check expiry
    if session["expires_at"] < datetime.now(timezone.utc).isoformat():
        await db.delete_session(token)
        return None
    user = await db.get_user(session["user_id"])
    return user


async def require_user(request: Request) -> dict:
    """Dependency that requires an authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(request: Request) -> dict:
    """Dependency that requires an authenticated admin user."""
    user = await require_user(request)
    if user["email"] not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


import urllib.parse

@app.get("/auth/google")
async def auth_google_redirect():
    """Redirect browser to Google's consent screen."""
    if not GOOGLE_CLIENT_ID or GOOGLE_CLIENT_ID.strip() == "":
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID is not configured in .env file. Please populate GOOGLE_CLIENT_ID in .env and restart backend."
        )
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    qs = urllib.parse.urlencode(params)
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{qs}")


@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle Google redirect: exchange code for tokens, create session."""
    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            google_err = token_resp.text
            print(f"[!] Google token exchange failed ({token_resp.status_code}): {google_err}")
            raise HTTPException(
                status_code=502,
                detail=f"Google token exchange failed: {google_err}"
            )
        tokens = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to get user info from Google")
        userinfo = userinfo_resp.json()

    # Upsert user
    user = await db.upsert_user(
        user_id=userinfo["sub"],
        email=userinfo.get("email", ""),
        name=userinfo.get("name", ""),
        picture=userinfo.get("picture", ""),
    )

    # Create session
    session_token = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)).isoformat()
    await db.create_session(session_token, user["id"], expires_at)

    # Redirect to frontend with session cookie
    is_admin = user["email"] in ADMIN_EMAILS
    redirect_url = "/admin" if is_admin else "/dashboard"
    response = RedirectResponse(redirect_url, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/auth/me")
async def auth_me(user: dict = Depends(require_user)):
    """Return the current user's info."""
    is_admin = user["email"] in ADMIN_EMAILS
    usage = await db.get_user_storage_usage(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
        "is_admin": is_admin,
        "storage_used": usage,
        "storage_quota": USER_STORAGE_QUOTA_BYTES,
    }


@app.post("/auth/logout")
async def auth_logout(request: Request):
    """Clear the session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.delete_session(token)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ── Admin endpoints ──────────────────────────────────────────────────────────

@app.get("/admin/users")
async def admin_list_users(user: dict = Depends(require_admin)):
    """Return all users with storage usage (admin only)."""
    users = await db.list_all_users_with_usage()
    # Only expose safe fields
    return {
        "users": [
            {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "picture": u["picture"],
                "storage_used": u["storage_used"],
                "storage_quota": USER_STORAGE_QUOTA_BYTES,
                "created_at": u["created_at"],
                "last_login": u["last_login"],
            }
            for u in users
        ]
    }


# ── Global State ─────────────────────────────────────────────────────────────

# NODE_STATUS is now stored in the database

# ── In-Memory Metadata Cache ──────────────────────────────────────────────────

CACHE_TTL_SECONDS = 5.0  # entries expire after this many seconds

_meta_cache: dict = {}
_chunks_cache: dict = {}


def _cache_get(store: dict, key: str):
    """Return cached value if present and not expired, else None."""
    import time
    entry = store.get(key)
    if entry and time.monotonic() < entry[0]:
        return entry[1]
    store.pop(key, None)
    return None


def _cache_set(store: dict, key: str, value):
    """Store a value with a TTL expiry."""
    import time
    store[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)


def _cache_invalidate(file_id: str):
    """Remove a file_id from both caches (call on write/delete)."""
    _meta_cache.pop(file_id, None)
    _chunks_cache.pop(file_id, None)


# ── Background Tasks ─────────────────────────────────────────────────────────

async def heartbeat_loop():
    """
    Poll all nodes every 5 seconds to detect failures.
    Marks nodes as 'ok', 'unmounted', 'absent', or 'dead' in NODE_STATUS.
    Caches the full JSON payload (free_space, total_bytes, disk_total, etc).

    IMPORTANT — availability vs. failure:
      We respect the node's own status report and preserve the crucial
      distinction between a drive that needs repair and one that is simply
      not connected:
        * "ok"        – node reachable, storage mounted & usable.
        * "unmounted" – node reachable, drive PRESENT but not mounted.  This is
                        repairable; the node's own watchdog will ntfsfix+remount
                        it (or an operator can trigger POST /repair/{node_id}).
        * "absent"    – node reachable, drive NOT plugged in.  Nothing to
                        repair — we never route work here and never try to fix.
        * "dead"      – node process itself is unreachable (crashed/killed).
      We must NOT collapse "absent" into "unmounted": there is no point trying
      to repair a drive that isn't even plugged in.
    """
    async with _get_http_client(timeout=2.0) as client:
        while True:
            for node_id in NODES:
                try:
                    resp = await client.get(f"{node_url(node_id)}/health")
                    if resp.status_code == 200:
                        node_data = resp.json()
                        reported_status = node_data.get("status", "ok")
                        # Respect node's own status — don't override the drive
                        # states the node reports ("unmounted" / "absent").
                        curr_node = await db.get_node(node_id)
                        curr_status = curr_node.get("state") if curr_node else "unknown"
                        if reported_status in ("unmounted", "absent"):
                            if curr_status != reported_status:
                                if reported_status == "absent":
                                    print(f"Node {node_id} drive is ABSENT (not plugged in).")
                                else:
                                    print(f"Node {node_id} drive is UNMOUNTED (repairable).")
                            node_data["status"] = reported_status
                        else:
                            if curr_status != "ok":
                                print(f"Node {node_id} is online.")
                            node_data["status"] = "ok"
                        
                        await db.upsert_node(
                            node_id=node_id, 
                            address=node_data.get("address", ""), 
                            device_id=node_data.get("device_id", ""), 
                            tier=node_data.get("tier", ""), 
                            state=node_data.get("status"), 
                            free_bytes=node_data.get("free_space", 0), 
                            blob_count=node_data.get("blob_count", 0)
                        )
                    elif resp.status_code == 503:
                        detail = ""
                        try:
                            detail = str(resp.json().get("detail", ""))
                        except Exception:
                            detail = resp.text or ""
                        drive_state = "absent" if "ABSENT" in detail.upper() else "unmounted"
                        curr_node = await db.get_node(node_id)
                        curr_status = curr_node.get("state") if curr_node else "unknown"
                        if curr_status != drive_state:
                            print(f"Node {node_id} reports drive {drive_state} (503).")
                        await db.upsert_node(node_id, "", "", "", drive_state, 0, 0)
                    else:
                        curr_node = await db.get_node(node_id)
                        curr_status = curr_node.get("state") if curr_node else "unknown"
                        if curr_status == "ok":
                            print(f"[FAILURE] Node {node_id} returned {resp.status_code}. Marking dead.")
                        await db.upsert_node(node_id, "", "", "", "dead", 0, 0)
                except Exception:
                    curr_node = await db.get_node(node_id)
                    curr_status = curr_node.get("state") if curr_node else "unknown"
                    if curr_status in ("ok", "unmounted", "absent"):
                        print(f"[FAILURE] Node {node_id} heartbeat failed. Marking dead.")
                    await db.upsert_node(node_id, "", "", "", "dead", 0, 0)
            await asyncio.sleep(5)


async def self_healing_loop():
    """
    Scan the metadata DB every 10 seconds. Identify under-replicated chunks
    (where the number of HEALTHY replicas is < REPLICATION_FACTOR).
    Pull a replica from a healthy node and push it to a new healthy node.
    """
    await asyncio.sleep(6)
    
    async with _get_http_client(timeout=10.0) as client:
        while True:
            try:
                from collections import defaultdict
                chunks_by_logical = defaultdict(list)
                
                for chunk_rec in await db.get_all_chunks():
                    key = (chunk_rec["file_id"], chunk_rec["chunk_index"])
                    chunks_by_logical[key].append(chunk_rec)
                    
                for (file_id, chunk_idx), replicas in chunks_by_logical.items():
                    all_nodes = await db.get_all_nodes()
                    node_status_dict = {n["node_id"]: n.get("state") for n in all_nodes}
                    healthy_replicas = [r for r in replicas if node_status_dict.get(r["node_id"]) == "ok"]
                    dead_replicas = [r for r in replicas if node_status_dict.get(r["node_id"]) != "ok"]
                    
                    # 1. Trimming excess replicas
                    if len(healthy_replicas) > REPLICATION_FACTOR:
                        excess_count = len(healthy_replicas) - REPLICATION_FACTOR
                        # Sort by some stable criteria, e.g. node_id, to keep the first REPLICATION_FACTOR nodes
                        healthy_replicas_sorted = sorted(healthy_replicas, key=lambda r: r["node_id"])
                        to_remove = healthy_replicas_sorted[-excess_count:]
                        for r in to_remove:
                            await db.delete_chunk_replica(file_id, chunk_idx, r["node_id"])
                            print(f"[TRIM] Removed excess replica record for chunk {chunk_idx} on {r['node_id']}")
                        
                        # Update healthy_replicas list after trimming
                        healthy_replicas = healthy_replicas_sorted[:-excess_count]

                    if not healthy_replicas:
                        continue
                        
                    # 2. Repairing under-replicated chunks
                    if len(healthy_replicas) < REPLICATION_FACTOR:
                        missing = REPLICATION_FACTOR - len(healthy_replicas)
                        print(f"[REPAIR] chunk {chunk_idx} of {file_id[:8]} is under-replicated ({len(healthy_replicas)}/{REPLICATION_FACTOR}). Repairing...")
                        
                        used_nodes = {r["node_id"] for r in replicas}
                        all_healthy = [n["node_id"] for n in all_nodes if n.get("state") == "ok"]
                        available_targets = [n for n in all_healthy if n not in used_nodes]
                        
                        if not available_targets:
                            continue
                            
                        target_nodes = _select_replica_nodes(available_targets, missing)
                        
                        source = healthy_replicas[0]
                        chunk_hash = source["chunk_hash"]
                        source_url = node_url(source["node_id"])
                        
                        try:
                            resp = await client.get(f"{source_url}/blob/{chunk_hash}")
                            if resp.status_code == 200:
                                chunk_data = resp.content
                                if _sha256(chunk_data) == chunk_hash:
                                    for target in target_nodes:
                                        target_url = node_url(target)
                                        print(f"[REPAIR] copying chunk {chunk_idx} {source['node_id']} -> {target}")
                                        push_resp = await client.put(f"{target_url}/blob/{chunk_hash}", content=chunk_data)
                                        if push_resp.status_code in (200, 201):
                                            await db.insert_chunk(file_id, chunk_idx, chunk_hash, target)
                                            print(f"[REPAIR] replication restored ({len(healthy_replicas) + 1}/{REPLICATION_FACTOR})")
                                            healthy_replicas.append({"node_id": target, "chunk_hash": chunk_hash}) # Optimistic update
                        except Exception as e:
                            print(f"[REPAIR] error on chunk {chunk_idx}: {e}")
                            
            except Exception as e:
                print(f"Self-healing loop encountered error: {e}")
                
            await asyncio.sleep(10)


async def gc_loop():
    """
    Background garbage collector.
    Finds softly deleted files, physically deletes their unshared chunks, 
    and hard deletes the metadata.
    """
    await asyncio.sleep(10)
    
    async with _get_http_client(timeout=5.0) as client:
        while True:
            deleted_files = await db.get_deleted_files()
            for file_id in deleted_files:
                chunk_records = await db.get_chunks(file_id)
                all_success = True
                
                for chunk_rec in chunk_records:
                    chunk_hash = chunk_rec["chunk_hash"]
                    node_id = chunk_rec["node_id"]
                    chunk_index = chunk_rec["chunk_index"]
                    
                    active_refs = await db.get_active_reference_count(chunk_hash)
                    if active_refs == 0:
                        base_url = node_url(node_id)
                        try:
                            resp = await client.delete(f"{base_url}/blob/{chunk_hash}")
                            if resp.status_code in (200, 404):
                                await db.delete_chunk_replica(file_id, chunk_index, node_id)
                            else:
                                print(f"[GC] Warning: Node {node_id} rejected delete ({resp.status_code})")
                                all_success = False
                        except Exception as e:
                            print(f"[GC] Warning: Unreachable node {node_id} during delete ({e})")
                            all_success = False
                    else:
                        await db.delete_chunk_replica(file_id, chunk_index, node_id)
                
                remaining_chunks = await db.get_chunks(file_id)
                if not remaining_chunks and all_success:
                    await db.delete_file(file_id)
                    print(f"[*] GC permanently reclaimed file {file_id[:12]}")
                    
            await asyncio.sleep(10)





# ── Helpers ──────────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    """Compute the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _split_into_3_chunks(data: bytes) -> list[bytes]:
    """Split data into 3 parts (chunks)."""
    if len(data) == 0:
        return [b"", b"", b""]
    chunk_size = max(1, (len(data) + 2) // 3)
    chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
    while len(chunks) < 3:
        chunks.append(b"")
    return chunks[:3]


async def repair_chunk(target_node_id: str, chunk_hash: str):
    """
    Self-repair a corrupted chunk on a specific node.
    Downloads the chunk from a healthy replica and pushes it to the target node.
    """
    print(f"[*] Starting repair for chunk {chunk_hash} on {target_node_id}")
    existing_nodes = await db.get_chunk_locations(chunk_hash)
    all_nodes = await db.get_all_nodes()
    node_status_dict = {n["node_id"]: n.get("state") for n in all_nodes}
    healthy_sources = [
        n for n in existing_nodes 
        if n != target_node_id and node_status_dict.get(n) == "ok"
    ]
    
    if not healthy_sources:
        print(f"[!] Cannot repair {chunk_hash} on {target_node_id}: no healthy replicas available.")
        return
        
    source_node = healthy_sources[0]
    print(f"[*] Fetching healthy chunk from {source_node}...")
    
    async with _get_http_client(timeout=10.0) as client:
        try:
            resp = await client.get(f"{node_url(source_node)}/blob/{chunk_hash}")
            if resp.status_code != 200:
                print(f"[!] Repair failed: source {source_node} returned {resp.status_code}")
                return
                
            chunk_data = resp.content
            if _sha256(chunk_data) != chunk_hash:
                print(f"[!] Repair failed: source {source_node} returned corrupted data!")
                return
                
            target_url = node_url(target_node_id)
            print(f"[*] Pushing repaired chunk to {target_node_id}...")
            put_resp = await client.put(f"{target_url}/blob/{chunk_hash}", content=chunk_data)
            
            if put_resp.status_code in (200, 201):
                print(f"[*] Successfully repaired chunk {chunk_hash} on {target_node_id}")
            else:
                print(f"[!] Repair failed: target {target_node_id} rejected the chunk ({put_resp.status_code})")
                
        except Exception as e:
            print(f"[!] Repair process failed with error: {e}")


async def _get_healthy_nodes() -> list[str]:
    """Return a list of nodes currently marked 'ok' by the heartbeat loop."""
    nodes = await db.get_all_nodes()
    return [n["node_id"] for n in nodes if n.get("state") == "ok"]


def _select_replica_nodes(healthy_nodes: list[str], count: int, exclude_nodes: set[str] = None) -> list[str]:
    """Select up to `count` healthy nodes dynamically and reasonably balanced."""
    if exclude_nodes is None:
        exclude_nodes = set()
    candidates = [n for n in healthy_nodes if n not in exclude_nodes]
    random.shuffle(candidates)
    if len(candidates) < count:
        for n in healthy_nodes:
            if n not in candidates and len(candidates) < count:
                candidates.append(n)
    return candidates[:count]



# ── Parallel chunk helpers ───────────────────────────────────────────────────

async def _store_chunk(client, file_hash, idx, chunk_data, chunk_hash, healthy_nodes):
    """Store a single chunk (with replicas) on the cluster based on free storage space."""
    existing_nodes = await db.get_chunk_locations(chunk_hash)
    if existing_nodes:
        for target_node in existing_nodes:
            await db.insert_chunk(file_hash, idx, chunk_hash, target_node)
        return {
            "index": idx,
            "hash": chunk_hash,
            "size": len(chunk_data),
            "nodes": existing_nodes,
        }

    target_nodes = _select_replica_nodes(healthy_nodes, REPLICATION_FACTOR)

    chunk_replicas = []
    tried_nodes = set()

    for target_node in target_nodes:
        tried_nodes.add(target_node)
        base_url = node_url(target_node)
        try:
            resp = await client.put(f"{base_url}/blob/{chunk_hash}", content=chunk_data)
            if resp.status_code in (200, 201):
                await db.insert_chunk(file_hash, idx, chunk_hash, target_node)
                chunk_replicas.append(target_node)
            elif resp.status_code == 507:
                print(f"[DEGRADED] Node {target_node} is full (507), skipping for chunk {idx}")
            else:
                print(f"[DEGRADED] Node {target_node} rejected chunk {idx} ({resp.status_code})")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            print(f"[DEGRADED] Node {target_node} unreachable for chunk {idx}: {type(e).__name__}")
        except Exception as e:
            print(f"[DEGRADED] Node {target_node} error for chunk {idx}: {e}")

    if len(chunk_replicas) < REPLICATION_FACTOR:
        fallback_nodes = [n for n in healthy_nodes if n not in tried_nodes]
        for fb_node in fallback_nodes:
            if len(chunk_replicas) >= REPLICATION_FACTOR:
                break
            try:
                resp = await client.put(f"{node_url(fb_node)}/blob/{chunk_hash}", content=chunk_data)
                if resp.status_code in (200, 201):
                    await db.insert_chunk(file_hash, idx, chunk_hash, fb_node)
                    chunk_replicas.append(fb_node)
                    print(f"[DEGRADED] Fallback: stored chunk {idx} on {fb_node}")
                elif resp.status_code == 507:
                    print(f"[DEGRADED] Fallback node {fb_node} also full")
            except Exception:
                pass

    if not chunk_replicas:
        raise RuntimeError(f"Failed to store chunk {idx} on ANY node")

    return {
        "index": idx,
        "hash": chunk_hash,
        "size": len(chunk_data),
        "nodes": chunk_replicas,
    }


async def _fetch_chunk(client, idx, replicas):
    """Fetch a single chunk from the cluster, trying replicas round-robin."""
    if not replicas:
        raise RuntimeError(f"Missing all replicas for chunk {idx}")

    chunk_hash = replicas[0]["chunk_hash"]

    all_nodes = await db.get_all_nodes()
    node_dict = {n["node_id"]: n for n in all_nodes}
    
    # Sort replicas by total_bytes, but prioritize active healthy nodes ('ok') over offline/unmounted nodes
    def _node_sort_key(r):
        nd = node_dict.get(r["node_id"], {})
        st = nd.get("state", "dead")
        is_ok = 0 if st == "ok" else 1
        return (is_ok, nd.get("free_bytes", float("inf"))) # using free_bytes as fallback approximation

    replicas_sorted = sorted(replicas, key=_node_sort_key)

    for chunk_rec in replicas_sorted:
        node_id = chunk_rec["node_id"]
        # Skip node if currently marked unmounted/dead unless no other option
        nd = node_dict.get(node_id, {})
        st = nd.get("state", "unknown")
        if st not in ("ok", "unknown"):
            print(f"[DEGRADED] Skipping node {node_id} for chunk {idx} (status: {st})")
            continue

        base_url = node_url(node_id)
        try:
            resp = await client.get(f"{base_url}/blob/{chunk_hash}")
            if resp.status_code == 200:
                computed_hash = _sha256(resp.content)
                if computed_hash == chunk_hash:
                    return resp.content
                else:
                    print(f"[DEGRADED] Integrity failure from {node_id} on chunk {idx}, trying next replica")
            else:
                print(f"[DEGRADED] Node {node_id} returned {resp.status_code} for chunk {idx}")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            print(f"[DEGRADED] Node {node_id} unreachable for chunk {idx}: {type(e).__name__}")
        except Exception as e:
            print(f"[DEGRADED] Error fetching chunk {idx} from {node_id}: {e}")

    raise RuntimeError(f"Failed to fetch chunk {idx} (hash {chunk_hash}) from any replica")


# ── File operations ──────────────────────────────────────────────────────────

async def _get_file_bytes(file_id: str) -> tuple[bytes, dict]:
    """Helper to fetch, decrypt, decompress and verify file bytes. Returns (bytes, file_meta)."""
    file_meta = _cache_get(_meta_cache, file_id)
    if file_meta is None:
        file_meta = await db.get_file(file_id)
        if file_meta:
            _cache_set(_meta_cache, file_id, file_meta)

    if not file_meta or file_meta.get("is_deleted"):
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    await db.update_last_accessed(file_id)
    _cache_invalidate(file_id)

    chunk_records = _cache_get(_chunks_cache, file_id)
    if chunk_records is None:
        chunk_records = await db.get_chunks(file_id)
        if chunk_records:
            _cache_set(_chunks_cache, file_id, chunk_records)

    if not chunk_records:
        raise HTTPException(
            status_code=500,
            detail=f"File {file_id} exists in metadata but has no chunks"
        )

    wrapped_dek = file_meta.get("wrapped_dek")
    file_dek = crypto_utils.unwrap_dek(wrapped_dek) if wrapped_dek else None

    from collections import defaultdict
    chunks_by_index = defaultdict(list)
    for chunk_rec in chunk_records:
        if chunk_rec["chunk_index"] >= 0:
            chunks_by_index[chunk_rec["chunk_index"]].append(chunk_rec)

    async with _get_http_client(timeout=5.0) as client:
        tasks = [
            _fetch_chunk(client, idx, chunks_by_index.get(idx, []))
            for idx in range(file_meta["total_chunks"])
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    reassembled = bytearray()
    for idx, result in enumerate(raw_results):
        if isinstance(result, Exception):
            raise HTTPException(status_code=502, detail=str(result))
        
        ciphertext_chunk = result
        decrypted_payload = None
        if file_dek:
            try:
                decrypted_payload = crypto_utils.decrypt_chunk(ciphertext_chunk, file_dek)
            except Exception:
                pass

        if decrypted_payload is None:
            raise HTTPException(status_code=500, detail=f"Decryption failed for chunk {idx}: Invalid key or corrupt ciphertext")

        if file_meta.get("is_compressed"):
            import gzip
            chunk_data = gzip.decompress(decrypted_payload)
        else:
            chunk_data = decrypted_payload

        reassembled.extend(chunk_data)

    reassembled_bytes = bytes(reassembled)
    reassembled_hash = _sha256(reassembled_bytes)

    if reassembled_hash != file_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Full-file integrity failure: expected {file_id}, "
                f"got {reassembled_hash}. "
                "Plaintext hash mismatch after decryption."
            ),
        )

    return reassembled_bytes, file_meta


@app.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    """
    Upload a file with multi-layer encryption, 3-part chunking, quota enforcement, and node replication.
    """
    import math
    contents = await file.read()
    file_size = len(contents)

    # Check per-user storage quota
    user_usage = await db.get_user_storage_usage(user["id"])
    if user_usage + file_size > USER_STORAGE_QUOTA_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Storage quota exceeded. Used: {user_usage} B, Uploading: {file_size} B, Quota: {USER_STORAGE_QUOTA_BYTES} B",
        )

    file_hash = _sha256(contents)

    existing_file = await db.get_file(file_hash)
    if existing_file:
        if not existing_file.get("wrapped_dek"):
            file_dek = crypto_utils.derive_convergent_key(contents) if config.USE_CONVERGENT_ENCRYPTION else crypto_utils.generate_dek()
            wrapped_dek = crypto_utils.wrap_dek(file_dek)
            await db.update_wrapped_dek(file_hash, wrapped_dek)
            _cache_invalidate(file_hash)
        return JSONResponse(
            status_code=200,
            content={
                "file_id": file_hash,
                "message": "File already exists (content-addressed dedup)",
            },
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    is_compressed = ext not in (".jpg", ".jpeg", ".mp4", ".zip", ".gz", ".png")
    chunks_raw = _split_into_3_chunks(contents)

    if config.USE_CONVERGENT_ENCRYPTION:
        file_dek = crypto_utils.derive_convergent_key(contents)
    else:
        file_dek = crypto_utils.generate_dek()

    wrapped_dek = crypto_utils.wrap_dek(file_dek)

    healthy_nodes = await _get_healthy_nodes()
    if not healthy_nodes:
        raise HTTPException(status_code=503, detail="No storage nodes are available")

    # Order of Operations: COMPRESS -> ENCRYPT -> HASH CIPHERTEXT
    prepared_chunks = []
    for idx, chunk_plaintext in enumerate(chunks_raw):
        if is_compressed:
            import gzip
            data_to_encrypt = gzip.compress(chunk_plaintext, mtime=0)
        else:
            data_to_encrypt = chunk_plaintext

        chunk_key = file_dek

        ciphertext_chunk = crypto_utils.encrypt_chunk(
            data_to_encrypt, chunk_key, deterministic_nonce=config.USE_CONVERGENT_ENCRYPTION
        )

        chunk_ciphertext_hash = _sha256(ciphertext_chunk)
        prepared_chunks.append((idx, ciphertext_chunk, chunk_ciphertext_hash))

    chunk_part_size = math.ceil(file_size / 3) if file_size > 0 else 0
    await db.insert_file(
        file_id=file_hash,
        filename=file.filename or "unnamed",
        size=file_size,
        chunk_size=chunk_part_size,
        total_chunks=len(chunks_raw),
        is_compressed=is_compressed,
        wrapped_dek=wrapped_dek,
        owner_id=user["id"],
    )

    async with _get_http_client(timeout=10.0) as client:
        tasks = [
            _store_chunk(client, file_hash, idx, chunk_data, chunk_hash, healthy_nodes)
            for idx, chunk_data, chunk_hash in prepared_chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    chunk_manifest = []
    for (idx, chunk_data, chunk_hash), result in zip(prepared_chunks, results):
        if isinstance(result, Exception):
            await db.delete_file(file_hash)
            raise HTTPException(status_code=502, detail=str(result))
        chunk_manifest.append(result)

    _cache_invalidate(file_hash)

    return {
        "file_id": file_hash,
        "filename": file.filename,
        "size": file_size,
        "total_chunks": len(chunks_raw),
        "chunk_size": chunk_part_size,
        "chunks": chunk_manifest,
    }


@app.get("/files/{file_id}")
async def get_file(
    file_id: str,
    user: dict = Depends(require_user),
):
    """
    Download a file: fetch ciphertext chunks, decrypt, decompress, verify end-to-end.
    """
    reassembled_bytes, file_meta = await _get_file_bytes(file_id)

    # Ownership check: Admin can access any file; users can only access their own (or legacy)
    is_admin = user["email"] in ADMIN_EMAILS
    if not is_admin and file_meta["owner_id"] not in (user["id"], "__legacy__"):
        raise HTTPException(status_code=403, detail="Access denied")

    filename = file_meta["filename"]
    return Response(
        content=reassembled_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/files/{file_id}/preview")
async def preview_file(
    file_id: str,
    user: dict = Depends(require_user),
):
    """
    Inline preview endpoint: streams file with appropriate Content-Type for browser rendering.
    """
    import mimetypes
    reassembled_bytes, file_meta = await _get_file_bytes(file_id)

    is_admin = user["email"] in ADMIN_EMAILS
    if not is_admin and file_meta["owner_id"] not in (user["id"], "__legacy__"):
        raise HTTPException(status_code=403, detail="Access denied")

    filename = file_meta["filename"]
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "text/plain" if filename.endswith((".md", ".json", ".js", ".py", ".css", ".html", ".log", ".txt", ".csv")) else "application/octet-stream"

    return Response(
        content=reassembled_bytes,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/files")
async def list_files(user: dict = Depends(require_user)):
    """List stored files for the current user (admins see all files)."""
    is_admin = user["email"] in ADMIN_EMAILS
    if is_admin:
        files = await db.list_files()
    else:
        files = await db.list_files_for_user(user["id"])

    enriched_files = []
    for f in files:
        f_dict = dict(f)
        f_dict.pop("wrapped_dek", None)
        chunks = await db.get_chunks(f["id"])
        f_dict["nodes"] = list({c["node_id"] for c in chunks})
        enriched_files.append(f_dict)
    return {"files": enriched_files, "count": len(enriched_files)}


@app.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user: dict = Depends(require_user),
):
    """
    Delete a file: Marks it as deleted (soft delete).
    A background GC will physically reclaim the space later.
    """
    file_meta = await db.get_file(file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    is_admin = user["email"] in ADMIN_EMAILS
    if not is_admin and file_meta["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await db.soft_delete_file(file_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to mark file as deleted")

    _cache_invalidate(file_id)

    return {
        "status": "soft_deleted (pending GC)",
        "file_id": file_id,
        "filename": file_meta["filename"]
    }


class CorruptionReport(BaseModel):
    node_id: str
    chunk_hash: str


@app.post("/report-corruption")
async def report_corruption(report: CorruptionReport):
    """
    Storage nodes call this endpoint when their background scrubber detects
    a corrupted blob. The coordinator will immediately trigger a repair.
    """
    print(f"[!] Node {report.node_id} reported corruption in {report.chunk_hash}")
    # Spawn the repair process in the background so we don't block the node
    asyncio.create_task(repair_chunk(report.node_id, report.chunk_hash))
    return {"status": "repair_initiated"}


# ── Drive mount repair (removable NTFS nodes) ────────────────────────────────

@app.post("/repair/{node_id}")
async def repair_node_mount(node_id: str):
    """
    Ask a node to repair (ntfsfix + remount) its removable drive.

    Strict separation is preserved: the coordinator NEVER touches a node's
    filesystem directly.  It only proxies an HTTP request to the node's own
    /repair-mount endpoint, and the node does the actual ntfsfix/mount locally.

    The endpoint refuses fast for drives that are ABSENT (not plugged in) or for
    a node whose process is unreachable — you cannot repair what isn't there.
    """
    if node_id not in NODES:
        raise HTTPException(status_code=404, detail=f"Unknown node {node_id}")

    node_rec = await db.get_node(node_id)
    status = node_rec.get("state", "unknown") if node_rec else "unknown"
    if status == "absent":
        return JSONResponse(
            status_code=409,
            content={
                "node_id": node_id,
                "success": False,
                "state_before": "absent",
                "message": "drive is not plugged in (absent) — nothing to repair",
            },
        )
    if status == "dead":
        return JSONResponse(
            status_code=502,
            content={
                "node_id": node_id,
                "success": False,
                "message": "node process is unreachable (dead) — cannot repair remotely",
            },
        )

    async with _get_http_client(timeout=200.0) as client:
        try:
            resp = await client.post(f"{node_url(node_id)}/repair-mount")
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Repair request to {node_id} failed: {e}")


@app.post("/repair")
async def repair_all_mounts():
    """
    Trigger a repair on every node currently reporting a repairable
    ('unmounted') drive.  ABSENT and healthy nodes are skipped.
    """
    all_nodes = await db.get_all_nodes()
    targets = [n["node_id"] for n in all_nodes if n.get("state") == "unmounted"]
    results = {}

    async with _get_http_client(timeout=200.0) as client:
        async def _repair(n: str):
            try:
                resp = await client.post(f"{node_url(n)}/repair-mount")
                results[n] = resp.json()
            except Exception as e:
                results[n] = {"success": False, "message": f"request failed: {e}"}

        await asyncio.gather(*[_repair(n) for n in targets])

    return {
        "attempted": targets,
        "skipped_absent": [n["node_id"] for n in all_nodes if n.get("state") == "absent"],
        "results": results,
    }


# ── Cluster overview ─────────────────────────────────────────────────────────

@app.get("/cluster")
async def cluster_overview():
    """
    Query every node's /health endpoint and report cluster status.
    """
    cluster = {}

    async with _get_http_client(timeout=3.0) as client:
        for node_id in NODES:
            base_url = node_url(node_id)
            try:
                resp = await client.get(f"{base_url}/health")
                cluster[node_id] = resp.json()
            except Exception as e:
                cluster[node_id] = {"status": "unreachable", "error": str(e)}

    return {"nodes": cluster}



# ── Run directly ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "coordinator.main:app", host="0.0.0.0",
        port=COORDINATOR_PORT, reload=True,
    )
