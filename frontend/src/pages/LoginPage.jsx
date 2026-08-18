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
              <span className="login-brand-name">LockIn</span>
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
            <h2>About LockIn</h2>
            <p>LockIn is a secure, self-hosted Distributed File System (DFS) designed for private cloud storage, end-to-end encrypted file delivery, and resilient cluster data management.</p>
          </div>

          <div className="info-grid">
            {/* Section 1: What LockIn Does */}
            <div className="info-block full-width">
              <h3>What LockIn Does</h3>
              <p>LockIn provides users with a zero-knowledge cloud storage environment. Files uploaded to LockIn are handled through a client-side architecture that splits, encrypts, and distributes data across a resilient storage node network.</p>
              <ul>
                <li><strong>Zero-Knowledge Encryption:</strong> Files are sliced into encrypted chunks directly within your web browser using client-side AES-GCM cryptography. Decryption keys remain local to your browser session; raw file contents are never transmitted in unencrypted form.</li>
                <li><strong>Distributed & Self-Healing Architecture:</strong> Encrypted data chunks are stored across multiple distributed storage nodes. The system continuously monitors node health, automatically repairing corrupt drives and replicating chunks to maintain 3x data redundancy.</li>
                <li><strong>Storage & Dashboard Management:</strong> Users can manage files, track personal storage quotas, and securely download or assemble encrypted file chunks back into original files directly from the web dashboard.</li>
              </ul>
            </div>

            {/* Section 2: Google Data Usage */}
            <div className="info-block full-width">
              <h3>How LockIn Uses Google Data & Permissions</h3>
              <p>LockIn requests authentication access through Google OAuth exclusively to verify user identity and manage secure account access.</p>
              <ul>
                <li><strong>Identity Verification:</strong> We use your Google primary profile information (such as your name and email address) to authenticate your login sessions securely.</li>
                <li><strong>Access Control & Quota Management:</strong> Google account credentials are used to link your personal file tree and enforce individual storage quota allocations (e.g., 1 GB per user).</li>
                <li><strong>Data Privacy:</strong> LockIn does not access, read, or store any extended user data from your Google Account beyond basic sign-in profile information. We do not share, sell, or analyze your user data for advertising or tracking purposes.</li>
              </ul>
            </div>
          </div>

          <div className="info-footer-links">
            <h3>Links & Resources</h3>
            <div className="landing-legal-links">
              <a href="/privacy.html" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
              <span className="divider">•</span>
              <a href="/terms.html" target="_blank" rel="noopener noreferrer">Terms of Service</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
