import type { DncConfirmationApproveResponse, DncConfirmationRejectResponse, FailedReviewRetryResponse, ReviewDecisionResponse, ReviewItemDetail, ReviewQueueResponse, ReviewType } from "./types";

const API_ROOT = "/api/followup-agent";
const DEMO_ACTOR_ID = "demo_operator";

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

export function getReviewQueue(reviewType?: ReviewType): Promise<ReviewQueueResponse> {
  const query = reviewType ? `?review_type=${encodeURIComponent(reviewType)}` : "";
  return request<ReviewQueueResponse>(`/review-queue${query}`);
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
      actor_id: DEMO_ACTOR_ID,
    }),
  });
}

export function approveDncConfirmation(confirmationId: string): Promise<DncConfirmationApproveResponse> {
  return request<DncConfirmationApproveResponse>(`/dnc-confirmations/${encodeURIComponent(confirmationId)}/approve`, {
    method: "POST",
    body: JSON.stringify({ actor_id: DEMO_ACTOR_ID }),
  });
}

export function rejectDncConfirmation(confirmationId: string): Promise<DncConfirmationRejectResponse> {
  return request<DncConfirmationRejectResponse>(`/dnc-confirmations/${encodeURIComponent(confirmationId)}/reject`, {
    method: "POST",
    body: JSON.stringify({ actor_id: DEMO_ACTOR_ID }),
  });
}

export function retryFailedReviewItem(replyId: string): Promise<FailedReviewRetryResponse> {
  return request<FailedReviewRetryResponse>(`/review-items/${encodeURIComponent(replyId)}/retry`, {
    method: "POST",
    body: JSON.stringify({ actor_id: DEMO_ACTOR_ID }),
  });
}
