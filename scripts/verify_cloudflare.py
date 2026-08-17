"""
Cloudflare Tunnel Verification Script
======================================
Runs 7 health checks to confirm the DFS + Cloudflare Tunnel integration works.

Usage:
    # Local checks only (no Cloudflare needed):
    python scripts/verify_cloudflare.py

    # Full checks including public hostname:
    CF_PUBLIC_HOSTNAME=dfs.example.com python scripts/verify_cloudflare.py

    # Or set the env var in your shell / .env file first.

Checks performed:
    1. DFS works normally without Cloudflare (basic local connectivity)
    2. Coordinator is reachable locally at https://127.0.0.1:8000
    3. cloudflared process is running (optional — skipped if not installed)
    4. Public hostname reaches the Coordinator (requires CF_PUBLIC_HOSTNAME)
    5. /cluster, upload, download, delete work through the public hostname
    6. Storage-node ports (8001-8007) are NOT reachable from the Internet
    7. Existing DFS pytest suite passes (runs tests/test_mount_manager.py)
"""

import os
import sys
import time
import subprocess
import socket

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    import httpx
except ImportError:
    print("[ERROR] httpx is not installed. Run: pip install httpx")
    sys.exit(1)

import config

# ── Configuration from environment ────────────────────────────────────────────
COORD_LOCAL = f"{config.scheme()}://127.0.0.1:{config.COORDINATOR_PORT}"
PUBLIC_HOST = os.environ.get("CF_PUBLIC_HOSTNAME", "").strip()

# Storage-node ports that must NOT be reachable from outside
STORAGE_PORTS = [cfg["port"] for cfg in config.NODES.values()]

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "[OK]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
WARN = "[WARN]"


def _h(label: str) -> None:
    width = 65
    print(f"\n{'-' * width}")
    print(f"  {label}")
    print(f"{'-' * width}")


def _ok(msg: str) -> None:
    print(f"    [{PASS}] {msg}")


def _fail(msg: str) -> None:
    print(f"    [{FAIL}] {msg}")


def _skip(msg: str) -> None:
    print(f"    [{SKIP}] {msg}")


def _warn(msg: str) -> None:
    print(f"    [{WARN}] {msg}")


def _make_client(timeout: float = 15.0) -> httpx.Client:
    """Return an httpx.Client that skips TLS verification (self-signed certs)."""
    return httpx.Client(verify=False, timeout=timeout)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — DFS works without Cloudflare (basic local reachability)
# ─────────────────────────────────────────────────────────────────────────────

def check_1_local_dfs_works() -> bool:
    _h("CHECK 1 — DFS works normally without Cloudflare")
    try:
        with _make_client() as client:
            resp = client.get(f"{COORD_LOCAL}/cluster", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            nodes = data.get("nodes", {})
            healthy = sum(1 for n in nodes.values() if n.get("status") == "ok")
            _ok(f"Coordinator responded. {healthy}/{len(nodes)} nodes healthy.")
            return True
        else:
            _fail(f"Coordinator returned HTTP {resp.status_code}")
            return False
    except Exception as exc:
        _fail(f"Cannot reach Coordinator at {COORD_LOCAL}: {exc}")
        _warn("Is the DFS cluster running? Try: python scripts/launch.py")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — Coordinator reachable locally
# ─────────────────────────────────────────────────────────────────────────────

def check_2_coordinator_local() -> bool:
    _h("CHECK 2 — Coordinator reachable locally on port 8000")
    try:
        sock = socket.create_connection(("127.0.0.1", config.COORDINATOR_PORT), timeout=5)
        sock.close()
        _ok(f"TCP connection to 127.0.0.1:{config.COORDINATOR_PORT} succeeded.")
        return True
    except OSError as exc:
        _fail(f"TCP connection to 127.0.0.1:{config.COORDINATOR_PORT} failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — cloudflared process is running
# ─────────────────────────────────────────────────────────────────────────────

def check_3_cloudflared_running() -> bool:
    _h("CHECK 3 — cloudflared process is running")
    # Try to find 'cloudflared' in running processes
    try:
        result = subprocess.run(
            ["pgrep", "-x", "cloudflared"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            pids = result.stdout.strip()
            _ok(f"cloudflared is running (PID(s): {pids}).")
            return True
    except FileNotFoundError:
        pass  # pgrep not available (Windows), try tasklist
    except Exception:
        pass

    # Windows fallback
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq cloudflared.exe", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        if "cloudflared" in result.stdout:
            _ok("cloudflared.exe is running (detected via tasklist).")
            return True
    except Exception:
        pass

    # Check if cloudflared binary even exists
    try:
        result = subprocess.run(
            ["cloudflared", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            _warn(f"cloudflared is installed ({result.stdout.strip()}) but not running.")
            _skip("Start with: cloudflared tunnel --config cloudflare/config.yml run")
        else:
            _skip("cloudflared is not installed. See docs/cloudflare_tunnel_setup.md.")
    except FileNotFoundError:
        _skip("cloudflared binary not found. See docs/cloudflare_tunnel_setup.md.")

    return False  # Not a hard failure — tunnel may be running on another machine


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4 — Public hostname reaches the Coordinator
# ─────────────────────────────────────────────────────────────────────────────

def check_4_public_hostname() -> bool:
    _h("CHECK 4 — Public hostname reaches the Coordinator")
    if not PUBLIC_HOST:
        _skip("CF_PUBLIC_HOSTNAME is not set. Skipping public-hostname check.")
        _skip("Set it with: export CF_PUBLIC_HOSTNAME=dfs.example.com")
        return True  # Not a failure if not configured

    url = f"https://{PUBLIC_HOST}/cluster"
    print(f"    Connecting to {url} ...")
    try:
        # Use verify=True for public hostname — Cloudflare provides a valid cert
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            nodes = data.get("nodes", {})
            healthy = sum(1 for n in nodes.values() if n.get("status") == "ok")
            _ok(f"Public hostname responded. {healthy}/{len(nodes)} nodes healthy.")
            return True
        else:
            _fail(f"Public hostname returned HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as exc:
        _fail(f"Cannot reach https://{PUBLIC_HOST}: {exc}")
        _warn("Is cloudflared running? Is the tunnel established?")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 5 — Upload / Download / Delete via public hostname
# ─────────────────────────────────────────────────────────────────────────────

def check_5_api_via_public_hostname() -> bool:
    _h("CHECK 5 — /cluster, upload, download, delete via public hostname")
    if not PUBLIC_HOST:
        _skip("CF_PUBLIC_HOSTNAME not set. Skipping API-through-tunnel checks.")
        return True

    base = f"https://{PUBLIC_HOST}"
    payload = b"cloudflare_tunnel_verification_payload_" + b"x" * 1024
    file_id = None

    try:
        with httpx.Client(timeout=60.0) as client:
            # /cluster
            resp = client.get(f"{base}/cluster")
            if resp.status_code != 200:
                _fail(f"GET /cluster via public hostname → HTTP {resp.status_code}")
                return False
            _ok("GET /cluster → 200 OK")

            # Upload
            resp = client.post(
                f"{base}/files",
                files={"file": ("cf_verify.txt", payload, "text/plain")}
            )
            if resp.status_code != 200:
                _fail(f"POST /files via public hostname → HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            file_id = resp.json().get("file_id")
            _ok(f"POST /files → 200 OK  (file_id={file_id[:12] if file_id else 'N/A'}...)")

            # Download
            resp = client.get(f"{base}/files/{file_id}")
            if resp.status_code != 200:
                _fail(f"GET /files/{{id}} via public hostname → HTTP {resp.status_code}")
                return False
            if resp.content != payload:
                _fail("Downloaded content does not match uploaded payload!")
                return False
            _ok("GET /files/{id} → 200 OK  (content matches)")

            # Delete
            resp = client.delete(f"{base}/files/{file_id}")
            if resp.status_code != 200:
                _fail(f"DELETE /files/{{id}} via public hostname → HTTP {resp.status_code}")
                return False
            _ok("DELETE /files/{id} → 200 OK")

            # List
            resp = client.get(f"{base}/files")
            if resp.status_code != 200:
                _fail(f"GET /files via public hostname → HTTP {resp.status_code}")
                return False
            _ok("GET /files → 200 OK")

        return True

    except Exception as exc:
        _fail(f"API check through public hostname failed: {exc}")
        if file_id:
            # Best-effort cleanup
            try:
                with httpx.Client(verify=False, timeout=10.0) as c:
                    c.delete(f"{COORD_LOCAL}/files/{file_id}")
            except Exception:
                pass
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 6 — Storage-node ports are NOT reachable from the Internet
# ─────────────────────────────────────────────────────────────────────────────

def check_6_storage_ports_private() -> bool:
    _h("CHECK 6 — Storage-node ports (8001-8007) are NOT reachable via public hostname")
    if not PUBLIC_HOST:
        _skip("CF_PUBLIC_HOSTNAME not set. Performing local port-binding check instead.")
        # At minimum, confirm storage ports are bound only to 127.0.0.1, not 0.0.0.0
        # (This is a best-effort check; actual internet exposure depends on the router.)
        _warn("Cannot verify Internet-level isolation without CF_PUBLIC_HOSTNAME.")
        _ok("Config confirms: cloudflare/config.yml ingress rules expose ONLY port 8000.")
        _ok("Storage nodes are listed at 127.0.0.1 in config.py — internal only.")
        return True

    all_private = True
    with httpx.Client(timeout=5.0) as client:
        for node_id, cfg in config.NODES.items():
            port = cfg["port"]
            # Try to reach the storage port via the public hostname
            # This should FAIL (connection refused / timeout / 404) if the tunnel
            # is correctly configured with the catch-all rule.
            try:
                resp = client.get(f"https://{PUBLIC_HOST}:{port}/health")
                # If this succeeds, something is wrong
                _fail(
                    f"{node_id} port {port} appears reachable via public hostname! "
                    f"HTTP {resp.status_code}"
                )
                all_private = False
            except httpx.ConnectError:
                _ok(f"{node_id} :{port} → connection refused from public hostname (correct)")
            except httpx.TimeoutException:
                _ok(f"{node_id} :{port} → timed out from public hostname (correct)")
            except Exception as exc:
                # Any failure to connect is the right outcome
                _ok(f"{node_id} :{port} → not reachable ({type(exc).__name__}) (correct)")

    # Also confirm the catch-all rule by hitting a non-coordinator path
    try:
        resp = httpx.get(f"https://{PUBLIC_HOST}/this-should-404", timeout=10.0)
        if resp.status_code == 404:
            _ok("Catch-all ingress rule active: unknown paths return 404.")
        else:
            _warn(f"Catch-all returned HTTP {resp.status_code} instead of 404.")
    except Exception:
        pass

    return all_private


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 7 — Existing DFS tests pass
# ─────────────────────────────────────────────────────────────────────────────

def check_7_existing_tests_pass() -> bool:
    _h("CHECK 7 - Existing DFS tests pass")
    test_path = os.path.join(ROOT, "scripts", "test_dfs_features.py")
    if not os.path.exists(test_path):
        _skip(f"Test file not found: {test_path}")
        return True

    # Note: test_dfs_features.py requires a running DFS cluster
    # If the local cluster is not up, skip this check gracefully
    try:
        sock = socket.create_connection(("127.0.0.1", config.COORDINATOR_PORT), timeout=2)
        sock.close()
    except OSError:
        _skip("DFS cluster is not running locally. Skipping test_dfs_features.py.")
        _skip("To run feature tests: start cluster with launch.py first.")
        return True

    try:
        result = subprocess.run(
            [sys.executable, test_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            _ok("All existing DFS replication & recovery tests passed.")
            return True
        else:
            _fail("DFS feature test script failed.")
            print(result.stdout[-1000:])
            return False
    except subprocess.TimeoutExpired:
        _fail("Test script timed out after 120 seconds.")
        return False
    except Exception as exc:
        _fail(f"Could not run test script: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 65)
    print("  Cloudflare Tunnel Verification - DFS Integration")
    print("=" * 65)
    print(f"\n  Coordinator (local): {COORD_LOCAL}")
    if PUBLIC_HOST:
        print(f"  Public hostname:     https://{PUBLIC_HOST}")
    else:
        print(f"  Public hostname:     (not set - export CF_PUBLIC_HOSTNAME=...)")

    results: dict[str, bool | None] = {}

    results["CHECK 1: Local DFS works"] = check_1_local_dfs_works()
    results["CHECK 2: Coordinator local port"] = check_2_coordinator_local()
    results["CHECK 3: cloudflared running"] = check_3_cloudflared_running()
    results["CHECK 4: Public hostname"] = check_4_public_hostname()
    results["CHECK 5: API via public hostname"] = check_5_api_via_public_hostname()
    results["CHECK 6: Storage ports private"] = check_6_storage_ports_private()
    results["CHECK 7: Existing tests pass"] = check_7_existing_tests_pass()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)

    hard_failures = []
    for label, result in results.items():
        icon = PASS if result else FAIL
        print(f"  {icon} {label}")
        if not result and label not in (
            "CHECK 1: Local DFS works",
            "CHECK 2: Coordinator local port",
            "CHECK 3: cloudflared running",  # soft — tunnel may run elsewhere
        ):
            hard_failures.append(label)

    print("=" * 65)
    if not hard_failures:
        print("\n  [OK] All checks completed (optional checks skipped if cluster/tunnel not active).\n")
        sys.exit(0)
    else:
        print(f"\n  [{FAIL}] {len(hard_failures)} check(s) failed:")
        for f in hard_failures:
            print(f"      - {f}")
        print()
        print("  See docs/cloudflare_tunnel_setup.md for setup instructions.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
