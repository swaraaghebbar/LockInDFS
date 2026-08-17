"""
Metadata database for the coordinator (SQLite).

Stores the mapping:  file  →  ordered list of chunks  →  which node holds each chunk.

## Schema

files
  id          TEXT PK   – SHA-256 of the *entire original file* (content-address)
  filename    TEXT       – original filename from the upload
  size        INTEGER    – total file size in bytes
  chunk_size  INTEGER    – chunk size used when splitting (bytes)
  total_chunks INTEGER   – how many chunks the file was split into
  is_compressed INTEGER  – whether the file was compressed before encryption
  is_deleted  INTEGER    – soft-delete flag for GC
  wrapped_dek BLOB       – wrapped data encryption key
  owner_id    TEXT       – user who uploaded the file (FK → users.id)
  created_at  TEXT       – ISO-8601 timestamp
  last_accessed TEXT     – ISO-8601 timestamp

chunks
  id          INTEGER PK AUTOINCREMENT
  file_id     TEXT FK    – references files.id
  chunk_index INTEGER    – 0-based position in the file
  chunk_hash  TEXT       – SHA-256 of this individual chunk
  node_id     TEXT       – which storage node holds this chunk
  UNIQUE(file_id, chunk_index, node_id)

users
  id          TEXT PK    – stable Google sub (subject) ID
  email       TEXT UNIQUE
  name        TEXT
  picture     TEXT       – Google profile picture URL
  created_at  TEXT
  last_login  TEXT

sessions
  token       TEXT PK    – opaque session token
  user_id     TEXT FK    – references users.id
  created_at  TEXT
  expires_at  TEXT

Why separate tables?
In later phases a single chunk may be replicated to multiple nodes, producing
multiple rows in `chunks` with different `node_id` values but the same
`file_id + chunk_index + chunk_hash`.
"""

import aiosqlite
import os
from datetime import datetime, timezone


DB_PATH = os.path.join(os.path.dirname(__file__), "metadata.db")


def _connect():
    """Return a connection with row-factory set to dict-like access."""
    # Note: caller must await this or use async with
    return aiosqlite.connect(DB_PATH)


async def init_db():
    """Create tables if they don't exist.  Safe to call on every startup."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                name TEXT,
                picture TEXT,
                created_at TEXT,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT,
                expires_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT,
                size INTEGER,
                chunk_size INTEGER,
                total_chunks INTEGER,
                is_compressed INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                wrapped_dek BLOB,
                owner_id TEXT DEFAULT '__legacy__',
                created_at TEXT,
                last_accessed TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT REFERENCES files(id) ON DELETE CASCADE,
                chunk_index INTEGER,
                chunk_hash TEXT,
                node_id TEXT,
                UNIQUE(file_id, chunk_index, node_id)
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash);
            
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                address TEXT,
                device_id TEXT,
                tier TEXT,
                state TEXT,
                free_bytes INTEGER,
                blob_count INTEGER,
                last_heartbeat TEXT,
                updated_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS scrub_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_hash TEXT,
                node_id TEXT,
                result TEXT,
                scanned_at TEXT,
                repaired_at TEXT
            );
        """)
        
        # ── Migrations for existing databases ────────────────────────────────
        _migrations = [
            ("files", "is_compressed", "ALTER TABLE files ADD COLUMN is_compressed INTEGER DEFAULT 0"),
            ("files", "is_deleted", "ALTER TABLE files ADD COLUMN is_deleted INTEGER DEFAULT 0"),
            ("files", "wrapped_dek", "ALTER TABLE files ADD COLUMN wrapped_dek BLOB"),
            ("files", "owner_id", "ALTER TABLE files ADD COLUMN owner_id TEXT DEFAULT '__legacy__'"),
            ("chunks", "checksum_verified_at", "ALTER TABLE chunks ADD COLUMN checksum_verified_at TEXT"),
            ("chunks", "status", "ALTER TABLE chunks ADD COLUMN status TEXT"),
        ]
        for _table, _col, _sql in _migrations:
            try:
                await conn.execute(_sql)
            except aiosqlite.OperationalError:
                pass  # Column already exists

        # Backfill last_accessed for files that don't have it
        try:
            await conn.execute("ALTER TABLE files ADD COLUMN last_accessed TEXT")
            await conn.execute("UPDATE files SET last_accessed = created_at WHERE last_accessed IS NULL")
        except aiosqlite.OperationalError:
            pass

        # Backfill owner_id for legacy files
        await conn.execute("UPDATE files SET owner_id = '__legacy__' WHERE owner_id IS NULL")
            
        await conn.commit()


# ── User operations ──────────────────────────────────────────────────────────

async def upsert_user(user_id: str, email: str, name: str, picture: str) -> dict:
    """Create or update a user from Google OAuth data. Returns the user dict."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            """
            INSERT INTO users (id, email, name, picture, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                picture = excluded.picture,
                last_login = excluded.last_login
            """,
            (user_id, email, name, picture, now, now),
        )
        await conn.commit()
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}


async def get_user(user_id: str) -> dict | None:
    """Return user by ID or None."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_email(email: str) -> dict | None:
    """Return user by email or None."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users WHERE email = ?", (email,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_all_users() -> list[dict]:
    """Return all users ordered by creation date."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_user_storage_usage(user_id: str) -> int:
    """Return total bytes used by a user's non-deleted files."""
    async with _connect() as conn:
        async with conn.execute(
            "SELECT COALESCE(SUM(size), 0) FROM files WHERE owner_id = ? AND is_deleted = 0",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def list_all_users_with_usage() -> list[dict]:
    """Return all users with their storage usage."""
    users = await list_all_users()
    result = []
    for u in users:
        usage = await get_user_storage_usage(u["id"])
        u["storage_used"] = usage
        result.append(u)
    return result


# ── Session operations ───────────────────────────────────────────────────────

async def create_session(token: str, user_id: str, expires_at: str) -> None:
    """Create a new session."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, expires_at),
        )
        await conn.commit()


async def get_session(token: str) -> dict | None:
    """Return session by token or None."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_session(token: str) -> None:
    """Delete a session (logout)."""
    async with _connect() as conn:
        await conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await conn.commit()


async def cleanup_expired_sessions() -> int:
    """Delete all expired sessions. Returns count deleted."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        cur = await conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        await conn.commit()
        return cur.rowcount


# ── Write operations ─────────────────────────────────────────────────────────

async def insert_file(
    file_id: str,
    filename: str,
    size: int,
    chunk_size: int,
    total_chunks: int,
    is_compressed: bool = False,
    wrapped_dek: bytes = None,
    owner_id: str = "__legacy__",
) -> None:
    """Record a new file upload."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO files (id, filename, size, chunk_size, total_chunks, is_compressed, wrapped_dek, owner_id, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, filename, size, chunk_size, total_chunks, int(is_compressed), wrapped_dek, owner_id, now, now),
        )
        await conn.commit()


async def update_wrapped_dek(file_id: str, wrapped_dek: bytes) -> None:
    """Update wrapped dek for existing file."""
    async with _connect() as conn:
        await conn.execute("UPDATE files SET wrapped_dek = ? WHERE id = ?", (wrapped_dek, file_id))
        await conn.commit()


async def update_last_accessed(file_id: str) -> None:
    """Update the last_accessed timestamp to now."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute("UPDATE files SET last_accessed = ? WHERE id = ?", (now, file_id))
        await conn.commit()


async def insert_chunk(file_id: str, chunk_index: int,
                 chunk_hash: str, node_id: str) -> None:
    """Record that a specific chunk lives on a specific node."""
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO chunks (file_id, chunk_index, chunk_hash, node_id) "
            "VALUES (?, ?, ?, ?)",
            (file_id, chunk_index, chunk_hash, node_id),
        )
        await conn.commit()

async def insert_file_and_chunks(
    file_id: str, filename: str, size: int, chunk_size: int, total_chunks: int,
    is_compressed: bool, wrapped_dek: bytes, chunk_records: list,
    owner_id: str = "__legacy__",
) -> None:
    """Insert file and multiple chunk records in a single transaction."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO files (id, filename, size, chunk_size, total_chunks, is_compressed, wrapped_dek, owner_id, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, filename, size, chunk_size, total_chunks, int(is_compressed), wrapped_dek, owner_id, now, now),
        )
        for idx, chunk_hash, node_id in chunk_records:
            await conn.execute(
                "INSERT INTO chunks (file_id, chunk_index, chunk_hash, node_id) VALUES (?, ?, ?, ?)",
                (file_id, idx, chunk_hash, node_id)
            )
        await conn.commit()


async def upsert_node(node_id: str, address: str, device_id: str, tier: str, state: str, free_bytes: int, blob_count: int) -> None:
    """Upsert node status."""
    now = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, address, device_id, tier, state, free_bytes, blob_count, last_heartbeat, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                address = excluded.address,
                device_id = excluded.device_id,
                tier = excluded.tier,
                state = excluded.state,
                free_bytes = excluded.free_bytes,
                blob_count = excluded.blob_count,
                last_heartbeat = excluded.last_heartbeat,
                updated_at = excluded.updated_at
            """,
            (node_id, address, device_id, tier, state, free_bytes, blob_count, now, now)
        )
        await conn.commit()

# ── Read operations ──────────────────────────────────────────────────────────

async def get_file(file_id: str) -> dict | None:
    """Return file metadata or None."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_chunks(file_id: str) -> list[dict]:
    """Return all chunks for a file, ordered by chunk_index."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index", (file_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_chunks() -> list[dict]:
    """Return all chunk records in the database."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM chunks") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def list_files() -> list[dict]:
    """Return all non-deleted files in the database."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM files WHERE is_deleted = 0 ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def list_files_for_user(owner_id: str) -> list[dict]:
    """Return all non-deleted files owned by a specific user."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM files WHERE is_deleted = 0 AND owner_id = ? ORDER BY created_at DESC",
            (owner_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_nodes() -> list[dict]:
    """Return all nodes from the nodes table."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM nodes") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
            
async def get_node(node_id: str) -> dict | None:
    """Return node by ID."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

# ── Delete operations ────────────────────────────────────────────────────────

async def delete_file(file_id: str) -> bool:
    """Hard delete a file and its chunks (cascade)."""
    async with _connect() as conn:
        cursor = await conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def soft_delete_file(file_id: str) -> bool:
    """Mark a file as deleted for GC processing."""
    async with _connect() as conn:
        cursor = await conn.execute("UPDATE files SET is_deleted = 1 WHERE id = ?", (file_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def get_deleted_files() -> list[str]:
    """Return a list of file IDs marked as deleted."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT id FROM files WHERE is_deleted = 1") as cursor:
            rows = await cursor.fetchall()
            return [r["id"] for r in rows]


async def delete_chunk_replica(file_id: str, chunk_index: int, node_id: str) -> bool:
    """Remove a specific replica record from the DB."""
    async with _connect() as conn:
        cursor = await conn.execute(
            "DELETE FROM chunks WHERE file_id = ? AND chunk_index = ? AND node_id = ?",
            (file_id, chunk_index, node_id)
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_chunk_locations(chunk_hash: str) -> list[str]:
    """Return a list of unique node_ids that currently hold this chunk_hash."""
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT DISTINCT node_id FROM chunks WHERE chunk_hash = ?", (chunk_hash,)) as cursor:
            rows = await cursor.fetchall()
            return [r["node_id"] for r in rows]


async def get_chunk_reference_count(chunk_hash: str) -> int:
    """Return how many distinct file_ids reference this chunk_hash."""
    async with _connect() as conn:
        async with conn.execute("SELECT COUNT(DISTINCT file_id) FROM chunks WHERE chunk_hash = ?", (chunk_hash,)) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_active_reference_count(chunk_hash: str) -> int:
    """Return how many non-deleted files reference this chunk_hash."""
    async with _connect() as conn:
        async with conn.execute(
            '''
            SELECT COUNT(DISTINCT chunks.file_id) 
            FROM chunks 
            JOIN files ON chunks.file_id = files.id 
            WHERE chunks.chunk_hash = ? AND files.is_deleted = 0
            ''',
            (chunk_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_node_chunk_reference_count(chunk_hash: str, node_id: str) -> int:
    """Return how many files (active or deleted) reference chunk_hash specifically on node_id."""
    async with _connect() as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_hash = ? AND node_id = ?",
            (chunk_hash, node_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]
