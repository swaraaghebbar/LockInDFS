import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const [isAdminMode, setIsAdminMode] = useState(false);

  return (
    <div className="login-page">
      <div className="login-backdrop-glow" />

      <div className="stacked-landing-container">
        {/* Top Container: Login Interface */}
        <div className="top-login-container">
          <div className="login-card">
            <div className="login-brand">
              <div className="login-logo-hex">⬡</div>
              <span className="login-brand-name">LOCKIN</span>
            </div>

            <h1 className="login-title">
              {isAdminMode ? 'System Admin Access' : 'Private Cloud Vault'}
            </h1>
            <p className="login-subtitle">
              {isAdminMode
                ? 'Sign in with your authorized admin Google account to manage node topology, cluster metrics, and storage nodes.'
                : 'Secure, self-hosted distributed cloud storage. Files are client-side encrypted and replicated.'}
            </p>

            <div className="login-actions">
              <button className="google-login-btn" onClick={login}>
                <svg className="google-icon" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
                <span>{isAdminMode ? 'Authenticate Admin Account' : 'Sign in with Google'}</span>
              </button>
            </div>

            <div className="login-footer">
              {isAdminMode ? (
                <button
                  className="admin-toggle-link"
                  onClick={() => setIsAdminMode(false)}
                >
                  ← Back to User Login
                </button>
              ) : (
                <button
                  className="admin-toggle-link"
                  onClick={() => setIsAdminMode(true)}
                >
                  Admin Gateway
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Bottom Container: Comprehensive System Documentation */}
        <div className="bottom-info-container">
          <div className="info-header">
            <h2>LockIn Technical Documentation & System Overview</h2>
            <p>LockIn is a secure, self-hosted Distributed File System (DFS) that orchestrates cluster-wide encrypted storage across personal hardware nodes.</p>
          </div>

          <div className="info-grid">
            {/* Section 1: Core Architecture */}
            <div className="info-block">
              <h3>1. System Architecture & Operation</h3>
              <p>
                LockIn operates on a three-tier model comprising a client-side interface, a centralized metadata Coordinator, and distributed storage nodes:
              </p>
              <ul>
                <li><strong>Vite React Client:</strong> Runs in the user's browser, handling file splitting (chunking) and zero-knowledge client-side encryption.</li>
                <li><strong>FastAPI Coordinator:</strong> A central server that manages SQLite metadata schemas, registers file chunk maps, tracks storage node health, and delegates read/write permissions.</li>
                <li><strong>Python Storage Nodes:</strong> Running on target machines (such as Raspberry Pis), these daemons serve upload/download requests for specific chunks and interface with mounted storage drives.</li>
              </ul>
            </div>

            {/* Section 2: Cryptographic Security & Redundancy */}
            <div className="info-block">
              <h3>2. Cryptography & 3x Redundancy</h3>
              <p>
                Security and durability are handled systematically at the client level:
              </p>
              <ul>
                <li><strong>AES-GCM Encryption:</strong> Files are split into three equal chunks and encrypted in-browser using Web Crypto APIs. The Coordinator and storage nodes never receive unencrypted file contents or private decryption keys.</li>
                <li><strong>Redundancy & Failover:</strong> Each encrypted chunk is replicated 3 times across separate node drives. If a drive fails or is unplugged, the Coordinator automatically redirects file requests to alternative active replicas.</li>
                <li><strong>Auto-Healing Watchdogs:</strong> Storage nodes run automated local processes that monitor disk mount integrity and execute self-healing repairs (NTFS auto-repair) for filesystem consistency.</li>
              </ul>
            </div>

            {/* Section 3: Data Access & OAuth Scopes (Required for Google Review) */}
            <div className="info-block full-width">
              <h3>3. Data Privacy & Google OAuth Usage Policy</h3>
              <p>
                LockIn requests user authentication via Google OAuth. Here is the transparent breakdown of the data we collect and why we require it:
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Requested Scope / Data</th>
                    <th>Exact Purpose & Application Functionality</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Google Email Address</strong></td>
                    <td>To create a unique account index, authorize file dashboard access, and enforce personal storage quotas (e.g., 1 GB allocation).</td>
                  </tr>
                  <tr>
                    <td><strong>Full Name & Profile Image URL</strong></td>
                    <td>To customize and personalize your session dashboard when logged into the client application.</td>
                  </tr>
                  <tr>
                    <td><strong>OAuth OpenID Identifiers</strong></td>
                    <td>To issue and validate signed session cookies (<code>dfs_session</code>) for secure coordinator API requests.</td>
                  </tr>
                </tbody>
              </table>
              <p className="privacy-assertion">
                <strong>Data Protection Guarantee:</strong> LockIn is a private, zero-tracking application. We do not sell, distribute, share, or analyze your personal profile data. All metadata is stored locally within our private database.
              </p>
            </div>
          </div>

          <div className="landing-legal-links">
            <a href="/privacy.html" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
            <span className="divider">•</span>
            <a href="/terms.html" target="_blank" rel="noopener noreferrer">Terms of Service</a>
          </div>
        </div>
      </div>
    </div>
  );
}
