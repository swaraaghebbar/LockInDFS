// API client — all calls go through Vite's proxy to the coordinator at :8000
const BASE = '/api';

// ── Auth API ──────────────────────────────────────────────────────
export async function fetchMe() {
  const r = await fetch(`${BASE}/auth/me`);
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`Auth check failed: ${r.status}`);
  return r.json();
}

export function getGoogleLoginUrl() {
  return `${BASE}/auth/google`;
}

export async function logoutUser() {
  const r = await fetch(`${BASE}/auth/logout`, { method: 'POST' });
  if (!r.ok) throw new Error(`Logout failed: ${r.status}`);
  return r.json();
}

// ── Admin API ─────────────────────────────────────────────────────
export async function fetchAdminUsers() {
  const r = await fetch(`${BASE}/admin/users`);
  if (!r.ok) throw new Error(`Fetch admin users failed: ${r.status}`);
  return r.json();
}

// ── File & Cluster API ────────────────────────────────────────────
export async function fetchCluster() {
  const r = await fetch(`${BASE}/cluster`);
  if (!r.ok) throw new Error(`Cluster fetch failed: ${r.status}`);
  return r.json();
}

export async function fetchFiles() {
  const r = await fetch(`${BASE}/files`);
  if (!r.ok) throw new Error(`Files fetch failed: ${r.status}`);
  return r.json();
}

export async function uploadFile(file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${BASE}/files`, { method: 'POST', body: form });
  if (!r.ok) {
    const txt = await r.text();
    let errMessage = txt;
    try {
      const parsed = JSON.parse(txt);
      if (parsed.detail) errMessage = parsed.detail;
    } catch {}
    throw new Error(errMessage || `Upload failed: ${r.status}`);
  }
  return r.json();
}

export async function downloadFile(fileId, filename) {
  const r = await fetch(`${BASE}/files/${fileId}`);
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function getPreviewUrl(fileId) {
  return `${BASE}/files/${fileId}/preview`;
}

export async function deleteFile(fileId) {
  const r = await fetch(`${BASE}/files/${fileId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`Delete failed: ${r.status}`);
  return r.json();
}

// ── Formatting helpers ────────────────────────────────────────────
export function formatBytes(bytes) {
  if (bytes === 0 || !bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatRelTime(isoStr) {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function shortHash(hash) {
  if (!hash) return '';
  return hash.slice(0, 8) + '…';
}
