import { QueryClient } from '@tanstack/react-query';

// Client state = TanStack Query cache (01-architecture §1). Live surfaces set
// their own refetchInterval; defaults stay conservative.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
    },
  },
});
