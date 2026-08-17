import { useState } from 'react';
import { downloadFile, deleteFile, formatBytes, formatRelTime, shortHash } from '../api.js';

function ConfirmModal({ file, onConfirm, onCancel }) {
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <p className="modal-title">Delete "{file.filename}"?</p>
        <p className="modal-body">
          The file will be marked for deletion. The background garbage collector
          will physically reclaim the storage within the next GC cycle.
        </p>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button id="confirm-delete-btn" className="btn btn-danger" onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

export default function FilesPanel({ files, onDeleted, addToast, loading }) {
  const [downloading, setDownloading] = useState(null);
  const [deleting, setDeleting]       = useState(null);
  const [confirmFile, setConfirmFile] = useState(null);

  const handleDownload = async (file) => {
    setDownloading(file.id);
    try {
      await downloadFile(file.id, file.filename);
      addToast(`✓ Downloaded "${file.filename}"`, 'success');
    } catch (e) {
      addToast(`✗ ${e.message}`, 'error');
    } finally {
      setDownloading(null);
    }
  };

  const handleDelete = async () => {
    const file = confirmFile;
    setConfirmFile(null);
    setDeleting(file.id);
    try {
      await deleteFile(file.id);
      addToast(`✓ Queued "${file.filename}" for GC`, 'success');
      onDeleted(file.id);
    } catch (e) {
      addToast(`✗ ${e.message}`, 'error');
    } finally {
      setDeleting(null);
    }
  };

  if (loading && !files.length) {
    return (
      <div>
        {[1,2,3].map(i => (
          <div key={i} className="skeleton" style={{ height: 42, marginBottom: 6, borderRadius: 8 }} />
        ))}
      </div>
    );
  }

  if (!files.length) {
    return (
      <div className="empty-state">
        <span className="empty-icon">🗂</span>
        <p className="empty-text">No files stored yet — upload one above!</p>
      </div>
    );
  }

  return (
    <>
      {confirmFile && (
        <ConfirmModal
          file={confirmFile}
          onConfirm={handleDelete}
          onCancel={() => setConfirmFile(null)}
        />
      )}
      <div className="file-table-wrap">
        <table className="file-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Size</th>
              <th>Replicas / Nodes</th>
              <th>Last accessed</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {files.map(file => {
              return (
                <tr key={file.id}>
                  <td>
                    <div className="file-name" title={file.filename}>{file.filename}</div>
                    <div className="file-hash" title={file.id}>{shortHash(file.id)}</div>
                  </td>
                  <td><span className="file-size">{formatBytes(file.size)}</span></td>
                  <td>
                    <div className="node-tags">
                      {(file.nodes || []).map(n => (
                        <span key={n} className="node-tag">
                          {n}
                        </span>
                      ))}
                      {(!file.nodes || file.nodes.length === 0) && <span className="text-dim">—</span>}
                    </div>
                  </td>
                  <td><span className="file-time">{formatRelTime(file.last_accessed)}</span></td>
                  <td><span className="file-time">{formatRelTime(file.created_at)}</span></td>
                  <td>
                    <div className="btn-row">
                      <button
                        id={`download-${file.id}`}
                        className="btn btn-ghost"
                        onClick={() => handleDownload(file)}
                        disabled={downloading === file.id || deleting === file.id}
                      >
                        {downloading === file.id ? '⏳' : '⬇'} Download
                      </button>
                      <button
                        id={`delete-${file.id}`}
                        className="btn btn-danger"
                        onClick={() => setConfirmFile(file)}
                        disabled={deleting === file.id || downloading === file.id}
                      >
                        {deleting === file.id ? '⏳' : '🗑'} Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
