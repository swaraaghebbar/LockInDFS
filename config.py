"""
Shared configuration for the distributed file system.

Node topology:
  - Pi partition A    → COORDINATOR          (port 8000)
  - Pi partition B    → Pi_Node_1            (port 8001)
  - Pi partition C    → Pi_Node_2            (port 8002)
  - SanDisk USB 1     → Sandisk_Node_1       (port 8003)
  - SanDisk USB 2     → Sandisk_Node_2       (port 8004)
  - Tag HDD part 1    → Tag_Node_1           (port 8005)
  - Tag HDD part 2    → Tag_Node_2           (port 8006)
  - Tag HDD part 3    → Tag_Node_3           (port 8007)

Update STORAGE_PATH values to real mount-points on your Pi.
On dev machines the paths are created as local directories.
"""

from pathlib import Path

COORDINATOR_PORT = 8000
COORDINATOR_HOST = "127.0.0.1"

# Every uploaded file is divided into exactly this many distributed chunks.
UPLOAD_CHUNK_COUNT = 3

# Number of copies to maintain per chunk (for automatic replication/failover).
REPLICATION_FACTOR = 3


# ── Per-node repair metadata ─────────────────────────────────────────────────
# Extra fields that drive the drive-availability detection and NTFS auto-repair
# subsystem (see mount_manager.py):
#
#   removable  True for drives that can be physically unplugged (USB pendrive,
#              external HDD).  Only removable drives can be ABSENT and only
#              removable drives are ever auto-repaired.  The Pi's own SSD
#              partitions live on the root filesystem and are never removable.
#   fs_type    Filesystem to mount with (default "ntfs-3g" for removable NTFS).
#   fs_label   Volume label used to locate the device via /dev/disk/by-label.
#              If omitted, the mount-point basename is used (udisks auto-mounts
#              removable media at /media/pi/<LABEL>, so the basename IS the label).
#   fs_uuid    (Recommended) Filesystem UUID for the most robust device lookup
#              via /dev/disk/by-uuid.  Survives replug/reordering.  Populate it
#              once per drive with:   sudo blkid
#   device     (Optional, discouraged) Explicit /dev/sdaN override.  Only used
#              as a LAST resort because kernel device names reorder on replug —
#              exactly why we never guess one for ntfsfix.

NODES = {
    "Pi_Node_1": {
        "host": "127.0.0.1",
        "port": 8001,
        "storage_path": Path("/Pi_Node_1"),
        "description": "Pi partition A",
        "removable": False,          # on the Pi root FS — cannot be unplugged
    },
    "Pi_Node_2": {
        "host": "127.0.0.1",
        "port": 8002,
        "storage_path": Path("/Pi_Node_2"),
        "description": "Pi partition B",
        "removable": False,
    },
    "Sandisk_Node_1": {
        "host": "127.0.0.1",
        "port": 8003,
        "storage_path": Path("/media/pi/SanDisk_Node1"),
        "description": "SanDisk Pendrive Partition 1",
        "removable": True,
        "fs_type": "ntfs-3g",
        "fs_label": "SanDisk_Node1",
        "fs_uuid": "2C36260A3625D61C", 
    },
    "Sandisk_Node_2": {
        "host": "127.0.0.1",
        "port": 8004,
        "storage_path": Path("/media/pi/SanDisk_Node2"),
        "description": "SanDisk Pendrive Partition 2",
        "removable": True,
        "fs_type": "ntfs-3g",
        "fs_label": "SanDisk_Node2",
        "fs_uuid": "0EC67064C6704E49",
    },
    "Tag_Node_1": {
        "host": "127.0.0.1",
        "port": 8005,
        "storage_path": Path("/media/pi/Tag_Node_1"),
        "description": "Tag HDD Partition 1",
        "removable": True,
        "fs_type": "ntfs-3g",
        "fs_label": "Tag_Node_1",
        "fs_uuid": None,
        # "device": "/dev/sda2",     # observed slot — left as a hint only, not used
    },
    "Tag_Node_2": {
        "host": "127.0.0.1",
        "port": 8006,
        "storage_path": Path("/media/pi/Tag_Node_2"),
        "description": "Tag HDD Partition 2",
        "removable": True,
        "fs_type": "ntfs-3g",
        "fs_label": "Tag_Node_2",
        "fs_uuid": None,
        # "device": "/dev/sda3",     # observed slot — left as a hint only, not used
    },
    "Tag_Node_3": {
        "host": "127.0.0.1",
        "port": 8007,
        "storage_path": Path("/media/pi/Tag_Node_3"),
        "description": "Tag HDD Partition 3",
        "removable": True,
        "fs_type": "ntfs-3g",
        "fs_label": "Tag_Node_3",
        "fs_uuid": None,
        # "device": "/dev/sda5",     # observed slot — left as a hint only, not used
    },
}


# Phase 13 Encryption Settings
USE_TLS = True
USE_CONVERGENT_ENCRYPTION = True

# ── Google OAuth 2.0 ──────────────────────────────────────────────────────────
import os as _os

def _load_env_file():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k:
                            _os.environ[k] = v
        except Exception as e:
            print(f"[!] Warning: failed to parse .env file: {e}")

_load_env_file()

GOOGLE_CLIENT_ID = _os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = _os.environ.get(
    "GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback"
)

# Secret key for signing session tokens (generate with: python -c "import secrets; print(secrets.token_hex(32))")
SESSION_SECRET = _os.environ.get(
    "SESSION_SECRET", "CHANGE_ME_IN_PRODUCTION_generate_a_random_hex_string"
)

# Comma-separated list of email addresses that get admin access
ADMIN_EMAILS = [
    e.strip()
    for e in _os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]

# Per-user storage quota in bytes (default 1 GB)
USER_STORAGE_QUOTA_BYTES = int(
    _os.environ.get("USER_STORAGE_QUOTA_BYTES", str(1 * 1024 * 1024 * 1024))
)

# ── Drive auto-repair settings (removable NTFS nodes) ─────────────────────────
# Each node process runs a small watchdog that detects when its removable drive
# is PRESENT-but-UNMOUNTED (the tell-tale sign of NTFS corruption after an
# unclean unplug) and automatically runs `ntfsfix` + `mount` to bring it back.
# A drive that is simply ABSENT (unplugged) is left alone — never repaired.
AUTO_REPAIR_ENABLED = True            # master switch for the node watchdog
AUTO_REPAIR_INTERVAL_SECONDS = 15     # how often each node re-checks its drive
AUTO_REPAIR_COOLDOWN_SECONDS = 60     # min gap between repair attempts per node
REPAIR_USE_SUDO = True                # prepend `sudo -n` to ntfsfix/mount
                                      # (requires passwordless sudo — see README)

def scheme() -> str:
    return "https" if USE_TLS else "http"

def node_url(node_id: str) -> str:
    """Return the base URL for a storage node."""
    n = NODES[node_id]
    return f"{scheme()}://{n['host']}:{n['port']}"
