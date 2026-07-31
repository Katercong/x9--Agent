import type {
  CurrentPrincipal,
  DeclineConfirmationResponse,
  DncConfirmationApproveResponse,
  DncConfirmationRejectResponse,
  DraftExportResponse,
  FailedReviewRetryResponse,
  ManualDeliveryAccountListResponse,
  ManualDeliveryConfirmationResponse,
  ManualDeliveryRequestResponse,
  ReviewDecisionResponse,
  ReviewFilter,
  ReviewItemDetail,
  ReviewQueueResponse,
} from "./types";

const API_ROOT = "/api/followup-agent";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { "content-type": "application/json", ...init?.headers },
    ...init,
  });
  const payload = (await response.json().catch(() => null)) as { detail?: string } | T | null;
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : "请求失败";
    throw new ApiError(response.status, detail || "请求失败");
  }
  return payload as T;
}

export function getReviewQueue(reviewType?: Exclude<ReviewFilter, "all">): Promise<ReviewQueueResponse> {
  const query = reviewType ? `?review_type=${encodeURIComponent(reviewType)}` : "";
  return request<ReviewQueueResponse>(`/review-queue${query}`);
}

export function getCurrentPrincipal(): Promise<CurrentPrincipal> {
  return request<CurrentPrincipal>("/auth/me");
}

export function getReviewItem(replyId: string): Promise<ReviewItemDetail> {
  return request<ReviewItemDetail>(`/review-items/${encodeURIComponent(replyId)}`);
}

export function submitReviewDecision(input: {
  runId: string;
  outcome: "approve_draft" | "close_without_draft";
  finalDraft?: string;
}): Promise<ReviewDecisionResponse> {
  return request<ReviewDecisionResponse>("/review-decisions", {
    method: "POST",
    body: JSON.stringify({
      agent_followup_run_id: input.runId,
      outcome: input.outcome,
      final_draft: input.outcome === "approve_draft" ? input.finalDraft?.trim() : undefined,
    }),
  });
}

export function createDraftExportRecord(decisionId: string): Promise<DraftExportResponse> {
  return request<DraftExportResponse>(`/review-decisions/${encodeURIComponent(decisionId)}/exports`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function approveDncConfirmation(confirmationId: string): Promise<DncConfirmationApproveResponse> {
  return request<DncConfirmationApproveResponse>(`/dnc-confirmations/${encodeURIComponent(confirmationId)}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function rejectDncConfirmation(confirmationId: string): Promise<DncConfirmationRejectResponse> {
  return request<DncConfirmationRejectResponse>(`/dnc-confirmations/${encodeURIComponent(confirmationId)}/reject`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function confirmDeclineReviewItem(replyId: string): Promise<DeclineConfirmationResponse> {
  return request<DeclineConfirmationResponse>(`/review-items/${encodeURIComponent(replyId)}/confirm-decline`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function retryFailedReviewItem(replyId: string): Promise<FailedReviewRetryResponse> {
  return request<FailedReviewRetryResponse>(`/review-items/${encodeURIComponent(replyId)}/retry`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getManualDeliveryRequest(decisionId: string): Promise<ManualDeliveryRequestResponse> {
  return request<ManualDeliveryRequestResponse>(`/review-decisions/${encodeURIComponent(decisionId)}/delivery-request`);
}

export function getMyManualDeliveryAccounts(): Promise<ManualDeliveryAccountListResponse> {
  return request<ManualDeliveryAccountListResponse>("/manual-delivery-accounts/mine");
}

export function confirmManualDeliveryRequest(
  decisionId: string,
  deliveryAccountId: string,
): Promise<ManualDeliveryConfirmationResponse> {
  return request<ManualDeliveryConfirmationResponse>(
    `/review-decisions/${encodeURIComponent(decisionId)}/delivery-confirmations`,
    {
      method: "POST",
      body: JSON.stringify({ delivery_account_id: deliveryAccountId }),
    },
  );
}
