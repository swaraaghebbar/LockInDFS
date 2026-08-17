import { useState, useCallback, useRef } from 'react';
import { uploadFile } from '../api.js';

export default function UploadZone({ onUploaded, addToast }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState(null);
  const inputRef = useRef(null);

  const handleFiles = useCallback(async (files) => {
    const file = files[0];
    if (!file) return;
    setFileName(file.name);
    setUploading(true);
    try {
      const result = await uploadFile(file);
      addToast(`✓ Uploaded "${file.name}"`, 'success');
      onUploaded(result);
    } catch (e) {
      addToast(`✗ Upload failed: ${e.message}`, 'error');
    } finally {
      setUploading(false);
      setFileName(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [onUploaded, addToast]);

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div
      id="upload-zone"
      className={`upload-zone ${dragging ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !uploading && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        id="file-input"
        onChange={(e) => handleFiles(e.target.files)}
        style={{ display: 'none' }}
      />
      {uploading ? (
        <>
          <span className="upload-icon">⏳</span>
          <p className="upload-title">Uploading {fileName}…</p>
          <div className="upload-progress"><div className="spinner" /></div>
        </>
      ) : (
        <>
          <span className="upload-icon">☁️</span>
          <p className="upload-title">Drop a file here, or click to browse</p>
          <p className="upload-sub">
            Files are split into 1 MiB chunks · content-addressed · replicated across 3 nodes
          </p>
        </>
      )}
    </div>
  );
}
