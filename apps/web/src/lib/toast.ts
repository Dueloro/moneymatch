/** `success` carries a lime dot, so keep it for points coming your way. */
export type ToastKind = 'success' | 'error' | 'info' | 'neutral';

export interface ToastAction {
  label: string;
  to: string;
}

export interface ToastMessage {
  id: number;
  kind: ToastKind;
  text: string;
  action?: ToastAction;
}

type Listener = (message: ToastMessage) => void;

const listeners = new Set<Listener>();
let seq = 0;

function emit(kind: ToastKind, text: string, action?: ToastAction): void {
  const message: ToastMessage = { id: ++seq, kind, text, action };
  listeners.forEach((listener) => listener(message));
}

export const toast = {
  success: (text: string, action?: ToastAction) => emit('success', text, action),
  error: (text: string) => emit('error', text),
  info: (text: string) => emit('info', text),
  neutral: (text: string, action?: ToastAction) => emit('neutral', text, action),
};

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
