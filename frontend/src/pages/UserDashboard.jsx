import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useAuth } from '../AuthContext.jsx';
import { fetchFiles, downloadFile, deleteFile, formatBytes, formatRelTime, getPreviewUrl, uploadFile } from '../api.js';
import FilePreviewModal from '../components/FilePreviewModal.jsx';

/* ── File type badge helper ─────────────────────────── */
function getTypeBadge(filename) {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['jpg','jpeg','png','gif','webp','svg'].includes(ext)) return 'IMG';
  if (['mp4','webm','mov'].includes(ext)) return 'VID';
  if (['mp3','wav','ogg','flac'].includes(ext)) return 'AUD';
  if (ext === 'pdf') return 'PDF';
  if (['zip','tar','gz','rar','7z'].includes(ext)) return 'ZIP';
  if (['js','ts','jsx','tsx','py','go','rs','cpp','c','java'].includes(ext)) return 'CODE';
  if (['md','txt','csv'].includes(ext)) return 'TXT';
  return ext.slice(0,4).toUpperCase() || 'FILE';
}

/* ── Single File Row ────────────────────────────────── */
function FileRow({ file, onSelect, onDelete, onDownload }) {
  return (
    <div className="file-row" onClick={() => onSelect(file)}>
      <div className="file-row-icon">{getTypeBadge(file.filename)}</div>
      <div className="file-row-info">
        <div className="file-row-name" title={file.filename}>{file.filename}</div>
        <div className="file-row-meta">{formatRelTime(file.created_at)}</div>
      </div>
      <div className="file-row-size">{formatBytes(file.size)}</div>
      <div className="file-row-actions" onClick={e => e.stopPropagation()}>
        <button
          className="file-action-btn"
          title="Download"
          onClick={() => onDownload(file)}
        >↓</button>
        <button
          className="file-action-btn danger"
          title="Delete"
          onClick={() => onDelete(file)}
        >✕</button>
      </div>
    </div>
  );
}

/* ── Upload Panel (integrated) ─────────────────────── */
function UploadPanel({ onUploaded, addToast }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingName, setUploadingName] = useState('');
  const [success, setSuccess] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = useCallback(async (files) => {
    const file = files[0];
    if (!file) return;
    setUploadingName(file.name);
    setUploading(true);
    setSuccess(false);
    try {
      const result = await uploadFile(file);
      setSuccess(true);
      addToast(`Uploaded "${file.name}"`, 'success');
      onUploaded(result);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      addToast(`Upload failed: ${e.message}`, 'error');
    } finally {
      setUploading(false);
      setUploadingName('');
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [onUploaded, addToast]);

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="upload-panel">
      <div className="upload-panel-header">
        <div className="upload-pending-info">
          <div className="upload-pending-count">
            {uploading ? '···' : success ? '✓' : '+'}
          </div>
          <div className="upload-pending-label">
            {uploading ? 'Uploading' : success ? 'Locked in' : 'Upload file'}
          </div>
          {uploading && (
            <div className="upload-pending-size">{uploadingName}</div>
          )}
        </div>

        {!uploading && !success && (
          <button
            className="upload-cta-btn"
            onClick={() => inputRef.current?.click()}
          >
            ↑ Upload
          </button>
        )}
      </div>

      {/* Progress bar */}
      {uploading && (
        <div className="upload-progress-wrap">
          <div className="upload-progress-bar-track">
            <div className="upload-progress-bar-fill" style={{ width: '100%' }} />
          </div>
          <div className="upload-progress-file">
            Encrypting &amp; distributing — {uploadingName}
          </div>
        </div>
      )}

      {/* Success state */}
      {success && (
        <div className="upload-success">
          <span>✓</span>
          <span>Stored securely across the network</span>
        </div>
      )}

      {/* Drop zone */}
      {!uploading && !success && (
        <div
          className={`drop-zone ${dragging ? 'drag-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            id="file-input"
            onChange={(e) => handleFiles(e.target.files)}
            style={{ display: 'none' }}
          />
          <span className="drop-zone-icon">⬡</span>
          <p className="drop-zone-text">
            <strong>Drop a file here</strong><br />
            or click to browse
          </p>
        </div>
      )}

      {/* Subtle info */}
      {!uploading && !success && (
        <div style={{ marginTop: 'auto', paddingTop: 16 }}>
          <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', lineHeight: 1.6, letterSpacing: '0.02em' }}>
            Files are AES-GCM encrypted in-browser · split into 1 MiB chunks · replicated 3× across the node cluster
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Main Dashboard ─────────────────────────────────── */
export default function UserDashboard() {
  const { user, logout, refetchUser } = useAuth();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'success') => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3500);
  }, []);

  const loadFiles = useCallback(async () => {
    try {
      const res = await fetchFiles();
      setFiles(res.files || []);
    } catch (e) {
      addToast(`Failed to load files: ${e.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => { loadFiles(); }, [loadFiles]);

  const handleUploaded = useCallback(() => {
    loadFiles();
    refetchUser();
  }, [loadFiles, refetchUser]);

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    const f = confirmDelete;
    setConfirmDelete(null);
    try {
      await deleteFile(f.id);
      addToast(`Deleted "${f.filename}"`, 'success');
      setFiles(prev => prev.filter(item => item.id !== f.id));
      refetchUser();
    } catch (e) {
      addToast(`Delete failed: ${e.message}`, 'error');
    }
  };

  const handleDownload = async (file) => {
    try {
      await downloadFile(file.id, file.filename);
      addToast(`Downloaded "${file.filename}"`, 'success');
    } catch (e) {
      addToast(`Download failed: ${e.message}`, 'error');
    }
  };

  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return files;
    const q = searchQuery.toLowerCase();
    return files.filter(
      f => f.filename.toLowerCase().includes(q) || f.id.toLowerCase().includes(q)
    );
  }, [files, searchQuery]);

  const usedBytes = user?.storage_used || 0;
  const quotaBytes = user?.storage_quota || (1024 * 1024 * 1024);
  const quotaPct = Math.min(100, Math.round((usedBytes / quotaBytes) * 100));

  return (
    <div className="dash-page">

      {/* ── App Container ── */}
      <div className="dash-container">
        {/* Cinematic background */}
        <div className="dash-bg" />

        {/* Header */}
        <header className="dash-header">
          <div className="dash-wordmark">
            <div className="dash-wordmark-dot" />
            LOCKIN
          </div>

          {/* Search */}
          <div className="dash-search-wrap">
            <span className="dash-search-icon">⌕</span>
            <input
              type="text"
              className="dash-search-input"
              placeholder="Search files…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="dash-search-clear" onClick={() => setSearchQuery('')}>✕</button>
            )}
          </div>

          {/* Right side */}
          <div className="dash-header-right">
            <div className="dash-quota-wrap">
              <div className="dash-quota-text">
                {formatBytes(usedBytes)} / {formatBytes(quotaBytes)}
              </div>
              <div className="dash-quota-track">
                <div className="dash-quota-fill" style={{ width: `${quotaPct}%` }} />
              </div>
            </div>
            <img
              src={user?.picture}
              alt={user?.name}
              className="dash-avatar"
              title={user?.name}
            />
            <button className="dash-signout-btn" onClick={logout}>Sign out</button>
          </div>
        </header>

        {/* Main body — two columns */}
        <div className="dash-body">

          {/* Files Panel */}
          <div className="files-panel">
            <div className="files-panel-header">
              <div>
                <div className="files-panel-title">Your Files</div>
                <div className="files-panel-count">{filteredFiles.length}</div>
                <div className="files-panel-subcount">
                  {searchQuery
                    ? `matching "${searchQuery}"`
                    : 'stored securely'}
                </div>
              </div>
            </div>

            <div className="file-list">
              {loading ? (
                [1,2,3,4,5].map(i => (
                  <div key={i} className="file-row-skeleton">
                    <div className="skeleton-box" style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0 }} />
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}>
                      <div className="skeleton-box" style={{ height: 12, width: '60%' }} />
                      <div className="skeleton-box" style={{ height: 10, width: '35%' }} />
                    </div>
                    <div className="skeleton-box" style={{ width: 48, height: 10 }} />
                  </div>
                ))
              ) : filteredFiles.length === 0 ? (
                <div className="files-empty">
                  <div className="files-empty-icon">⬡</div>
                  <div className="files-empty-text">
                    {searchQuery ? 'No files match your search' : 'No files uploaded yet'}
                  </div>
                </div>
              ) : (
                filteredFiles.map(file => (
                  <FileRow
                    key={file.id}
                    file={file}
                    onSelect={setSelectedFile}
                    onDelete={setConfirmDelete}
                    onDownload={handleDownload}
                  />
                ))
              )}
            </div>
          </div>

          {/* Upload Panel */}
          <UploadPanel onUploaded={handleUploaded} addToast={addToast} />
        </div>

        {/* Footer */}
        <footer className="dash-footer">
          <span className="dash-footer-tag">
            Stored across the LockIn network
          </span>
          <div className="dash-footer-dots">
            <div className="dash-footer-dot active" title="Coordinator online" />
            <div className="dash-footer-dot active" title="Node cluster" />
            <div className="dash-footer-dot" title="Offline node" />
          </div>
        </footer>
      </div>

      {/* ── File Preview Modal ── */}
      {selectedFile && (
        <FilePreviewModal
          file={selectedFile}
          onClose={() => setSelectedFile(null)}
          addToast={addToast}
        />
      )}

      {/* ── Confirm Delete Modal ── */}
      {confirmDelete && (
        <div className="overlay" onClick={() => setConfirmDelete(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Delete "{confirmDelete.filename}"?</div>
            <div className="modal-body">
              This file will be permanently removed from the distributed cluster.
            </div>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button className="btn-danger" onClick={handleDeleteConfirmed}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toasts ── */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>
        ))}
      </div>
    </div>
  );
}
