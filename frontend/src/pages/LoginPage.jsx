import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const [isAdminMode, setIsAdminMode] = useState(false);

  return (
    <div className="login-page">
      <div className="login-backdrop-glow" />

      <div className="login-card">
        <div className="login-brand">
          <div className="login-logo-hex">⬡</div>
          <span className="login-brand-name">LOCKIN DFS</span>
        </div>

        <h1 className="login-title">
          {isAdminMode ? 'System Admin Access' : 'Encrypted Cloud Storage'}
        </h1>
        <p className="login-subtitle">
          {isAdminMode
            ? 'Sign in with your authorized admin Google account to manage node topology, cluster metrics, and storage nodes.'
            : 'Zero-trust distributed file storage. Files are client-side chunked, end-to-end encrypted, and replicated.'}
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
            <span>{isAdminMode ? 'Authenticate Admin Account' : 'Continue with Google'}</span>
          </button>
        </div>

        <div className="login-features">
          <div className="feature-item">
            <span className="feature-icon">🔒</span>
            <span>AES-GCM Encryption</span>
          </div>
          <div className="feature-item">
            <span className="feature-icon">⚡</span>
            <span>3× Chunk Replication</span>
          </div>
          <div className="feature-item">
            <span className="feature-icon">🛡️</span>
            <span>Zero-Knowledge Decryption</span>
          </div>
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
  );
}
