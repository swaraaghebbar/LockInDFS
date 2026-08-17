import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const [isAdminMode, setIsAdminMode] = useState(false);

  return (
    <div className="login-page">
      <div className="login-backdrop-glow" />

      <div className="landing-container">
        {/* Left Side: Product Information and Purpose (Google Requirement) */}
        <div className="landing-info-section">
          <div className="landing-logo">
            <div className="login-logo-hex">⬡</div>
            <span className="landing-brand-title">LockIn</span>
          </div>

          <h1 className="landing-headline">
            Private, Secure, & Distributed Cloud Storage.
          </h1>
          
          <div className="landing-section">
            <h2>About LockIn</h2>
            <p className="landing-description">
              LockIn is a self-hosted Distributed File System (DFS) designed to run on personal clusters like Raspberry Pis. By combining multiple storage nodes, LockIn offers redundant, client-side encrypted, and secure cloud storage under your own control.
            </p>
          </div>

          {/* Detailed Functionality Explanation */}
          <div className="landing-section">
            <h2>Core Functionality</h2>
            <div className="landing-features-grid">
              <div className="landing-feature-card">
                <span className="feature-icon-badge">🔒</span>
                <div>
                  <h3>AES-GCM Client-Side Encryption</h3>
                  <p>All file encryption is performed directly in your browser using zero-knowledge keys. Your raw file data is never sent to the coordinator or nodes unencrypted.</p>
                </div>
              </div>

              <div className="landing-feature-card">
                <span className="feature-icon-badge">⚡</span>
                <div>
                  <h3>3x Replicated Redundancy</h3>
                  <p>Files are split into discrete chunks, encrypted, and replicated three times across different storage drives to guarantee high availability and fault tolerance.</p>
                </div>
              </div>

              <div className="landing-feature-card">
                <span className="feature-icon-badge">🛡️</span>
                <div>
                  <h3>Self-Healing Watchdog</h3>
                  <p>Node processes continuously monitor drive integrity and automatically run system tools to remount and repair corrupted filesystems on the fly.</p>
                </div>
              </div>
            </div>
          </div>

          {/* Google OAuth Data Transparency (Google Requirement) */}
          <div className="landing-section data-transparency">
            <h2>Data Transparency & Consent</h2>
            <p>
              LockIn requests access to your basic Google Account information (email address, full name, and profile picture). We collect and use this data <strong>solely</strong> for the following purposes:
            </p>
            <ul>
              <li><strong>Authentication:</strong> To verify your identity and establish a secure session.</li>
              <li><strong>Quota Management:</strong> To allocate and enforce your personal storage quota on our cluster.</li>
              <li><strong>Personalization:</strong> To display your name and profile photo within your private dashboard.</li>
            </ul>
            <p className="transparency-note">
              LockIn does not sell, trade, share, or use your personal data for advertising or tracking. All data is kept confidential within our private database.
            </p>
          </div>

          <div className="landing-legal-links">
            <a href="/privacy.html" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
            <span className="divider">•</span>
            <a href="/terms.html" target="_blank" rel="noopener noreferrer">Terms of Service</a>
          </div>
        </div>

        {/* Right Side: Interactive Login Box */}
        <div className="login-card-section">
          <div className="login-card">
            <div className="login-brand-mobile">
              <div className="login-logo-hex">⬡</div>
              <span className="login-brand-name">LOCKIN</span>
            </div>

            <h2 className="login-title">
              {isAdminMode ? 'System Admin Access' : 'Access your Files'}
            </h2>
            <p className="login-subtitle">
              {isAdminMode
                ? 'Sign in with your authorized admin Google account to manage node topology, cluster metrics, and storage nodes.'
                : 'Sign in to access your secure distributed file vault.'}
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
                <span>{isAdminMode ? 'Authenticate Admin' : 'Sign in with Google'}</span>
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
      </div>
    </div>
  );
}
