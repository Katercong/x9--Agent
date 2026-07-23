import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OperatorWorkbench } from "./OperatorWorkbench";
import type { ReviewItemDetail, ReviewQueueItem } from "./types";

const standardItem: ReviewQueueItem = {
  review_type: "standard",
  decision_available: true,
  reply: {
    id: "reply_standard",
    creator_id: "creator_1",
    from_email: "creator@example.test",
    to_email: "",
    subject: "Re: Campaign",
    body: "Sounds interesting.",
    message_at: "2026-07-22T10:00:00",
    processing_status: "need_ai_review",
    reply_category: "interested",
    classification_confidence: 0.78,
    classification_reason: "matched_keyword:interested",
  },
  run: {
    id: "run_standard",
    creator_id: "creator_1",
    inbound_reply_id: "reply_standard",
    reply_category: "interested",
    suggested_status: "pending_followup",
    llm_status: "success",
    block_reason: null,
    execution_status: "succeeded",
    provider_model: "deepseek-ai/DeepSeek-V3.2",
    output: {
      suggested_reply: "Thank you for your interest.",
      next_action: "send_campaign_details",
      confidence: 0.88,
      review_reasons: ["human_approval_required"],
    },
    validation_error: null,
    error_summary: null,
    prompt_version: "reply_followup_v2",
    duration_ms: 120,
    created_at: "2026-07-22T10:00:00",
    started_at: "2026-07-22T10:00:00",
    finished_at: "2026-07-22T10:00:01",
  },
  dnc_confirmation: null,
};

const approvedDraftItem: ReviewQueueItem = {
  ...standardItem,
  review_type: "approved_draft",
  decision_available: false,
  reply: { ...standardItem.reply, id: "reply_approved", body: "Please share the next steps.", processing_status: "reviewed" },
  decision: {
    id: "decision_approved",
    creator_id: "creator_1",
    inbound_reply_id: "reply_approved",
    agent_followup_run_id: "run_standard",
    outcome: "approve_draft",
    final_draft: "Approved final draft for manual handoff.",
    note: "Reviewed by demo operator.",
    actor_id: "demo_operator",
    decided_at: "2026-07-22T12:00:00",
    created_at: "2026-07-22T12:00:00",
  },
};

const modelFailureItem: ReviewQueueItem = {
  ...standardItem,
  review_type: "model_failure",
  reply: { ...standardItem.reply, id: "reply_failure", creator_id: "creator_failure", body: "Could you share more details?" },
  run: {
    ...standardItem.run!,
    id: "run_failure",
    creator_id: "creator_failure",
    inbound_reply_id: "reply_failure",
    llm_status: "validation_failed",
    execution_status: "failed",
    output: { raw_output: "{invalid model output}" },
    validation_error: "suggested_reply: Field required",
  },
};

const dncItem: ReviewQueueItem = {
  ...standardItem,
  review_type: "dnc_confirmation",
  decision_available: false,
  reply: { ...standardItem.reply, id: "reply_dnc", body: "Please unsubscribe me.", reply_category: "not_interested" },
  run: null,
  dnc_confirmation: { id: "dnc_1", reason: "explicit_opt_out", status: "pending_confirmation", created_at: "2026-07-22T11:00:00" },
};

// This intentionally keeps stale draft data in the mocked response.  The UI
// must still suppress it whenever the server classifies the creator as DNC.
const dncBlockedApprovedItem: ReviewQueueItem = {
  ...approvedDraftItem,
  review_type: "dnc_confirmation",
  decision_available: false,
  dnc_confirmation: { id: "dnc_confirmed", reason: "explicit_opt_out", status: "confirmed", created_at: "2026-07-22T12:30:00" },
};

function detailFor(item: ReviewQueueItem): ReviewItemDetail {
  return {
    ok: true,
    item,
    context: {
      creator: {
        id: item.reply.creator_id,
        platform: "tiktok",
        handle: "creator_1",
        display_name: "Creator One",
        email: "creator@example.test",
        bio: "Synthetic profile.",
        followers_count: 15000,
        owner_bd: "bd_1",
        recommendation_reason: "Synthetic reason.",
        recommended_product_type: "baby care",
        recommended_collab_type: "product review",
      },
      product: {
        id: "product_1",
        product_type: "baby care",
        name: "Baby Care Starter",
        summary: "Synthetic product.",
        selling_points: ["gentle formula"],
        target_audience: "Parents",
        collaboration_requirements: "One video",
        campaign_timeline: null,
        campaign_deliverables: null,
        budget_guidance: null,
        notes: null,
      },
      inbound_reply: item.reply,
      recent_inbound_replies: [{ id: "inbound_old", subject: "Re: Campaign", body: "What is the budget range?", message_at: "2026-07-21T09:00:00" }],
      recent_outreach_emails: [{ id: "outbound_old", subject: "Campaign introduction", body: "We would like to explore a collaboration.", sent_at: "2026-07-21T08:00:00" }],
      recent_events: [],
      open_followup_tasks: [],
      reference_materials: [{ reference_key: "policy", title: "Policy", content: "Synthetic policy.", version: 1 }],
    },
    runs: item.run ? [item.run] : [],
  };
}

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } }));
}

function renderWorkbench() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ConfigProvider>
      <QueryClientProvider client={queryClient}>
        <OperatorWorkbench />
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("OperatorWorkbench", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("uses the merged reply-ready queue and renders a client conversation timeline with AI kept out of the message stream", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 2, items: [standardItem, approvedDraftItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench();

    expect(await screen.findByText("人工回复草稿")).toBeInTheDocument();
    await screen.findByLabelText("最终草稿");
    expect(screen.getAllByText("待审核").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已锁定待交接").length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/达人回复/)).length).toBe(2);
    expect(screen.getByText(/历史建联记录/)).toBeInTheDocument();
    expect(screen.getByText("What is the budget range?")).toBeInTheDocument();
    expect(screen.getByText("We would like to explore a collaboration.")).toBeInTheDocument();
    expect(screen.getByText("AI 协作建议")).toBeInTheDocument();
    expect(screen.getAllByText("Thank you for your interest.").length).toBe(2);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("review_type=reply_ready"))).toBe(true);
    expect(screen.queryByText("AI 回复")).not.toBeInTheDocument();
  });

  it("lets an operator edit and lock a draft through the decision API without any sending request", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      if (url.endsWith("/review-decisions") && init?.method === "POST") {
        return jsonResponse({ ok: true, decision: { ...approvedDraftItem.decision, final_draft: "Human final draft." }, reply: standardItem.reply });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    const draft = await screen.findByLabelText("最终草稿");
    await user.clear(draft);
    await user.type(draft, "Human final draft.");
    await user.click(screen.getByRole("button", { name: /批准并锁定草稿/ }));

    await waitFor(() => {
      const decisionCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/review-decisions") && init?.method === "POST");
      expect(decisionCall).toBeDefined();
      expect(JSON.parse(decisionCall?.[1].body as string)).toMatchObject({
        agent_followup_run_id: "run_standard",
        outcome: "approve_draft",
        final_draft: "Human final draft.",
        actor_id: "demo_operator",
      });
    });
    expect(fetchMock.mock.calls.some(([url]) => /send/i.test(String(url)))).toBe(false);
  });

  it("shows an approved draft as locked manual handoff and audits both copy and download actions", async () => {
    const createObjectUrl = vi.fn(() => "blob:approved-draft");
    const revokeObjectUrl = vi.fn();
    const anchorClick = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(anchorClick);
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/review-decisions/decision_approved/exports") && init?.method === "POST") {
        return jsonResponse({ ok: true, export: { id: "export_1", delivery_status: "not_sent_by_system" } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    expect(await screen.findByText("Approved final draft for manual handoff.")).toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送（暂未接入）" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /复制草稿/ }));
    await user.click(screen.getByRole("button", { name: /下载 .txt/ }));

    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:approved-draft");
    const exportCalls = fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith("/review-decisions/decision_approved/exports") && init?.method === "POST");
    expect(exportCalls).toHaveLength(2);
    expect(fetchMock.mock.calls.some(([url]) => /send/i.test(String(url)))).toBe(false);
  });

  it("keeps DNC in a terminal review flow with confirmation and rejection, never draft or handoff controls", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [dncItem] });
      if (url.includes("/review-items/reply_dnc")) return jsonResponse(detailFor(dncItem));
      if (url.endsWith("/dnc-confirmations/dnc_1/approve") && init?.method === "POST") {
        return jsonResponse({ ok: true, confirmation: { ...dncItem.dnc_confirmation, status: "confirmed" }, creator: { id: "creator_1", do_not_contact_status: "confirmed" }, reply: dncItem.reply });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    expect(await screen.findByText("DNC 待人工确认")).toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制草稿" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /确认 DNC/ }));
    const confirmationButtons = await screen.findAllByRole("button", { name: /确认 DNC/ });
    await user.click(confirmationButtons.at(-1)!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/dnc-confirmations/dnc_1/approve") && init?.method === "POST")).toBe(true));
    expect(fetchMock.mock.calls.some(([url]) => /send/i.test(String(url)))).toBe(false);
  });

  it("hides a previously approved draft and every handoff entry after the creator becomes DNC", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [dncBlockedApprovedItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(dncBlockedApprovedItem));
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench();

    expect(await screen.findByText("DNC 已确认并阻断")).toBeInTheDocument();
    expect(screen.queryByText("Approved final draft for manual handoff.")).not.toBeInTheDocument();
    expect(screen.queryByText("Thank you for your interest.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制草稿" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载 .txt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发送（暂未接入）" })).not.toBeInTheDocument();
  });

  it("starts a model failure from an empty composer and only retries when the operator clicks the action", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [modelFailureItem] });
      if (url.includes("/review-items/reply_failure")) return jsonResponse(detailFor(modelFailureItem));
      if (url.endsWith("/review-items/reply_failure/retry") && init?.method === "POST") {
        return jsonResponse({ ok: true, reply: modelFailureItem.reply, run: { ...modelFailureItem.run, id: "run_retry", execution_status: "queued" } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    expect((await screen.findAllByText("模型未生成可用建议")).length).toBe(2);
    expect(await screen.findByLabelText("最终草稿")).toHaveValue("");
    expect(screen.getByText("suggested_reply: Field required")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /人工重新生成草稿/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/review-items/reply_failure/retry") && init?.method === "POST")).toBe(true));
  });

  it("switches queue categories through the real API filter rather than treating terminal items as reply-ready", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=model_failure")) return jsonResponse({ ok: true, total: 1, items: [modelFailureItem] });
      if (url.includes("/review-items/reply_failure")) return jsonResponse(detailFor(modelFailureItem));
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    await screen.findByText("人工回复草稿");
    await user.click(screen.getByRole("button", { name: /模型生成失败.*可人工起草/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("review_type=model_failure"))).toBe(true));
    expect(screen.getByRole("button", { name: /模型生成失败.*可人工起草/ })).toHaveAttribute("aria-pressed", "true");
  });
});
