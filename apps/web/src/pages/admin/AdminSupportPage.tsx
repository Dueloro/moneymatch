import { useEffect, useState } from 'react';

import {
  useAdminSupportThread,
  useAdminSupportThreads,
  useReplyToSupport,
} from '../../hooks/useAdmin';
import { styles } from './adminStyles';
import { AdminError, AdminLoading } from './AdminStates';

export function AdminSupportPage() {
  const threads = useAdminSupportThreads();
  const [selected, setSelected] = useState<string | null>(null);
  const thread = useAdminSupportThread(selected);
  const reply = useReplyToSupport();
  const [body, setBody] = useState('');

  useEffect(() => {
    if (!selected && threads.data?.[0]) setSelected(threads.data[0].conversation_id);
  }, [selected, threads.data]);

  async function send() {
    if (!selected || !body.trim()) return;
    await reply.mutateAsync({ conversationId: selected, body: body.trim() });
    setBody('');
  }

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Support</h1>
      {threads.isLoading && <AdminLoading bare />}
      {threads.isError && (
        <AdminError
          bare
          what="support threads"
          onRetry={() => void threads.refetch()}
        />
      )}
      {threads.data?.length === 0 && <p style={styles.ok}>No support threads.</p>}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(240px, 340px) minmax(0, 1fr)',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <div style={{ border: '1px solid #d4d4d8' }}>
          {(threads.data ?? []).map((item) => (
            <button
              key={item.conversation_id}
              type="button"
              onClick={() => setSelected(item.conversation_id)}
              style={{
                display: 'block',
                width: '100%',
                border: 0,
                borderBottom: '1px solid #e4e4e7',
                padding: 10,
                textAlign: 'left',
                background: selected === item.conversation_id ? '#e4e4e7' : '#fff',
                color: '#111',
                cursor: 'pointer',
              }}
            >
              <strong>{item.username ?? 'Player'}</strong>{' '}
              {item.awaiting_reply && <span style={styles.alert}>needs reply</span>}
              <div style={{ color: '#52525b', marginTop: 3 }}>
                {item.last_message_preview ?? 'No message yet'}
              </div>
            </button>
          ))}
        </div>
        <section>
          {thread.isLoading && selected && <AdminLoading bare />}
          {thread.isError && (
            <AdminError
              bare
              what="support thread"
              onRetry={() => void thread.refetch()}
            />
          )}
          {thread.data && (
            <>
              <p>
                <strong>{thread.data.username ?? 'Player'}</strong> ·{' '}
                {thread.data.email ?? 'no email'}
              </p>
              <div
                style={{
                  border: '1px solid #d4d4d8',
                  maxHeight: '55vh',
                  overflowY: 'auto',
                  padding: 10,
                }}
              >
                {thread.data.messages.map((message) => (
                  <div
                    key={message.id}
                    style={{
                      margin: '0 0 10px',
                      padding: 8,
                      background:
                        message.sender === 'user'
                          ? '#f4f4f5'
                          : message.sender === 'support'
                            ? '#e0f2fe'
                            : '#fafafa',
                    }}
                  >
                    <strong>{message.sender}</strong>{' '}
                    <span style={{ color: '#71717a' }}>
                      {new Date(message.created_at).toLocaleString()}
                      {message.source ? ` · ${message.source}` : ''}
                    </span>
                    <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                      {message.body}
                    </div>
                  </div>
                ))}
              </div>
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="Reply in-app and by email"
                style={{
                  ...styles.input,
                  display: 'block',
                  width: '100%',
                  marginTop: 10,
                }}
              />
              <button
                type="button"
                style={{ ...styles.button, marginTop: 8 }}
                disabled={reply.isPending || !body.trim()}
                onClick={() => void send()}
              >
                {reply.isPending ? 'Sending…' : 'Send reply'}
              </button>
              {reply.isError && <p style={styles.alert}>{reply.error.message}</p>}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
