import { MutationCache, QueryClient } from '@tanstack/react-query';

import { toast } from './toast';

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
