import { useState, useEffect } from 'react';
import { getPreviewUrl, downloadFile, formatBytes, formatRelTime } from '../api.js';

export default function FilePreviewModal({ file, onClose, addToast }) {
  const [textData, setTextData] = useState(null);
  const [loadingText, setLoadingText] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [playing, setPlaying] = useState(false);

  const previewUrl = getPreviewUrl(file.id);
  const filename = file.filename || '';
  const ext = filename.split('.').pop()?.toLowerCase() || '';

  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext);
  const isVideo = ['mp4', 'webm'].includes(ext);
  const isAudio = ['mp3', 'wav', 'ogg'].includes(ext);
  const isPdf = ext === 'pdf';
  const isText = ['txt', 'md', 'json', 'js', 'jsx', 'ts', 'tsx', 'py', 'html', 'css', 'csv', 'log', 'env', 'yml', 'yaml'].includes(ext);

  useEffect(() => {
    if (isText) {
      setLoadingText(true);
      fetch(previewUrl)
        .then(res => res.text())
        .then(text => setTextData(text))
        .catch(err => setTextData(`Failed to load preview: ${err.message}`))
        .finally(() => setLoadingText(false));
    }
  }, [isText, previewUrl]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadFile(file.id, file.filename);
      addToast?.(`✓ Downloaded "${file.filename}"`, 'success');
    } catch (e) {
      addToast?.(`✗ ${e.message}`, 'error');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="preview-overlay" onClick={onClose}>
      <div className="preview-modal" onClick={e => e.stopPropagation()}>
        <header className="preview-header">
          <div className="preview-file-info">
            <span className="preview-filename">{filename}</span>
            <span className="preview-meta">
              {formatBytes(file.size)} · Uploaded {formatRelTime(file.created_at)}
            </span>
          </div>
          <div className="preview-actions">
            <button
              className="btn btn-primary"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading ? '⏳ Downloading...' : '⬇ Download'}
            </button>
            <button className="preview-close-btn" onClick={onClose}>
              ✕
            </button>
          </div>
        </header>

        <div className="preview-body">
          {isImage && (
            <div className="preview-media-wrapper">
              <img src={previewUrl} alt={filename} className="preview-image" />
            </div>
          )}

          {isVideo && (
            <div className="preview-media-wrapper">
              <video controls src={previewUrl} className="preview-video" />
            </div>
          )}

          {isAudio && (
            <div className="preview-media-wrapper audio-wrapper">
              {/* Dynamic Vinyl Record Player */}
              <div className={`vinyl-player ${playing ? 'playing' : ''}`}>
                <div className="vinyl-arm"></div>
                <div className="vinyl-disc">
                  <div className="vinyl-label">
                    <div className="vinyl-center"></div>
                  </div>
                </div>
              </div>
              <audio
                controls
                src={previewUrl}
                className="preview-audio"
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onEnded={() => setPlaying(false)}
              />
            </div>
          )}

          {isPdf && (
            <iframe
              src={previewUrl}
              title={filename}
              className="preview-iframe"
            />
          )}

          {isText && (
            <div className="preview-text-container">
              {loadingText ? (
                <div className="spinner-center"><div className="spinner" /></div>
              ) : (
                <pre className="preview-code-block">{textData}</pre>
              )}
            </div>
          )}

          {!isImage && !isVideo && !isAudio && !isPdf && !isText && (
            <div className="preview-fallback">
              <span className="fallback-icon">📄</span>
              <p className="fallback-title">No direct preview available for .{ext} files</p>
              <p className="fallback-sub">Download the file to view its contents locally.</p>
              <button className="btn btn-primary" onClick={handleDownload}>
                Download {filename}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
