import { useQuery, useMutation } from '@tanstack/react-query';
import { authApi } from '@/api/authClient';

const AUTH_KEY = ['auth', 'me'];

export function useAuthMe() {
  return useQuery({
    queryKey: AUTH_KEY,
    queryFn: () => authApi.me(),
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.login(username, password),
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () => authApi.logout(),
  });
}
