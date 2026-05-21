import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, err: any) => {
        if (err?.status === 401) return false; // 不重试登录失败
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
  },
});
