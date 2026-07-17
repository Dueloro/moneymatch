import { useState } from 'react';

import { useAdminFlags, useUpdateFlag } from '../../hooks/useAdmin';
import { styles } from './adminStyles';

/** Kill switches + config. Toggling is live (server reads flags per-request). */
export function AdminFlagsPage() {
  const flags = useAdminFlags();
  const update = useUpdateFlag();
  const [geoText, setGeoText] = useState<string | null>(null);

  if (flags.isLoading) return <div style={styles.page}>Loading…</div>;
  if (flags.error) return <div style={styles.page}>Failed to load flags.</div>;

  const rows = flags.data ?? [];
  const geo = rows.find((f) => f.key === 'geo_config');
  const geoStates = ((geo?.payload?.excluded_states as string[]) ?? []).join(', ');

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Feature flags &amp; kill switches</h1>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Key</th>
            <th style={styles.th}>Enabled</th>
            <th style={styles.th}>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows
            .filter((f) => f.key !== 'geo_config')
            .map((f) => (
              <tr key={f.key}>
                <td style={styles.td}>{f.key}</td>
                <td style={styles.td}>
                  <span style={f.enabled ? styles.ok : styles.alert}>
                    {String(f.enabled)}
                  </span>
                </td>
                <td style={styles.td}>
                  <button
                    style={styles.button}
                    disabled={update.isPending}
                    onClick={() => update.mutate({ key: f.key, enabled: !f.enabled })}
                  >
                    {f.enabled ? 'Disable' : 'Enable'}
                  </button>
                </td>
              </tr>
            ))}
        </tbody>
      </table>

      <h1 style={{ ...styles.h1, marginTop: 24 }}>geo_config excluded states</h1>
      <p>Comma-separated 2-letter codes. Blocked from staking server-side.</p>
      <input
        style={{ ...styles.input, width: 400 }}
        value={geoText ?? geoStates}
        onChange={(e) => setGeoText(e.target.value)}
      />
      <button
        style={{ ...styles.button, marginLeft: 8 }}
        disabled={update.isPending}
        onClick={() => {
          const excluded_states = (geoText ?? geoStates)
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean);
          update.mutate(
            { key: 'geo_config', payload: { excluded_states } },
            { onSuccess: () => setGeoText(null) },
          );
        }}
      >
        Save geo_config
      </button>
    </div>
  );
}
