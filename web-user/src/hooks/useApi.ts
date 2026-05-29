import { useQuery, useMutation, type UseQueryOptions } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';

type Params = Record<string, unknown> | undefined;

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: () => endpoints.me() });
}

export function useAppStatus() {
  return useQuery({ queryKey: ['app', 'status'], queryFn: () => endpoints.appStatus() });
}

export function useDbStats() {
  return useQuery({
    queryKey: ['db', 'stats'],
    queryFn: () => endpoints.dbStats(),
    refetchInterval: 10_000,
  });
}

export function useDbStatus() {
  return useQuery({ queryKey: ['db', 'status'], queryFn: () => endpoints.dbStatus() });
}

export function useBusinessDashboard() {
  return useQuery({ queryKey: ['biz', 'dashboard'], queryFn: () => endpoints.businessDashboard() });
}

export function useCreators(params?: Params, opts?: Partial<UseQueryOptions<any>>) {
  return useQuery({
    queryKey: ['creators', params],
    queryFn: () => endpoints.creators(params),
    ...opts,
  });
}

export function useRecommended(params?: Params) {
  return useQuery({
    queryKey: ['creators', 'recommended', params],
    queryFn: () => endpoints.creatorsRecommended(params),
  });
}

export function useCreator(id?: string | number) {
  return useQuery({
    queryKey: ['creator', id],
    queryFn: () => endpoints.creator(id!),
    enabled: id !== undefined && id !== null && String(id).length > 0,
  });
}

export function useReviewTasks(params?: Params) {
  return useQuery({
    queryKey: ['review-tasks', params],
    queryFn: () => endpoints.reviewTasks(params),
  });
}

export function useExtensionStatus() {
  return useQuery({
    queryKey: ['extension', 'status'],
    queryFn: () => endpoints.extensionStatus(),
    refetchInterval: 15_000,
  });
}

export function useRunProgress(workerId?: string) {
  return useQuery({
    queryKey: ['run-progress', workerId],
    queryFn: () => endpoints.runProgress(workerId),
    refetchInterval: 5_000,
  });
}

export function useKeywordsDashboard() {
  return useQuery({
    queryKey: ['keywords', 'dashboard'],
    queryFn: () => endpoints.keywordsDashboard(),
  });
}

export function useAssistantInfo() {
  return useQuery({ queryKey: ['assistant', 'info'], queryFn: () => endpoints.assistantInfo() });
}

export function useAssistantChat() {
  return useMutation({
    mutationFn: ({ message, history }: { message: string; history?: any[] }) =>
      endpoints.assistantChat(message, history),
  });
}

export function useRunPipeline() {
  return useMutation({ mutationFn: () => endpoints.runPipeline() });
}

// ---------- Extension / Collection ----------
export function useExtensionSessions() {
  return useQuery({
    queryKey: ['extension', 'sessions'],
    queryFn: () => endpoints.extensionSessions(),
    refetchInterval: 15_000,
  });
}

export function usePostExtensionCommand() {
  return useMutation({ mutationFn: (body: Parameters<typeof endpoints.postExtensionCommand>[0]) => endpoints.postExtensionCommand(body) });
}

export function useRecentObservations(limit = 50) {
  return useQuery({
    queryKey: ['collector', 'recent-observations', limit],
    queryFn: () => endpoints.recentObservations(limit),
    refetchInterval: 10_000,
  });
}

// ---------- Outreach ----------
export function useOutreachTemplates(params?: Params) {
  return useQuery({ queryKey: ['outreach', 'templates', params], queryFn: () => endpoints.outreachTemplates(params) });
}
export function useCreateOutreachTemplate() {
  return useMutation({ mutationFn: (body: Parameters<typeof endpoints.createOutreachTemplate>[0]) => endpoints.createOutreachTemplate(body) });
}
export function usePatchOutreachTemplate() {
  return useMutation({ mutationFn: ({ id, body }: { id: string; body: Parameters<typeof endpoints.patchOutreachTemplate>[1] }) => endpoints.patchOutreachTemplate(id, body) });
}
export function useDeleteOutreachTemplate() {
  return useMutation({ mutationFn: (id: string) => endpoints.deleteOutreachTemplate(id) });
}

export function usePreviewOutreach() {
  return useMutation({
    mutationFn: ({ creator_id, body }: { creator_id: string | number; body: Parameters<typeof endpoints.previewOutreach>[1] }) =>
      endpoints.previewOutreach(creator_id, body),
  });
}
export function useCreateDraft() {
  return useMutation({ mutationFn: (body: Parameters<typeof endpoints.createDraft>[0]) => endpoints.createDraft(body) });
}
export function usePatchDraft() {
  return useMutation({ mutationFn: ({ id, body }: { id: string; body: Parameters<typeof endpoints.patchDraft>[1] }) => endpoints.patchDraft(id, body) });
}
export function useSendDraft() {
  return useMutation({ mutationFn: ({ id, body }: { id: string; body?: Parameters<typeof endpoints.sendDraft>[1] }) => endpoints.sendDraft(id, body || { confirm: true }) });
}
export function useOutreachHistory(creator_id?: string | number, params?: Params) {
  return useQuery({
    queryKey: ['outreach', 'history', creator_id, params],
    queryFn: () => endpoints.outreachHistory(creator_id!, params),
    enabled: !!creator_id,
  });
}

export function useAcquireOutreachLock() {
  return useMutation({
    mutationFn: ({ creator_id, body }: { creator_id: string | number; body?: Parameters<typeof endpoints.acquireOutreachLock>[1] }) =>
      endpoints.acquireOutreachLock(creator_id, body),
  });
}

export function useHeartbeatOutreachLock() {
  return useMutation({
    mutationFn: ({ lock_id, body }: { lock_id: string; body?: Parameters<typeof endpoints.heartbeatOutreachLock>[1] }) =>
      endpoints.heartbeatOutreachLock(lock_id, body),
  });
}

export function useReleaseOutreachLock() {
  return useMutation({
    mutationFn: ({ lock_id, body }: { lock_id: string; body?: Parameters<typeof endpoints.releaseOutreachLock>[1] }) =>
      endpoints.releaseOutreachLock(lock_id, body),
  });
}

export function useOutreachArchive(params?: Params) {
  return useQuery({
    queryKey: ['outreach', 'archive', params],
    queryFn: () => endpoints.outreachArchive(params),
  });
}

export function useOutreachArchiveDetail(id?: string | null) {
  return useQuery({
    queryKey: ['outreach', 'archive-detail', id],
    queryFn: () => endpoints.outreachArchiveDetail(id!),
    enabled: Boolean(id),
  });
}

export function useOutreachTracking(params?: Params) {
  return useQuery({
    queryKey: ['outreach', 'tracking', params],
    queryFn: () => endpoints.outreachTracking(params),
  });
}

export function usePatchOutreachTrackingStatus() {
  return useMutation({
    mutationFn: ({ creator_id, ...body }: { creator_id: string | number; current_status: string; note?: string }) =>
      endpoints.patchOutreachTrackingStatus(creator_id, body),
  });
}

export function useGenerateTkScript() {
  return useMutation({
    mutationFn: ({ creator_id, ...body }: { creator_id: string | number; commission: number; strategy?: string; custom_prompt?: string; prompt_id?: string; product_asset_id?: string }) =>
      endpoints.generateTkScript(creator_id, body),
  });
}

export function useProductAssets(creator_id?: string | number) {
  return useQuery({
    queryKey: ['outreach', 'product-assets', creator_id],
    queryFn: () => endpoints.listProductAssets(creator_id),
    enabled: creator_id !== undefined && creator_id !== null && String(creator_id).length > 0,
  });
}

export function useCreateProductAsset() {
  return useMutation({ mutationFn: (body: Parameters<typeof endpoints.createProductAsset>[0]) => endpoints.createProductAsset(body) });
}

export function useDeleteProductAsset() {
  return useMutation({ mutationFn: (id: string) => endpoints.deleteProductAsset(id) });
}

export function useTkPrompts() {
  return useQuery({ queryKey: ['tk-prompts'], queryFn: () => endpoints.listTkPrompts() });
}
export function useCreateTkPrompt() {
  return useMutation({ mutationFn: (body: { name: string; prompt: string; strategy: string }) => endpoints.createTkPrompt(body) });
}
export function useDeleteTkPrompt() {
  return useMutation({ mutationFn: (id: string) => endpoints.deleteTkPrompt(id) });
}

// Gmail
export function useGmailStatus() {
  return useQuery({ queryKey: ['gmail', 'status'], queryFn: () => endpoints.gmailStatus() });
}
export function useGmailAccounts() {
  return useQuery({ queryKey: ['gmail', 'accounts'], queryFn: () => endpoints.gmailAccounts() });
}
export function useGmailSetDefault() {
  return useMutation({ mutationFn: (id: string) => endpoints.gmailSetDefault(id) });
}
export function useGmailDeleteAccount() {
  return useMutation({ mutationFn: (id: string) => endpoints.gmailDeleteAccount(id) });
}

// Creators write
export function useClaimCreator() {
  return useMutation({ mutationFn: ({ id, body }: { id: string | number; body?: Parameters<typeof endpoints.claimCreator>[1] }) => endpoints.claimCreator(id, body) });
}
export function useReleaseCreator() {
  return useMutation({ mutationFn: ({ id, force }: { id: string | number; force?: boolean }) => endpoints.releaseCreator(id, force) });
}

// Review tasks write
export function usePatchReviewTask() {
  return useMutation({ mutationFn: ({ id, body }: { id: string | number; body: import('@/api/types').ReviewTaskUpdate }) => endpoints.patchReviewTask(id, body) });
}
