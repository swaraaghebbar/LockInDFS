import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../AuthContext.jsx';
import { fetchCluster, fetchFiles, fetchAdminUsers, formatBytes } from '../api.js';
import ClusterPanel from '../components/ClusterPanel.jsx';

function UserTable({ users, loading }) {
  if (loading) {
    return (
      <div className="skeleton-wrap">
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton" style={{ height: 48, marginBottom: 8 }} />
        ))}
      </div>
    );
  }

  if (!users.length) {
    return (
      <div className="empty-state">
        <span className="empty-icon">👥</span>
        <p className="empty-text">No registered users found</p>
      </div>
    );
  }

  return (
    <div className="file-table-wrap">
      <table className="file-table">
        <thead>
          <tr>
            <th>User</th>
            <th>Email</th>
            <th>Storage Used</th>
            <th>Quota</th>
            <th>Usage</th>
            <th>Registered</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => {
            const used = u.storage_used || 0;
            const quota = u.storage_quota || (1024 * 1024 * 1024);
            const pct = Math.min(100, Math.round((used / quota) * 100));

            return (
              <tr key={u.id}>
                <td>
                  <div className="user-cell">
                    <img
                      src={u.picture || 'https://via.placeholder.com/32'}
                      alt={u.name}
                      className="user-avatar-sm"
                      onError={e => { e.target.src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(u.name); }}
                    />
                    <span className="user-cell-name">{u.name || 'User'}</span>
                  </div>
                </td>
                <td><span className="file-time">{u.email}</span></td>
                <td><span className="file-size">{formatBytes(used)}</span></td>
                <td><span className="file-size">{formatBytes(quota)}</span></td>
                <td style={{ minWidth: 120 }}>
                  <div className="user-quota-bar">
                    <div
                      className={`progress-fill ${pct > 80 ? 'danger' : ''}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="pct-label">{pct}%</span>
                </td>
                <td><span className="file-time">{new Date(u.created_at).toLocaleDateString()}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState('overview');
  const [cluster, setCluster] = useState(null);
  const [files, setFiles] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  const loadData = useCallback(async () => {
    try {
      const [clusterData, filesData, usersData] = await Promise.all([
        fetchCluster().catch(() => null),
        fetchFiles().catch(() => ({ files: [] })),
        fetchAdminUsers().catch(() => ({ users: [] })),
      ]);
      setCluster(clusterData);
      setFiles(filesData.files || []);
      setAdminUsers(usersData.users || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    pollRef.current = setInterval(() => loadData(), 5000);
    return () => clearInterval(pollRef.current);
  }, [loadData]);

  const nodes = cluster?.nodes || {};
  const nodeList = Object.values(nodes);
  const healthyCount = nodeList.filter(n => n?.status === 'ok').length;
  const totalNodes = nodeList.length;
  const totalClusterBytes = nodeList.reduce((s, n) => s + (n?.total_bytes ?? 0), 0);

  return (
    <div className="app">
      {/* ── Admin Header ── */}
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">⬡</div>
          <span>DFS Admin Console</span>
        </div>

        <div className="header-spacer" />

        <div className="header-badge admin">
          <div className="dot" />
          {healthyCount}/{totalNodes} Nodes Healthy
        </div>

        <div className="header-user-profile">
          <img src={user?.picture} alt={user?.name} className="user-avatar-header" />
          <div className="header-user-details">
            <span className="header-user-name">{user?.name}</span>
            <span className="header-user-badge">Admin</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout} title="Sign Out">
            Sign Out
          </button>
        </div>
      </header>

      {/* ── Admin Sidebar ── */}
      <nav className="sidebar">
        <div className="sidebar-section-label">Management</div>
        <div
          className={`nav-item ${tab === 'overview' ? 'active' : ''}`}
          onClick={() => setTab('overview')}
        >
          <span className="icon">📊</span> Overview
        </div>
        <div
          className={`nav-item ${tab === 'cluster' ? 'active' : ''}`}
          onClick={() => setTab('cluster')}
        >
          <span className="icon">⬡</span> Storage Nodes
        </div>
        <div
          className={`nav-item ${tab === 'users' ? 'active' : ''}`}
          onClick={() => setTab('users')}
        >
          <span className="icon">👥</span> Users ({adminUsers.length})
        </div>
      </nav>

      {/* ── Main View ── */}
      <main className="main">
        {tab === 'overview' && (
          <>
            <div>
              <h1 className="page-title">Cluster Telemetry</h1>
              <p className="page-subtitle">Live hardware node metrics, storage allocations, and registered user quotas</p>
            </div>

            <div className="stat-row">
              <div className="stat-card">
                <span className="stat-label">Active Storage Nodes</span>
                <span className={`stat-value ${healthyCount === totalNodes ? 'green' : 'amber'}`}>
                  {loading ? '—' : `${healthyCount}/${totalNodes}`}
                </span>
                <span className="stat-sub">online and responding</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Cluster Blobs</span>
                <span className="stat-value blue">{loading ? '—' : formatBytes(totalClusterBytes)}</span>
                <span className="stat-sub">across all physical drives</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Registered Users</span>
                <span className="stat-value purple">{loading ? '—' : adminUsers.length}</span>
                <span className="stat-sub">Google OAuth accounts</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Files Stored</span>
                <span className="stat-value green">{loading ? '—' : files.length}</span>
                <span className="stat-sub">user uploads</span>
              </div>
            </div>

            <div className="card">
              <div className="section-header">
                <span className="section-title">Physical Storage Nodes</span>
                <span className="section-meta">Auto-refreshes every 5s</span>
              </div>
              <ClusterPanel cluster={cluster} />
            </div>
          </>
        )}

        {tab === 'cluster' && (
          <>
            <div>
              <h1 className="page-title">Node Topology & Mount Health</h1>
              <p className="page-subtitle">Inspect individual Pi partitions, external USB drives, and disk usage</p>
            </div>
            <div className="card">
              <ClusterPanel cluster={cluster} />
            </div>
          </>
        )}

        {tab === 'users' && (
          <>
            <div>
              <h1 className="page-title">Registered Users</h1>
              <p className="page-subtitle">User account roster and storage space allocation (Privacy-preserved)</p>
            </div>
            <div className="card">
              <UserTable users={adminUsers} loading={loading} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
