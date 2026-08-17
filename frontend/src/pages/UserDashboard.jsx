import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../AuthContext.jsx';
import { fetchFiles, downloadFile, deleteFile, formatBytes, formatRelTime, getPreviewUrl } from '../api.js';
import UploadZone from '../components/UploadZone.jsx';
import FilePreviewModal from '../components/FilePreviewModal.jsx';

function FileCard({ file, onSelect, onDelete, onDownload }) {
  const ext = file.filename.split('.').pop()?.toLowerCase() || '';
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext);
  const previewUrl = getPreviewUrl(file.id);

  let typeBadge = ext.toUpperCase();
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) typeBadge = 'IMG';
  if (['mp4', 'webm'].includes(ext)) typeBadge = 'VIDEO';
  if (['mp3', 'wav', 'ogg'].includes(ext)) typeBadge = 'AUDIO';
  if (ext === 'pdf') typeBadge = 'PDF';

  return (
    <div className="user-file-card" onClick={() => onSelect(file)}>
      <div className="file-card-preview">
        {isImage ? (
          <img src={previewUrl} alt={file.filename} className="card-thumb" />
        ) : (
          <div className="card-icon-fallback">
            <span className="type-badge">{typeBadge}</span>
          </div>
        )}
      </div>

      <div className="file-card-info">
        <span className="file-card-title" title={file.filename}>
          {file.filename}
        </span>
        <div className="file-card-sub">
          <span>{formatBytes(file.size)}</span>
          <span className="dot-sep">•</span>
          <span>{formatRelTime(file.created_at)}</span>
        </div>
      </div>

      <div className="file-card-actions" onClick={e => e.stopPropagation()}>
        <button
          className="btn-icon"
          title="Download"
          onClick={() => onDownload(file)}
        >
          ⬇
        </button>
        <button
          className="btn-icon danger"
          title="Delete"
          onClick={() => onDelete(file)}
        >
          🗑
        </button>
      </div>
    </div>
  );
}

export default function UserDashboard() {
  const { user, logout, refetchUser } = useAuth();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [activeTab, setActiveTab] = useState('my-files');

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

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const handleUploaded = useCallback((result) => {
    loadFiles();
    refetchUser();
    setActiveTab('my-files');
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
    <div className="user-app-layout">
      {/* ── Header ── */}
      <header className="user-header">
        <div className="header-logo">
          <div className="header-logo-icon">⬡</div>
          <span>Lockin Storage</span>
        </div>

        <div className="search-bar-wrap">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="search-input"
            placeholder="Search your encrypted files..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>✕</button>
          )}
        </div>

        <div className="header-user-profile">
          <div className="user-quota-mini">
            <span className="quota-text">{formatBytes(usedBytes)} / {formatBytes(quotaBytes)}</span>
            <div className="quota-track">
              <div className="quota-fill" style={{ width: `${quotaPct}%` }} />
            </div>
          </div>
          <img src={user?.picture} alt={user?.name} className="user-avatar-header" />
          <button className="btn btn-ghost btn-sm" onClick={logout}>Sign Out</button>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <div className="user-body">
        {/* Sidebar */}
        <aside className="user-sidebar">
          <button
            className={`user-nav-btn ${activeTab === 'my-files' ? 'active' : ''}`}
            onClick={() => setActiveTab('my-files')}
          >
            <span className="nav-icon">📁</span> My Files ({files.length})
          </button>
          <button
            className={`user-nav-btn ${activeTab === 'upload' ? 'active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <span className="nav-icon">☁️</span> Upload File
          </button>

          <div className="sidebar-storage-card">
            <div className="storage-card-header">
              <span>Storage Usage</span>
              <span className="storage-pct">{quotaPct}%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${quotaPct}%` }} />
            </div>
            <span className="storage-card-sub">
              {formatBytes(quotaBytes - usedBytes)} remaining of 1 GB
            </span>
          </div>
        </aside>

        {/* Content Area */}
        <main className="user-main">
          {activeTab === 'upload' && (
            <div className="upload-page-card">
              <h2 className="section-title">Upload Encrypted File</h2>
              <p className="page-subtitle">
                Files are AES-256 encrypted, split into 3 chunks, and replicated across the distributed cluster.
              </p>
              <div className="card" style={{ marginTop: 16 }}>
                <UploadZone onUploaded={handleUploaded} addToast={addToast} />
              </div>
            </div>
          )}

          {activeTab === 'my-files' && (
            <>
              <div className="files-section-header">
                <div>
                  <h1 className="page-title">My Files</h1>
                  <p className="page-subtitle">
                    {filteredFiles.length} {filteredFiles.length === 1 ? 'file' : 'files'}{' '}
                    {searchQuery ? `matching "${searchQuery}"` : 'stored securely'}
                  </p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={() => setActiveTab('upload')}
                >
                  + Upload New
                </button>
              </div>

              {loading ? (
                <div className="files-grid">
                  {[1, 2, 3, 4, 5, 6].map(i => (
                    <div key={i} className="skeleton" style={{ height: 180, borderRadius: 14 }} />
                  ))}
                </div>
              ) : filteredFiles.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">🗂</span>
                  <p className="empty-text">
                    {searchQuery ? 'No files match your search filter' : 'No files uploaded yet'}
                  </p>
                  {!searchQuery && (
                    <button
                      className="btn btn-primary"
                      style={{ marginTop: 14 }}
                      onClick={() => setActiveTab('upload')}
                    >
                      Upload your first file
                    </button>
                  )}
                </div>
              ) : (
                <div className="files-grid">
                  {filteredFiles.map(file => (
                    <FileCard
                      key={file.id}
                      file={file}
                      onSelect={setSelectedFile}
                      onDelete={setConfirmDelete}
                      onDownload={handleDownload}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </main>
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
            <h3 className="modal-title">Delete "{confirmDelete.filename}"?</h3>
            <p className="modal-body">
              This file will be permanently queued for garbage collection from the distributed cluster.
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleDeleteConfirmed}>Delete File</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast Notifications ── */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>
        ))}
      </div>
    </div>
  );
}
