"""
Drive availability detection & NTFS auto-repair for storage nodes.

## Why this module exists

Removable NTFS drives (the SanDisk pendrive and the Tag HDD) get yanked out or
lose power without a clean unmount.  When they come back, the kernel refuses to
mount them and you see the classic pair of errors:

    $MFTMirr does not match $MFT (record 3)
    Failed to mount '/dev/sda2': Input/output error

The fix a human runs by hand is always the same two commands:

    sudo ntfsfix /dev/sda2
    sudo mount -t ntfs-3g /dev/sda2 /media/pi/Tag_Node_1

This module automates exactly that — but *only* when it is safe to do so.

## The distinction that actually matters (READ THIS)

There is a world of difference between a drive that is **plugged in but not
mounted** and a drive that is **simply not plugged in**:

  * PRESENT + NOT MOUNTED  → the filesystem is probably corrupt.  Repair it.
  * NOT PRESENT AT ALL     → nothing is wrong that we can fix.  Running
                             `ntfsfix` here is pointless at best and, if we
                             guessed a device name like `/dev/sda2`, actively
                             DANGEROUS — that name may now belong to a totally
                             different disk after a replug.

So this module classifies every node into one of three states:

  * ``MOUNTED``   ("ok")        – storage is live and usable.
  * ``UNMOUNTED`` ("unmounted") – backing device IS present but not mounted.
                                  **This is the only repairable state.**
  * ``ABSENT``    ("absent")    – backing device is NOT present (unplugged).
                                  We never attempt a repair in this state.

We identify the backing device by its stable filesystem **UUID or LABEL**
(via ``/dev/disk/by-uuid`` / ``/dev/disk/by-label``), never by a bare
``/dev/sdaN`` name, precisely so we can never ntfsfix the wrong disk.

## Platform behaviour

All real device/mount/repair logic is Linux-only (this runs on the Pi).  On a
Windows/macOS dev box the module degrades to a plain "does the directory
exist?" check so the app keeps working while you develop.
"""

from __future__ import annotations

import os
import stat
import sys
import subprocess

# ── Node storage states ──────────────────────────────────────────────────────
# The string values are the exact status strings reported over HTTP, so they
# stay backwards-compatible with the coordinator/frontend which already know
# about "ok" and "unmounted".  "absent" is the new, important third state.
MOUNTED = "ok"          # storage path is an active mount (usable)
UNMOUNTED = "unmounted"  # device present but not mounted  -> REPAIRABLE
ABSENT = "absent"        # device not present (unplugged)  -> NOT repairable

IS_LINUX = sys.platform.startswith("linux")


# ── Low-level helpers ────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """
    Run *cmd* and return ``(returncode, stdout, stderr)``.

    Never raises: a missing binary, a timeout, or any other failure is folded
    into a non-zero return code so callers can stay linear and log cleanly.
    """
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError as e:
        return 127, "", f"command not found: {e}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", str(e)


def _is_block_device(path: str) -> bool:
    """True iff *path* exists and is a block device node (e.g. /dev/sda2)."""
    try:
        return stat.S_ISBLK(os.stat(path).st_mode)
    except OSError:
        return False


def _label_candidates(cfg: dict) -> list[str]:
    """
    Ordered list of filesystem labels to try when resolving a device.

    An explicit ``fs_label`` wins; otherwise we fall back to the mount-point
    basename, because udisks auto-mounts removable media at
    ``/media/pi/<LABEL>`` — so the basename usually *is* the label.
    """
    candidates: list[str] = []
    label = cfg.get("fs_label")
    if label:
        candidates.append(str(label))
    mount_point = str(cfg.get("storage_path", ""))
    base = os.path.basename(mount_point.rstrip("/"))
    if base and base not in candidates:
        candidates.append(base)
    return candidates


def _blkid_device_for_label(label: str) -> str | None:
    """Ask blkid for the device that currently holds filesystem *label*."""
    rc, out, _ = _run(["blkid", "-L", label], timeout=10)
    if rc == 0 and out:
        return out.strip()
    return None


# ── Device resolution ────────────────────────────────────────────────────────

def resolve_device(cfg: dict) -> str | None:
    """
    Return the block-device path that backs this node, or ``None`` if the
    device is not currently present.

    Resolution is deliberately ordered most-stable-first so that we address a
    *specific filesystem*, not a volatile ``/dev/sdaN`` slot:

      1. ``fs_uuid``  -> /dev/disk/by-uuid/<uuid>     (most robust; survives replug)
      2. ``fs_label`` -> /dev/disk/by-label/<label>   (robust; survives replug)
      3. mount-point basename as a label                (udisks convention)
      4. blkid scan by label                            (metadata still readable)
      5. explicit ``device`` path, only if it is really a block device

    Returning ``None`` is the signal for "ABSENT — do not repair".  We would
    rather report ABSENT than guess and risk repairing the wrong disk.
    """
    if not IS_LINUX:
        return None

    # 1) by UUID — the single most reliable handle on a filesystem
    uuid = cfg.get("fs_uuid")
    if uuid:
        by_uuid = f"/dev/disk/by-uuid/{uuid}"
        if os.path.exists(by_uuid):
            return os.path.realpath(by_uuid)

    # 2) + 3) by label (explicit, then derived from the mount-point basename)
    for label in _label_candidates(cfg):
        by_label = f"/dev/disk/by-label/{label}"
        if os.path.exists(by_label):
            return os.path.realpath(by_label)

    # 4) last-ditch: ask blkid directly (works while FS metadata is readable)
    for label in _label_candidates(cfg):
        dev = _blkid_device_for_label(label)
        if dev and _is_block_device(dev):
            return dev

    # 5) explicit device override — only honoured if it's genuinely present.
    #    This is the fragile option (device names reorder on replug) so it is
    #    intentionally LAST and never used unless the operator opted in.
    dev = cfg.get("device")
    if dev and _is_block_device(str(dev)):
        return str(dev)

    return None


def _device_is_mounted(device: str) -> bool:
    """True iff *device* is mounted anywhere on the system."""
    return bool(_device_mount_targets(device))


def _device_mount_targets(device: str) -> list[str]:
    """Return every mount point currently backed by *device*.

    A block device can be mounted more than once.  That is normally useful,
    but it is not valid for a storage node: every extra mount is shown as
    another copy of the volume in the file manager.  ``findmnt`` gives us the
    kernel's authoritative list, rather than relying on stale UI entries.
    """
    rc, out, _ = _run(["findmnt", "-r", "-n", "-S", device, "-o", "TARGET"], timeout=10)
    if rc != 0 or not out:
        return []
    return [target.strip() for target in out.splitlines() if target.strip()]


def _unmount_duplicate_targets(cfg: dict, device: str, mount_point: str,
                               sudo: list[str], result: dict, logger=print) -> bool:
    """Unmount every existing mount of *device* except the configured target.

    Returns ``False`` if an old copy cannot be unmounted (for example, it is
    busy).  In that situation we deliberately do not create another copy.
    """
    expected = os.path.realpath(mount_point)
    stale_targets = [
        target for target in _device_mount_targets(device)
        if os.path.realpath(target) != expected
    ]
    for target in stale_targets:
        cmd = sudo + ["umount", target]
        rc, out, err = _run(cmd, timeout=60)
        result["steps"].append({"cmd": " ".join(cmd), "rc": rc, "out": out, "err": err})
        logger(f"[{result['node_id']}] removing duplicate mount {target} -> rc={rc} {err}".rstrip())
        if rc != 0:
            result["state_after"] = classify(cfg)
            result["message"] = (f"could not remove duplicate mount at {target} "
                                 f"(rc={rc}): {err or out}; no new mount was created")
            return False
    return True


def is_mounted(cfg: dict, device: str | None = None) -> bool:
    """True iff the expected filesystem is mounted at this node's path.

    For removable nodes, ``os.path.ismount`` alone is not sufficient: another
    USB volume could be mounted at the same directory. Compare the mount source
    with the resolved expected device before declaring the node healthy.
    """
    mount_point = str(cfg.get("storage_path", ""))
    if not mount_point:
        return False
    try:
        if not os.path.ismount(mount_point):
            return False
    except OSError:
        return False

    if not (IS_LINUX and cfg.get("removable", False)):
        return True

    expected = device or resolve_device(cfg)
    if not expected:
        return False
    rc, source, _ = _run(["findmnt", "-n", "-T", mount_point, "-o", "SOURCE"], timeout=10)
    return rc == 0 and bool(source) and os.path.realpath(source) == os.path.realpath(expected)


# ── State classification ─────────────────────────────────────────────────────

def classify(cfg: dict) -> str:
    """
    Return ``MOUNTED`` / ``UNMOUNTED`` / ``ABSENT`` for a node.

    * Removable node on Linux — the real logic:
        - mounted                     -> MOUNTED
        - not mounted, device present -> UNMOUNTED  (repairable)
        - not mounted, device absent  -> ABSENT     (not plugged in)

    * Non-removable node (Pi root-FS dirs like ``/Pi_Node_1``) or any non-Linux
      dev host — availability is just "does the directory exist?":
        - directory exists -> MOUNTED
        - directory missing -> ABSENT
    """
    removable = bool(cfg.get("removable", False))
    mount_point = str(cfg.get("storage_path", ""))

    if IS_LINUX and removable:
        device = resolve_device(cfg)
        if device is None:
            return ABSENT
        return MOUNTED if is_mounted(cfg, device) else UNMOUNTED

    # Non-removable / dev-mode fallback.
    return MOUNTED if os.path.isdir(mount_point) else ABSENT


def describe(cfg: dict) -> dict:
    """
    A small status snapshot for a node's ``/health`` payload.

    ``repairable`` is the field the UI/coordinator should key off to decide
    whether offering (or attempting) a repair even makes sense.
    """
    state = classify(cfg)
    return {
        "state": state,
        "mounted": state == MOUNTED,
        "present": state in (MOUNTED, UNMOUNTED),
        "repairable": state == UNMOUNTED,
        "removable": bool(cfg.get("removable", False)),
        "device": resolve_device(cfg) if (IS_LINUX and cfg.get("removable")) else None,
        "fs_type": cfg.get("fs_type", "ntfs-3g"),
    }


# ── Repair ───────────────────────────────────────────────────────────────────

def attempt_repair(cfg: dict, node_id: str = "?", logger=print,
                   use_sudo: bool = True) -> dict:
    """
    Repair and remount a node whose drive is PRESENT but UNMOUNTED.

    Runs the same recipe a human would:  ``ntfsfix <dev>`` then
    ``mount -t <fstype> <dev> <mountpoint>``.  Returns a structured result and
    **never raises** — every failure mode is captured in the returned dict.

    ### Safety guarantees
    * If the node is already ``MOUNTED`` → no-op success.
    * If the node is ``ABSENT`` (device not plugged in) → we refuse, because
      there is nothing to repair and guessing a device could damage the wrong
      disk.  This is the core requirement of the whole feature.
    * If the device cannot be resolved to a specific filesystem → we refuse
      rather than run ntfsfix on a guess.
    * ``ntfsfix`` only runs for NTFS filesystems.
    * ``sudo -n`` is used (non-interactive) so a missing sudoers rule fails
      fast with a clear message instead of hanging on a password prompt.
    """
    result = {
        "node_id": node_id,
        "attempted": False,
        "success": False,
        "state_before": None,
        "state_after": None,
        "device": None,
        "steps": [],
        "message": "",
    }

    state_before = classify(cfg)
    result["state_before"] = state_before

    if state_before == MOUNTED:
        result["success"] = True
        result["state_after"] = MOUNTED
        result["message"] = "already mounted; nothing to repair"
        return result

    if state_before == ABSENT:
        # The whole point of this feature: do NOT repair an unplugged drive.
        result["state_after"] = ABSENT
        result["message"] = ("device not present (not plugged in) — repair "
                             "skipped by design")
        logger(f"[{node_id}] ABSENT — not plugged in; skipping repair.")
        return result

    if not IS_LINUX:
        result["state_after"] = state_before
        result["message"] = "repair is only supported on Linux (the Pi)"
        return result

    # state_before == UNMOUNTED, and the device is present.
    device = resolve_device(cfg)
    result["device"] = device
    if not device:
        result["state_after"] = classify(cfg)
        result["message"] = ("could not resolve the backing device to a "
                             "specific filesystem; refusing to guess so we "
                             "never ntfsfix the wrong disk")
        logger(f"[{node_id}] UNMOUNTED but device unresolved — refusing to guess.")
        return result

    mount_point = str(cfg.get("storage_path", ""))
    fs_type = str(cfg.get("fs_type", "ntfs-3g"))
    sudo = ["sudo", "-n"] if use_sudo else []

    # Reconcile mounts before mounting again. A previous auto-mount/manual
    # mount may already have attached this device at another path, which is
    # exactly what creates repeated volume entries in the file manager.
    was_mounted_elsewhere = _device_is_mounted(device)
    if was_mounted_elsewhere:
        if not _unmount_duplicate_targets(cfg, device, mount_point, sudo, result, logger):
            return result
        if is_mounted(cfg, device):
            result["success"] = True
            result["state_after"] = MOUNTED
            result["message"] = f"removed duplicate mounts; {device} is mounted at {mount_point}"
            return result

    logger(f"[{node_id}] UNMOUNTED, device present at {device} — repairing...")

    # 1) ntfsfix — fixes the "$MFTMirr does not match $MFT" corruption.
    result["attempted"] = True
    if not was_mounted_elsewhere and "ntfs" in fs_type:
        cmd = sudo + ["ntfsfix", device]
        rc, out, err = _run(cmd, timeout=180)
        result["steps"].append({"cmd": " ".join(cmd), "rc": rc, "out": out, "err": err})
        logger(f"[{node_id}] ntfsfix {device} -> rc={rc} {out} {err}".rstrip())
        if rc != 0:
            result["state_after"] = classify(cfg)
            hint = ""
            if rc == 1 and ("sudo" in err.lower() or "password" in err.lower()):
                hint = " (passwordless sudo for ntfsfix not configured — see README)"
            result["message"] = f"ntfsfix failed (rc={rc}): {err or out}{hint}"
            return result

    # 2) Make sure the mount point exists (udisks may have removed it on unplug).
    cmd = sudo + ["mkdir", "-p", mount_point]
    rc, out, err = _run(cmd, timeout=30)
    result["steps"].append({"cmd": " ".join(cmd), "rc": rc, "out": out, "err": err})

    # 3) Mount it back at the expected path.
    cmd = sudo + ["mount", "-t", fs_type, device, mount_point]
    rc, out, err = _run(cmd, timeout=60)
    result["steps"].append({"cmd": " ".join(cmd), "rc": rc, "out": out, "err": err})
    logger(f"[{node_id}] mount {device} {mount_point} -> rc={rc} {err}".rstrip())

    state_after = classify(cfg)
    result["state_after"] = state_after
    result["success"] = state_after == MOUNTED
    if result["success"]:
        result["message"] = f"repaired and remounted {device} at {mount_point}"
    else:
        hint = ""
        if rc != 0 and ("sudo" in err.lower() or "password" in err.lower()):
            hint = " (passwordless sudo for mount not configured — see README)"
        result["message"] = f"mount did not take (rc={rc}): {err or out}{hint}"
    return result


def summarize_repair(result: dict) -> dict:
    """A compact, JSON-friendly summary suitable for /health `last_repair`."""
    return {
        "attempted": result.get("attempted"),
        "success": result.get("success"),
        "state_before": result.get("state_before"),
        "state_after": result.get("state_after"),
        "device": result.get("device"),
        "message": result.get("message"),
    }
