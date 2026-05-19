import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { authApi } from '@/api/authClient';
import type { ListResponse } from '@/api/types';

type Params = Record<string, unknown> | undefined;

// Desktop-backend user list (source of truth for registration approval).
export function useAuthUsers() {
  return useQuery({ queryKey: ['auth', 'users'], queryFn: () => authApi.users() });
}

// Generic resource list
export function useResource<T>(
  resource: string,
  params?: Params,
  options?: Partial<UseQueryOptions<ListResponse<T>>>,
) {
  return useQuery({
    queryKey: ['data', resource, params],
    queryFn: () => endpoints.listResource<T>(resource, params),
    ...options,
  });
}

export function useCreators(params?: Params) {
  return useQuery({ queryKey: ['data', 'creators', params], queryFn: () => endpoints.creators(params) });
}
export function useProducts(params?: Params) {
  return useQuery({ queryKey: ['data', 'products', params], queryFn: () => endpoints.products(params) });
}
export function useOutreach(params?: Params) {
  return useQuery({ queryKey: ['data', 'outreach', params], queryFn: () => endpoints.outreach(params) });
}
export function useProductImages(params?: Params) {
  return useQuery({ queryKey: ['data', 'product_images', params], queryFn: () => endpoints.productImages(params) });
}
export function useCategories(params?: Params) {
  return useQuery({ queryKey: ['data', 'categories', params], queryFn: () => endpoints.categories(params) });
}
export function useStaff(params?: Params) {
  return useQuery({ queryKey: ['data', 'staff', params], queryFn: () => endpoints.staff(params) });
}
export function useAuditLog(params?: Params) {
  return useQuery({ queryKey: ['data', 'audit_log', params], queryFn: () => endpoints.auditLog(params) });
}
export function useKeywordSnapshots(params?: Params) {
  return useQuery({ queryKey: ['data', 'keyword_snapshots', params], queryFn: () => endpoints.keywordSnapshots(params) });
}

export function useWebhooks(params?: Params) {
  return useQuery({ queryKey: ['data', 'webhooks', params], queryFn: () => endpoints.webhooks(params) });
}
export function useDepartments(params?: Params) {
  return useQuery({ queryKey: ['data', 'departments', params], queryFn: () => endpoints.departments(params) });
}
export function useNotifications(params?: Params) {
  return useQuery({ queryKey: ['data', 'notifications', params], queryFn: () => endpoints.notifications(params) });
}
export function useApiMetrics(params?: Params) {
  return useQuery({ queryKey: ['data', 'api_metrics', params], queryFn: () => endpoints.apiMetrics(params) });
}
export function useLlmTokenUsages(params?: Params) {
  return useQuery({ queryKey: ['data', 'llm_token_usages', params], queryFn: () => endpoints.llmTokenUsages(params) });
}
export function useBusinessMetricsDaily(params?: Params) {
  return useQuery({ queryKey: ['data', 'business_metrics_daily', params], queryFn: () => endpoints.businessMetricsDaily(params) });
}
export function useDepartmentDashboardSummary() {
  return useQuery({ queryKey: ['dashboard', 'department-summary'], queryFn: () => endpoints.departmentDashboardSummary() });
}

export function useSystemMetrics() {
  return useQuery({
    queryKey: ['admin', 'system-metrics'],
    queryFn: () => endpoints.systemMetrics(),
    refetchInterval: 10_000,
  });
}

export function useUsers() {
  return useQuery({ queryKey: ['auth', 'users'], queryFn: () => endpoints.users() });
}

export function useLlmProviders() {
  return useQuery({ queryKey: ['llm', 'providers'], queryFn: () => endpoints.llmProviders() });
}

export function useNamedQueries() {
  return useQuery({ queryKey: ['queries'], queryFn: () => endpoints.queries() });
}

export function useNamedQuery<T>(name: string, params?: Params, enabled = true) {
  return useQuery({
    queryKey: ['nq', name, params],
    queryFn: () => endpoints.runQuery<T>(name, params),
    enabled,
  });
}

export function useVersion() {
  return useQuery({ queryKey: ['version'], queryFn: () => endpoints.version() });
}

export function useResources() {
  return useQuery({ queryKey: ['resources'], queryFn: () => endpoints.resources() });
}
