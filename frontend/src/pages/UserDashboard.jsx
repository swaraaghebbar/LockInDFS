import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useAuth } from '../AuthContext.jsx';
import { fetchFiles, downloadFile, deleteFile, formatBytes, formatRelTime, getPreviewUrl, uploadFile } from '../api.js';
import FilePreviewModal from '../components/FilePreviewModal.jsx';

/* ── File type helper ───────────────────────────────── */
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

/* ── Media Grid Card (Pictures & Videos) ─────────────── */
function MediaGridCard({ file, onSelect, onDelete, onDownload }) {
  const ext = file.filename.split('.').pop()?.toLowerCase() || '';
  const isVideo = ['mp4', 'webm', 'mov'].includes(ext);
  const previewUrl = getPreviewUrl(file.id);

  return (
    <div className="media-grid-card" onClick={() => onSelect(file)}>
      <div className="media-preview-container">
        {isVideo ? (
          <div className="video-thumb-placeholder">
            <span className="media-play-icon">▶</span>
          </div>
        ) : (
          <img src={previewUrl} alt={file.filename} loading="lazy" className="media-img" />
        )}
        <div className="media-overlay-meta">
          <div className="media-meta-title">{file.filename}</div>
          <div className="media-meta-sub">{formatBytes(file.size)} • {formatRelTime(file.created_at)}</div>
        </div>
      </div>
      <div className="media-card-actions" onClick={e => e.stopPropagation()}>
        <button className="media-action-btn" onClick={() => onDownload(file)}>↓</button>
        <button className="media-action-btn danger" onClick={() => onDelete(file)}>✕</button>
      </div>
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

  // macOS-style overlay window states
  const [activeWindow, setActiveWindow] = useState(null); // null, 'pictures_video', 'documents_text', 'upload', 'audio', 'misc'
  const [windowAnimState, setWindowAnimState] = useState('closed'); // 'closed', 'opening', 'open', 'closing'
  
  const [uploading, setUploading] = useState(false);
  const [uploadingName, setUploadingName] = useState('');
  const [dragging, setDragging] = useState(false);

  const hiddenInputRef = useRef(null);

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

  const handleUploadFile = useCallback(async (file) => {
    if (!file) return;
    setUploadingName(file.name);
    setUploading(true);
    try {
      await uploadFile(file);
      addToast(`✓ Uploaded "${file.name}"`, 'success');
      loadFiles();
      refetchUser();
    } catch (e) {
      addToast(`✗ Upload failed: ${e.message}`, 'error');
    } finally {
      setUploading(false);
      setUploadingName('');
      if (hiddenInputRef.current) hiddenInputRef.current.value = '';
    }
  }, [addToast, loadFiles, refetchUser]);

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      handleUploadFile(file);
    }
  };

  const handleOpenWindow = (category) => {
    if (activeWindow === category) {
      handleCloseWindow();
      return;
    }
    setActiveWindow(category);
    setWindowAnimState('opening');
    requestAnimationFrame(() => {
      setTimeout(() => {
        setWindowAnimState('open');
      }, 10);
    });
  };

  const handleCloseWindow = () => {
    setWindowAnimState('closing');
    setTimeout(() => {
      setActiveWindow(null);
      setWindowAnimState('closed');
    }, 450);
  };

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

  // Base files sorted newest -> oldest
  const sortedFiles = useMemo(() => {
    return [...files].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }, [files]);

  // Search filtered base list
  const displayFiles = useMemo(() => {
    if (!searchQuery.trim()) return sortedFiles;
    const q = searchQuery.toLowerCase();
    return sortedFiles.filter(
      f => f.filename.toLowerCase().includes(q) || f.id.toLowerCase().includes(q)
    );
  }, [sortedFiles, searchQuery]);

  // Category specific file lists
  const picturesVideoFiles = useMemo(() => {
    return sortedFiles.filter(file => {
      const ext = file.filename.split('.').pop()?.toLowerCase() || '';
      return ['jpg','jpeg','png','gif','webp','svg','mp4','webm','mov'].includes(ext);
    });
  }, [sortedFiles]);

  const documentsTextFiles = useMemo(() => {
    return sortedFiles.filter(file => {
      const ext = file.filename.split('.').pop()?.toLowerCase() || '';
      return ['pdf','doc','docx','txt','md','csv','xls','xlsx','ppt','pptx','rtf'].includes(ext);
    });
  }, [sortedFiles]);

  const audioFiles = useMemo(() => {
    return sortedFiles.filter(file => {
      const ext = file.filename.split('.').pop()?.toLowerCase() || '';
      return ['mp3','wav','ogg','flac','aac','m4a'].includes(ext);
    });
  }, [sortedFiles]);

  const miscFiles = useMemo(() => {
    return sortedFiles.filter(file => {
      const ext = file.filename.split('.').pop()?.toLowerCase() || '';
      const isPicVid = ['jpg','jpeg','png','gif','webp','svg','mp4','webm','mov'].includes(ext);
      const isDocText = ['pdf','doc','docx','txt','md','csv','xls','xlsx','ppt','pptx','rtf'].includes(ext);
      const isAudio = ['mp3','wav','ogg','flac','aac','m4a'].includes(ext);
      return !isPicVid && !isDocText && !isAudio;
    });
  }, [sortedFiles]);

  const usedBytes = user?.storage_used || 0;
  const quotaBytes = user?.storage_quota || (1024 * 1024 * 1024);
  const quotaPct = Math.min(100, Math.round((usedBytes / quotaBytes) * 100));

  // Determine file dragging target
  const handleDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleUploadFile(file);
    }
  };

  return (
    <div className="dash-page">
      {/* Hidden file input */}
      <input
        ref={hiddenInputRef}
        type="file"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />

      {/* ── All Files Base Desktop Page ── */}
      <div
        className={`dash-container ${dragging ? 'drag-over' : ''} ${activeWindow ? 'under-overlay' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
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

        {/* Main body — single files panel */}
        <div className="dash-body">
          <div className="files-panel">
            <div className="files-panel-header">
              <div>
                <div className="files-panel-title">All Files</div>
                <div className="files-panel-count">{displayFiles.length}</div>
                <div className="files-panel-subcount">
                  {searchQuery
                    ? `matching "${searchQuery}"`
                    : 'stored securely'}
                </div>
              </div>
            </div>

            <div className="file-list">
              {/* Uploading progress inline row */}
              {uploading && (
                <div className="file-row uploading-row" style={{ pointerEvents: 'none', background: 'rgba(255,75,53,0.04)', borderBottom: '1px solid rgba(255,75,53,0.12)' }}>
                  <div className="file-row-icon" style={{ color: 'var(--accent)', borderColor: 'rgba(255,75,53,0.22)' }}>UP</div>
                  <div className="file-row-info" style={{ flex: 1 }}>
                    <div className="file-row-name" style={{ color: 'var(--accent)', fontWeight: 500 }}>Encrypting &amp; distributing {uploadingName}…</div>
                    <div className="upload-progress-bar-track" style={{ height: 2, background: 'rgba(255,255,255,0.06)', borderRadius: 1, overflow: 'hidden', marginTop: 4 }}>
                      <div className="upload-progress-bar-fill" style={{ height: '100%', background: 'var(--accent)', animation: 'progressPulse 1.2s ease-in-out infinite' }} />
                    </div>
                  </div>
                </div>
              )}

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
              ) : displayFiles.length === 0 ? (
                <div className="files-empty">
                  <div className="files-empty-icon">⬡</div>
                  <div className="files-empty-text">
                    {searchQuery ? 'No files match your search' : 'No files uploaded yet. Drag anywhere here to upload.'}
                  </div>
                </div>
              ) : (
                displayFiles.map(file => (
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

      {/* ── macOS-style Category Window Overlay ── */}
      {activeWindow && (
        <div className={`window-overlay ${windowAnimState}`}>
          <div className="category-window">
            
            {/* Window Title Bar */}
            <div className="window-titlebar">
              <div className="titlebar-left">
                {activeWindow === 'pictures_video' && (
                  <>
                    <svg className="window-title-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="3" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <path d="M21 15l-5-5L5 21" />
                    </svg>
                    <span className="window-title-text">Pictures / Video</span>
                    <span className="window-title-count">({picturesVideoFiles.length} items)</span>
                  </>
                )}
                {activeWindow === 'documents_text' && (
                  <>
                    <svg className="window-title-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                    </svg>
                    <span className="window-title-text">Documents / Text</span>
                    <span className="window-title-count">({documentsTextFiles.length} items)</span>
                  </>
                )}
                {activeWindow === 'upload' && (
                  <>
                    <svg className="window-title-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <span className="window-title-text">File Upload</span>
                  </>
                )}
                {activeWindow === 'audio' && (
                  <>
                    <svg className="window-title-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
                      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
                    </svg>
                    <span className="window-title-text">Audio</span>
                    <span className="window-title-count">({audioFiles.length} items)</span>
                  </>
                )}
                {activeWindow === 'misc' && (
                  <>
                    <svg className="window-title-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                      <line x1="12" y1="22.08" x2="12" y2="12" />
                    </svg>
                    <span className="window-title-text">Miscellaneous</span>
                    <span className="window-title-count">({miscFiles.length} items)</span>
                  </>
                )}
              </div>
              <button className="window-close-trigger" onClick={handleCloseWindow} title="Close window">✕</button>
            </div>

            {/* Window Content Body */}
            <div className="window-body-content">
              {activeWindow === 'pictures_video' && (
                picturesVideoFiles.length === 0 ? (
                  <div className="window-empty-state">No images or videos stored.</div>
                ) : (
                  <div className="media-masonry-grid">
                    {picturesVideoFiles.map(file => (
                      <MediaGridCard
                        key={file.id}
                        file={file}
                        onSelect={setSelectedFile}
                        onDelete={setConfirmDelete}
                        onDownload={handleDownload}
                      />
                    ))}
                  </div>
                )
              )}

              {activeWindow === 'documents_text' && (
                documentsTextFiles.length === 0 ? (
                  <div className="window-empty-state">No documents found.</div>
                ) : (
                  <div className="window-list-view">
                    {documentsTextFiles.map(file => (
                      <FileRow
                        key={file.id}
                        file={file}
                        onSelect={setSelectedFile}
                        onDelete={setConfirmDelete}
                        onDownload={handleDownload}
                      />
                    ))}
                  </div>
                )
              )}

              {activeWindow === 'audio' && (
                audioFiles.length === 0 ? (
                  <div className="window-empty-state">No audio files found.</div>
                ) : (
                  <div className="window-list-view">
                    {audioFiles.map(file => (
                      <FileRow
                        key={file.id}
                        file={file}
                        onSelect={setSelectedFile}
                        onDelete={setConfirmDelete}
                        onDownload={handleDownload}
                      />
                    ))}
                  </div>
                )
              )}

              {activeWindow === 'misc' && (
                miscFiles.length === 0 ? (
                  <div className="window-empty-state">No miscellaneous files found.</div>
                ) : (
                  <div className="window-list-view">
                    {miscFiles.map(file => (
                      <FileRow
                        key={file.id}
                        file={file}
                        onSelect={setSelectedFile}
                        onDelete={setConfirmDelete}
                        onDownload={handleDownload}
                      />
                    ))}
                  </div>
                )
              )}

              {activeWindow === 'upload' && (
                <div className="upload-window-container">
                  <div className="upload-window-header-desc">
                    Securely encrypt &amp; distribute new files directly to the LockIn network.
                  </div>
                  
                  {uploading ? (
                    <div className="upload-active-card">
                      <div className="upload-card-spinner" />
                      <div className="upload-card-filename">Encrypting {uploadingName}</div>
                      <div className="upload-progress-bar-track" style={{ width: '100%', height: 2, background: 'rgba(255,255,255,0.06)', marginTop: 12 }}>
                        <div className="upload-progress-bar-fill" style={{ width: '100%', height: '100%', background: 'var(--accent)', animation: 'progressPulse 1.2s ease-in-out infinite' }} />
                      </div>
                    </div>
                  ) : (
                    <div 
                      className="window-dropzone" 
                      onClick={() => hiddenInputRef.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); }}
                      onDrop={handleDrop}
                    >
                      <svg className="dropzone-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                      </svg>
                      <span className="dropzone-title">Drop Files Here</span>
                      <span className="dropzone-subtitle">or click to browse local storage</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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

      {/* ── Floating File Category Bar ── */}
      <div className="floating-category-bar">
        <button
          className={`category-item ${activeWindow === 'pictures_video' ? 'active' : ''}`}
          onClick={() => handleOpenWindow('pictures_video')}
          title="Pictures / Video"
        >
          <svg className="cat-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span className="category-label">Pictures / Video</span>
        </button>

        <button
          className={`category-item ${activeWindow === 'documents_text' ? 'active' : ''}`}
          onClick={() => handleOpenWindow('documents_text')}
          title="Documents / Text"
        >
          <svg className="cat-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <span className="category-label">Documents / Text</span>
        </button>

        <button
          className={`category-item primary-upload ${activeWindow === 'upload' ? 'active' : ''}`}
          onClick={() => handleOpenWindow('upload')}
          title="File Upload"
        >
          <svg className="cat-svg primary-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span className="category-label">File Upload</span>
        </button>

        <button
          className={`category-item ${activeWindow === 'audio' ? 'active' : ''}`}
          onClick={() => handleOpenWindow('audio')}
          title="Audio"
        >
          <svg className="cat-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
            <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
          </svg>
          <span className="category-label">Audio</span>
        </button>

        <button
          className={`category-item ${activeWindow === 'misc' ? 'active' : ''}`}
          onClick={() => handleOpenWindow('misc')}
          title="Miscellaneous"
        >
          <svg className="cat-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
          <span className="category-label">Miscellaneous</span>
        </button>
      </div>
    </div>
  );
}
