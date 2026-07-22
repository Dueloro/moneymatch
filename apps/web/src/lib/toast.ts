// Tiny framework-agnostic toast bus. Any module (including the React Query
// client, which lives outside the component tree) can call `toast.*`; the
// <Toaster /> mounted once at the root subscribes and renders the messages.

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastMessage {
  id: number;
  kind: ToastKind;
  text: string;
}

type Listener = (message: ToastMessage) => void;

const listeners = new Set<Listener>();
let seq = 0;

function emit(kind: ToastKind, text: string): void {
  const message: ToastMessage = { id: ++seq, kind, text };
  listeners.forEach((listener) => listener(message));
}

export const toast = {
  success: (text: string) => emit('success', text),
  error: (text: string) => emit('error', text),
  info: (text: string) => emit('info', text),
};

/** Subscribe to toast emissions. Returns an unsubscribe function. */
export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
