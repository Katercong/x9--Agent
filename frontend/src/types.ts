export type ReviewType = "standard" | "model_failure" | "decline" | "dnc_confirmation" | "generation_pending" | "approved_draft";

/**
 * `reply_ready` is a workbench-only aggregate: editable pending replies and
 * approved drafts locked for manual handoff.  Individual API response items
 * still retain their concrete `review_type`.
 */
export type ReviewFilter = ReviewType | "reply_ready" | "all";

export interface InboundReply {
  id: string;
  creator_id: string;
  from_email: string;
  to_email: string;
  subject: string;
  body: string;
  message_at: string | null;
  processing_status: string;
  reply_category: string | null;
  classification_confidence: number | null;
  classification_reason: string | null;
  created_at?: string | null;
}

export interface AgentRun {
  id: string;
  creator_id: string;
  inbound_reply_id: string;
  reply_category: string | null;
  suggested_status: string | null;
  llm_status: string;
  block_reason: string | null;
  execution_status: string;
  provider_model: string | null;
  output: Record<string, unknown> | null;
  validation_error: string | null;
  error_summary: string | null;
  prompt_version: string | null;
  duration_ms: number | null;
  created_by?: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DncConfirmation {
  id: string;
  reason: string;
  status: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string | null;
}

export interface ReviewQueueItem {
  review_type: ReviewType;
  decision_available: boolean;
  reply: InboundReply;
  run: AgentRun | null;
  dnc_confirmation: DncConfirmation | null;
  decision?: HumanReviewDecision | null;
}

export interface ReviewQueueResponse {
  ok: true;
  total: number;
  items: ReviewQueueItem[];
}

export interface CreatorContext {
  id: string;
  platform: string;
  handle: string;
  display_name: string | null;
  email: string | null;
  bio: string | null;
  followers_count: number | null;
  owner_bd: string | null;
  recommendation_reason: string | null;
  recommended_product_type: string | null;
  recommended_collab_type: string | null;
}

export interface ProductContext {
  id: string;
  product_type: string;
  name: string;
  summary: string;
  selling_points: string[];
  target_audience: string | null;
  collaboration_requirements: string | null;
  campaign_timeline: string | null;
  campaign_deliverables: string | null;
  budget_guidance: string | null;
  notes: string | null;
}

export interface MessageContext {
  id: string;
  subject: string | null;
  body: string | null;
  message_at?: string | null;
  sent_at?: string | null;
}

export interface EventContext {
  id: string;
  event_type: string;
  note: string | null;
  event_at: string | null;
}

export interface TaskContext {
  id: string;
  task_type: string;
  status: string;
  reason: string | null;
  due_at: string | null;
}

export interface ReviewContext {
  creator: CreatorContext;
  product: ProductContext | null;
  inbound_reply: InboundReply;
  recent_inbound_replies: MessageContext[];
  recent_outreach_emails: MessageContext[];
  recent_events: EventContext[];
  open_followup_tasks: TaskContext[];
  reference_materials: Array<{ reference_key: string; title: string; content: string; version: number }>;
}

export interface ReviewItemDetail {
  ok: true;
  item: ReviewQueueItem;
  context: ReviewContext;
  runs: AgentRun[];
}

export interface HumanReviewDecision {
  id: string;
  creator_id: string;
  inbound_reply_id: string;
  agent_followup_run_id: string;
  outcome: "approve_draft" | "close_without_draft";
  final_draft: string | null;
  note: string | null;
  actor_id: string;
  decided_at: string | null;
  created_at: string | null;
}

export interface ReviewDecisionResponse {
  ok: true;
  decision: HumanReviewDecision;
  reply: InboundReply;
}

export interface DraftExportRecord {
  id: string;
  human_review_decision_id: string;
  creator_id: string;
  inbound_reply_id: string;
  exported_content: string;
  actor_id: string;
  exported_at: string | null;
  created_at: string | null;
  delivery_status: "not_sent_by_system";
}

export interface DraftExportResponse {
  ok: true;
  export: DraftExportRecord;
}

export interface DncConfirmationApproveResponse {
  ok: true;
  confirmation: DncConfirmation;
  creator: {
    id: string;
    do_not_contact_status: string;
  };
  reply: InboundReply;
}

export interface DncConfirmationRejectResponse extends DncConfirmationApproveResponse {
  run: AgentRun;
}

export interface FailedReviewRetryResponse {
  ok: true;
  run: AgentRun;
  reply: InboundReply;
}
