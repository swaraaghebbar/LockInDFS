import { formatBytes } from '../api.js';

// Node metadata map — from config.py
const NODE_META = {
  Pi_Node_1:      { desc: 'Pi partition A' },
  Pi_Node_2:      { desc: 'Pi partition B' },
  Sandisk_Node_1: { desc: 'SanDisk Pendrive Partition 1' },
  Sandisk_Node_2: { desc: 'SanDisk Pendrive Partition 2' },
  Tag_Node_1:     { desc: 'Tag HDD Partition 1' },
  Tag_Node_2:     { desc: 'Tag HDD Partition 2' },
  Tag_Node_3:     { desc: 'Tag HDD Partition 3' },
};

function UsageBar({ used, total }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  const isDanger = pct > 80;
  return (
    <div className="progress-bar">
      <div
        className={`progress-fill ${isDanger ? 'danger' : ''}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function NodeCard({ nodeId, data }) {
  const meta = NODE_META[nodeId] || { desc: nodeId };
  const ok = data?.status === 'ok';
  const unmounted = data?.status === 'unmounted';
  const absent = data?.status === 'absent';
  const blobs = data?.blob_count ?? '—';
  const totalBytes = data?.total_bytes ?? 0;     // blob data THIS node stores
  const freeBytes  = data?.free_space ?? 0;      // free on the partition
  const diskTotal  = data?.disk_total ?? 0;      // total capacity of partition
  // Used space on the partition = disk_total - free_space
  const diskUsed   = diskTotal > 0 ? diskTotal - freeBytes : totalBytes;

  // Status label and colour
  let statusLabel = 'offline';
  let statusColor = 'var(--red)';
  if (ok) {
    statusLabel = 'healthy';
    statusColor = 'var(--green)';
  } else if (unmounted) {
    statusLabel = 'unmounted';
    statusColor = 'var(--amber, #f59e0b)';
  } else if (absent) {
    statusLabel = 'not connected';
    statusColor = 'var(--text-dim)';
  }

  return (
    <div className={`node-card ${ok ? 'ok' : 'dead'}`}>
      <div className="node-header">
        <div className={`node-status-dot ${ok ? 'ok' : 'dead'}`} />
        <span className="node-name">{nodeId}</span>
      </div>

      <div className="node-stats">
        <div className="node-stat-row">
          <span className="node-stat-label">Status</span>
          <span className="node-stat-value" style={{ color: statusColor }}>
            {statusLabel}
          </span>
        </div>
        <div className="node-stat-row">
          <span className="node-stat-label">Blobs</span>
          <span className="node-stat-value">{blobs}</span>
        </div>
        <div className="node-stat-row">
          <span className="node-stat-label">Data stored</span>
          <span className="node-stat-value">{formatBytes(totalBytes)}</span>
        </div>
        <div className="node-stat-row">
          <span className="node-stat-label">Free space</span>
          <span className="node-stat-value">{formatBytes(freeBytes)}</span>
        </div>
        {diskTotal > 0 && (
          <div className="node-stat-row">
            <span className="node-stat-label">Disk capacity</span>
            <span className="node-stat-value">{formatBytes(diskTotal)}</span>
          </div>
        )}
        {ok && <UsageBar used={diskUsed} total={diskTotal || (freeBytes + totalBytes)} />}
        <p className="node-desc">{meta.desc}</p>
      </div>
    </div>
  );
}

export default function ClusterPanel({ cluster }) {
  if (!cluster) {
    return (
      <div className="node-grid">
        {['n1','n2','n3','n4','n5','n6','n7'].map(id => (
          <div key={id} className="node-card">
            <div className="skeleton" style={{ height: 120 }} />
          </div>
        ))}
      </div>
    );
  }

  const nodes = cluster.nodes || {};
  return (
    <div className="node-grid">
      {Object.entries(nodes).map(([nodeId, data]) => (
        <NodeCard key={nodeId} nodeId={nodeId} data={data} />
      ))}
    </div>
  );
}
