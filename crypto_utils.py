"""
Crypto Utilities for DFS Phase 13.

Provides functionality for:
- Layer 1: In-transit TLS certificate generation & SSL contexts.
- Layer 2: At-rest AES-256-GCM encryption & decryption per chunk.
- Layer 3: Envelope encryption (KEK/DEK management & wrapping).
- Deduplication: Convergent encryption (key derived from chunk plaintext hash).

Comments explain security rationale, architecture decisions, and trade-offs.
"""

import os
import hmac
import hashlib
import ssl
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta, timezone

# ── LAYER 3: KEY MANAGEMENT & ENVELOPE ENCRYPTION ─────────────────────────────
#
# WHY ENVELOPE ENCRYPTION?
# 1. Key Rotation: We can rotate the master Key-Encryption-Key (KEK) by simply
#    re-encrypting the small per-file Data-Encryption-Keys (DEKs) in the metadata DB.
#    We NEVER need to re-encrypt gigabytes/terabytes of stored blob data on disk.
# 2. Key Separation: Plaintext keys are never stored on disk. The KEK is supplied at
#    runtime (via env var or key file), and DEKs exist on disk only in wrapped (encrypted) form.
# 3. Isolation: Compromise of one file's DEK does not expose other files.

# Master KEK from env var, file, or dev default (32-byte hex or string)
DEFAULT_DEV_KEK = b"DFS_MASTER_KEY_ENCRYPTION_KEY_32BYTES!!"  # Exactly 32 bytes

def get_master_kek() -> bytes:
    """Retrieve the master KEK from environment or fallback dev default."""
    env_kek = os.getenv("DFS_MASTER_KEK")
    if env_kek:
        # Standardize to 32 bytes using SHA-256
        return hashlib.sha256(env_kek.encode('utf-8')).digest()
    return DEFAULT_DEV_KEK[:32]

def generate_dek() -> bytes:
    """Generate a random 256-bit (32-byte) Data Encryption Key (DEK)."""
    return AESGCM.generate_key(bit_length=256)

def wrap_dek(dek: bytes, kek: bytes = None) -> bytes:
    """
    Wrap (encrypt) a DEK using the KEK with AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + tag (16 bytes)
    """
    if kek is None:
        kek = get_master_kek()
    aesgcm = AESGCM(kek)
    nonce = os.urandom(12)
    wrapped = aesgcm.encrypt(nonce, dek, None)
    return nonce + wrapped

def unwrap_dek(wrapped_dek: bytes, kek: bytes = None) -> bytes:
    """
    Unwrap (decrypt) a wrapped DEK using the KEK.
    """
    if kek is None:
        kek = get_master_kek()
    aesgcm = AESGCM(kek)
    nonce = wrapped_dek[:12]
    ciphertext = wrapped_dek[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)




# ── DEDUPLICATION: CONVERGENT ENCRYPTION ────────────────────────────────────────
#
# WHY CONVERGENT ENCRYPTION FOR DEDUP?
# Naive per-file or per-chunk random keys break deduplication completely because
# identical plaintext chunks encrypted with different random keys produce different
# ciphertext blobs.
#
# Convergent encryption derives the chunk's encryption key deterministically from
# the SHA-256 hash of the chunk's plaintext salted with the KEK:
#   chunk_key = HMAC-SHA256(KEK, chunk_plaintext)
#
# This ensures identical plaintext chunks produce IDENTICAL ciphertext blobs, enabling
# chunk-level deduplication to work seamlessly while data remains encrypted on disk.
#
# SECURITY TRADEOFF / PRIVACY NOTE:
# An attacker who possesses a candidate file/chunk can encrypt it using the same scheme
# and check if the resulting ciphertext hash exists in our system. Thus, convergent
# encryption allows confirmation of whether a known file/chunk exists in storage
# ("confirmation-of-file attack"). However, it protects unknown files against blind
# content disclosure.

def derive_convergent_key(chunk_plaintext: bytes, kek: bytes = None) -> bytes:
    """
    Derive a 256-bit AES key deterministically from the chunk plaintext & KEK.
    """
    if kek is None:
        kek = get_master_kek()
    return hmac.new(kek, chunk_plaintext, hashlib.sha256).digest()


# ── LAYER 2: ENCRYPTION AT REST (PER NODE) ──────────────────────────────────────
#
# WHY AES-256-GCM AT REST?
# 1. Confidentiality: Each blob stored on disk (e.g., on a removable USB flash drive
#    or hard disk partition) is ciphertext. If someone physically steals or unplugs
#    the SanDisk USB stick, the stored blobs are completely unreadable without the KEK/DEK.
# 2. Authenticated Integrity: AES-GCM generates a 128-bit authentication tag.
#    Any tampering with the ciphertext on disk is detected immediately upon decryption.
#
# NOTE ON REMOVABLE USB: Removable storage is at high risk of physical theft or loss.
# Encryption at rest ensures data privacy even if physical access is lost.

def encrypt_chunk(chunk_plaintext: bytes, key: bytes, deterministic_nonce: bool = False) -> bytes:
    """
    Encrypt a chunk payload using AES-256-GCM.
    Structure: nonce (12 bytes) + ciphertext + tag (16 bytes)
    """
    aesgcm = AESGCM(key)
    if deterministic_nonce:
        nonce = hmac.new(key, chunk_plaintext, hashlib.sha256).digest()[:12]
    else:
        nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, chunk_plaintext, None)
    return nonce + ciphertext


def decrypt_chunk(encrypted_chunk: bytes, key: bytes) -> bytes:
    """
    Decrypt an AES-256-GCM encrypted chunk payload.
    Extracts nonce (first 12 bytes) and ciphertext+tag.
    """
    aesgcm = AESGCM(key)
    nonce = encrypted_chunk[:12]
    ciphertext = encrypted_chunk[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)


# ── LAYER 1: ENCRYPTION IN TRANSIT (TLS / HTTPS) ──────────────────────────────
#
# WHY TLS / HTTPS IN TRANSIT?
# Network traffic between client <-> coordinator and coordinator <-> nodes passes
# over network interfaces. Without TLS, an attacker on the same Wi-Fi, switch, or
# network path can eavesdrop (network sniffing) or intercept/tamper with API requests.
# Using HTTPS ensures full end-to-end confidentiality and integrity over the wire.

CERT_DIR = os.path.join(os.path.dirname(__file__), "certs")
CERT_FILE = os.path.join(CERT_DIR, "server.crt")
KEY_FILE = os.path.join(CERT_DIR, "server.key")

def generate_self_signed_cert():
    """
    Generate a self-signed X.509 certificate and private key for local HTTPS/TLS.
    """
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return CERT_FILE, KEY_FILE

    os.makedirs(CERT_DIR, exist_ok=True)
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"DFS Self Signed"),
    ])
    import ipaddress
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(timezone.utc)
    ).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
        critical=False,
    ).sign(key, hashes.SHA256())


    with open(KEY_FILE, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return CERT_FILE, KEY_FILE
