import { MutationCache, QueryClient } from '@tanstack/react-query';

import { toast } from './toast';

// Client state = TanStack Query cache (01-architecture §1). Live surfaces set
// their own refetchInterval; defaults stay conservative.
//
// Every failed mutation surfaces a toast by default, so a money action never
// fails silently. Mutations that want a custom message can still throw one
// (the thrown Error's message is what shows); those that render their own
// inline error keep doing so on top of this safety net.
export const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (error) => {
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Something went wrong. Please try again.';
      toast.error(message);
    },
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
    },
  },
});
