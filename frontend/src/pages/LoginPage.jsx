import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const [isAdminMode, setIsAdminMode] = useState(false);

  return (
    <div className="login-page">

      {/* ── Cinematic App Container ── */}
      <div className="cinema-container">
        {/* Background image layer */}
        <div className="cinema-bg" />

        {/* Header */}
        <header className="cinema-header">
          <div className="cinema-wordmark">
            <div className="cinema-wordmark-dot" />
            LOCKIN
          </div>
          <nav className="cinema-nav">
            <a href="/privacy.html" target="_blank" rel="noopener noreferrer">Privacy</a>
            <a href="/terms.html" target="_blank" rel="noopener noreferrer">Terms</a>
          </nav>
        </header>

        {/* Hero + Sign-In Panel */}
        <section className="cinema-hero">
          {/* Left — editorial heading */}
          <div className="hero-left">
            <h1 className="hero-heading">
              your files.<br />
              <em>locked in.</em>
            </h1>
            <p className="hero-subline">
              Secure distributed storage, made simple.
            </p>

            <button
              className="hero-admin-link"
              onClick={() => setIsAdminMode(v => !v)}
            >
              {isAdminMode ? '← User Sign-In' : 'Admin Gateway →'}
            </button>
          </div>

          {/* Right — frosted glass sign-in panel */}
          <div className="glass-panel">
            <div className="glass-panel-header">
              <div className="glass-panel-label">
                <div className="glass-panel-count">
                  {isAdminMode ? 'Admin' : 'Sign in'}
                </div>
                <div className="glass-panel-sublabel">
                  {isAdminMode ? 'System Access' : 'to your vault'}
                </div>
              </div>
            </div>

            <div className="signin-content">
              <div>
                <div className="signin-mode-label">
                  {isAdminMode ? 'Administrator' : 'User Access'}
                </div>
                <div className="signin-mode-title">
                  {isAdminMode
                    ? 'System administration panel'
                    : 'Private Cloud Vault'}
                </div>
                <div className="signin-mode-desc" style={{ marginTop: 8 }}>
                  {isAdminMode
                    ? 'Sign in with your authorized admin Google account to manage nodes, cluster topology, and storage quotas.'
                    : 'Files are client-side AES-GCM encrypted, split into chunks, and distributed across the node network. Your keys never leave your browser.'}
                </div>
              </div>

              <div className="divider-line" />

              <button className="google-signin-btn" onClick={login}>
                <svg className="google-icon" viewBox="0 0 24 24">
                  <path fill="#8ab4f8" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#81c995" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#fdd663" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#f28b82" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <span>Continue with Google</span>
              </button>
            </div>
          </div>
        </section>

        {/* Footer strip */}
        <footer className="cinema-footer">
          <span className="cinema-footer-tag">
            Distributed · Encrypted · Resilient
          </span>
          <span className="cinema-footer-copyright">© 2026 Lockin</span>
        </footer>
      </div>

      {/* ── About Section ── */}
      <div className="about-section">
        <div className="about-block wide">
          <div className="about-block-label">About LockIn</div>
          <h3>What LockIn Does</h3>
          <p>
            LockIn is a secure, self-hosted Distributed File System designed for private cloud storage,
            end-to-end encrypted file delivery, and resilient cluster data management. Files uploaded
            to LockIn are handled through a client-side architecture that splits, encrypts, and
            distributes data across a resilient storage node network.
          </p>
          <ul>
            <li>
              <strong>Zero-Knowledge Encryption</strong> — Files are sliced into encrypted chunks
              directly within your browser using AES-GCM cryptography. Decryption keys remain
              local to your browser session; raw file contents are never transmitted unencrypted.
            </li>
            <li>
              <strong>Distributed &amp; Self-Healing Architecture</strong> — Encrypted chunks are
              stored across multiple nodes. The system monitors node health, automatically repairing
              corrupt drives and replicating data to maintain 3× redundancy.
            </li>
            <li>
              <strong>Dashboard Management</strong> — Track your storage quota, manage files, and
              securely download your encrypted data — all from the web interface.
            </li>
          </ul>
        </div>

        <div className="about-block">
          <div className="about-block-label">Google Permissions</div>
          <h3>How LockIn Uses Google Data</h3>
          <p>LockIn requests authentication via Google OAuth exclusively to verify identity and manage secure account access.</p>
          <ul>
            <li>
              <strong>Identity Verification</strong> — We use your Google profile (name and email) to authenticate login sessions securely.
            </li>
            <li>
              <strong>Access Control</strong> — Google account credentials link your personal file tree and enforce individual storage quotas.
            </li>
            <li>
              <strong>Data Privacy</strong> — LockIn does not access, read, or store any extended user data beyond basic sign-in profile information. We do not share or sell your data.
            </li>
          </ul>
        </div>

        <div className="about-block">
          <div className="about-block-label">Architecture</div>
          <h3>How It Works</h3>
          <p>
            Your files never leave your browser unencrypted. Each upload is split into 1 MiB content-addressed chunks,
            encrypted locally using the Web Crypto API (AES-256-GCM), and distributed across the storage node cluster.
            Downloads reassemble and decrypt chunks entirely within your browser session.
          </p>
          <ul>
            <li>3× replication factor across distributed storage nodes</li>
            <li>Coordinator manages chunk routing and cluster topology</li>
            <li>Self-healing: nodes automatically repaired and re-replicated on failure</li>
          </ul>
        </div>
      </div>

    </div>
  );
}
