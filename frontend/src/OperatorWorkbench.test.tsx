import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OperatorWorkbench } from "./OperatorWorkbench";
import type { CurrentPrincipal, ReviewItemDetail, ReviewQueueItem } from "./types";

const adminPrincipal: CurrentPrincipal = {
  user_id: "auth_user_demo_admin",
  display_name: "Demo Admin",
  departments: [{ code: "cross_border", role: "admin" }],
  capabilities: ["review:read", "review:decide", "run:retry", "dnc:decide", "draft:export", "delivery:confirm"],
};

const standardItem: ReviewQueueItem = {
  review_type: "standard",
  decision_available: true,
  reply: {
    id: "reply_standard",
    department_code: "cross_border",
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
    actor_id: "auth_user_demo_admin",
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

const declineItem: ReviewQueueItem = {
  ...dncItem,
  review_type: "decline",
  reply: {
    ...dncItem.reply,
    id: "reply_decline",
    creator_id: "creator_decline",
    body: "No thanks, I am not interested.",
    reply_category: "not_interested",
  },
  dnc_confirmation: null,
};

const confirmedDncItem: ReviewQueueItem = {
  ...dncItem,
  dnc_confirmation: { ...dncItem.dnc_confirmation!, status: "confirmed" },
};

// This intentionally keeps stale draft data in the mocked response.  The UI
// must still suppress it whenever the server classifies the creator as DNC.
const dncBlockedApprovedItem: ReviewQueueItem = {
  ...approvedDraftItem,
  review_type: "dnc_blocked",
  decision_available: false,
  dnc_confirmation: null,
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

function manualDeliveryResponse(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    delivery: {
      id: "delivery_approved",
      human_review_decision_id: "decision_approved",
      creator_id: "creator_1",
      inbound_reply_id: "reply_approved",
      department_code: "cross_border",
      status: "pending_second_confirmation",
      stored_status: "pending_second_confirmation",
      status_reason: null,
      dnc_blocked: false,
      snapshot_available: true,
      snapshot: {
        draft_content: "Approved final draft for manual handoff.",
        draft_sha256: "synthetic-hash",
        recipient_email: "creator@example.test",
        subject: "Re: Campaign",
        gmail_thread_id: "gmail-thread-1",
        rfc_message_id: "<message-1@example.test>",
        references: "<message-0@example.test>",
        account_email: null,
        account_owner_auth_user_id: null,
      },
      approved_by_auth_user_id: "auth_user_demo_admin",
      second_confirmed_by_auth_user_id: null,
      second_confirmed_at: null,
      expires_at: "2099-07-30T12:00:00",
      quota_reserved: false,
      quota_reservation_date: null,
      queued_at: null,
      sending_started_at: null,
      completed_at: null,
      created_at: "2026-07-22T12:00:00",
      updated_at: "2026-07-22T12:00:00",
      account: null,
      ...overrides,
    },
    events: [{
      id: "delivery-event-created",
      manual_delivery_request_id: "delivery_approved",
      department_code: "cross_border",
      actor_id: "auth_user_demo_admin",
      event_type: "delivery_request_created",
      metadata: {},
      event_at: "2026-07-22T12:00:00",
      created_at: "2026-07-22T12:00:00",
    }],
  };
}

const ownDeliveryAccount = {
  id: "delivery_account_1",
  department_code: "cross_border",
  owner_auth_user_id: "auth_user_demo_admin",
  display_name: "我的 Workspace 邮箱",
  email: "bd@example.test",
  is_active: true,
  daily_limit: 40,
  created_at: "2026-07-22T12:00:00",
  updated_at: "2026-07-22T12:00:00",
};

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } }));
}

function renderWorkbench(principal: CurrentPrincipal | null = adminPrincipal) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  if (principal) queryClient.setQueryData(["current-principal"], principal);
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
    vi.useRealTimers();
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
      });
    });
    expect(fetchMock.mock.calls.some(([url]) => /send/i.test(String(url)))).toBe(false);
  });

  it("renders the current identity and hides review decisions for an operator-only department role", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench({
      user_id: "auth_user_operator",
      display_name: "Scoped Operator",
      departments: [{ code: "cross_border", role: "operator" }],
      capabilities: ["review:read", "draft:export"],
    });

    expect(await screen.findByText("当前操作人：Scoped Operator")).toBeInTheDocument();
    await screen.findByText("Thank you for your interest.");
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.getByText("当前身份仅可查看")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/review-decisions"))).toBe(false);
  });

  it("does not load review data when the current identity cannot be resolved", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(new Response(JSON.stringify({ detail: "invalid or missing identity assertion" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench(null);

    expect(await screen.findByText("身份或权限验证失败")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/review-queue"))).toBe(false);
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
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) return jsonResponse(manualDeliveryResponse());
      if (url.endsWith("/manual-delivery-accounts/mine")) return jsonResponse({ items: [ownDeliveryAccount] });
      if (url.endsWith("/review-decisions/decision_approved/exports") && init?.method === "POST") {
        return jsonResponse({ ok: true, export: { id: "export_1", delivery_status: "not_sent_by_system" } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    expect(await screen.findByText("Approved final draft for manual handoff.")).toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(await screen.findByText("本地投递二次确认")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /发送/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /复制草稿/ }));
    await user.click(screen.getByRole("button", { name: /下载 .txt/ }));

    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:approved-draft");
    const exportCalls = fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith("/review-decisions/decision_approved/exports") && init?.method === "POST");
    expect(exportCalls).toHaveLength(2);
    expect(fetchMock.mock.calls.some(([url]) => /gmail|send/i.test(String(url)))).toBe(false);
  });

  it("lets the approving reviewer select only a local account and explicitly queue a locked draft without Gmail", async () => {
    let queued = false;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/manual-delivery-accounts/mine")) return jsonResponse({ items: [ownDeliveryAccount] });
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) {
        return jsonResponse(manualDeliveryResponse(queued ? {
          status: "queued",
          stored_status: "queued",
          account: ownDeliveryAccount,
          second_confirmed_by_auth_user_id: "auth_user_demo_admin",
          second_confirmed_at: "2026-07-22T12:05:00",
          queued_at: "2026-07-22T12:05:00",
          quota_reserved: true,
          quota_reservation_date: "2026-07-22",
        } : {}));
      }
      if (url.endsWith("/review-decisions/decision_approved/delivery-confirmations") && init?.method === "POST") {
        queued = true;
        return jsonResponse({
          ok: true,
          delivery: manualDeliveryResponse({
            status: "queued",
            stored_status: "queued",
            account: ownDeliveryAccount,
          }).delivery,
          message: "delivery was queued locally; no Gmail request was made",
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    expect(await screen.findByText("收件人")).toBeInTheDocument();
    expect(screen.getAllByText("creator@example.test").length).toBeGreaterThan(1);
    const queueButton = screen.getByRole("button", { name: "确认进入投递队列" });
    await waitFor(() => expect(queueButton).toBeEnabled());
    expect(screen.getByText("我的 Workspace 邮箱 · bd@example.test")).toBeInTheDocument();
    await user.click(queueButton);
    await user.click(await screen.findByRole("button", { name: "确认入队" }));

    await waitFor(() => {
      const confirmationCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/review-decisions/decision_approved/delivery-confirmations") && init?.method === "POST",
      );
      expect(confirmationCall).toBeDefined();
      expect(JSON.parse(confirmationCall?.[1].body as string)).toEqual({ delivery_account_id: "delivery_account_1" });
    });
    expect(await screen.findByText("已进入本地投递队列")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => /gmail|send/i.test(String(url)))).toBe(false);
  });

  it("shows the minimum audit start time while a local delivery is sending", async () => {
    const sendingStartedAt = "2026-07-22T12:06:00";
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) {
        return jsonResponse(manualDeliveryResponse({
          status: "sending",
          stored_status: "sending",
          account: ownDeliveryAccount,
          second_confirmed_by_auth_user_id: "auth_user_demo_admin",
          second_confirmed_at: "2026-07-22T12:05:00",
          queued_at: "2026-07-22T12:05:00",
          sending_started_at: sendingStartedAt,
          quota_reserved: true,
          quota_reservation_date: "2026-07-22",
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench();

    expect(await screen.findByText("投递处理中")).toBeInTheDocument();
    expect(screen.getByText("开始投递时间")).toBeInTheDocument();
    expect(screen.getByText(new Date(sendingStartedAt).toLocaleString("zh-CN", { hour12: false }))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认进入投递队列" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => /gmail|send/i.test(String(url)))).toBe(false);
  });

  it("disables local queue confirmation when the locked snapshot lacks reliable thread references", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/manual-delivery-accounts/mine")) return jsonResponse({ items: [ownDeliveryAccount] });
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) {
        return jsonResponse(manualDeliveryResponse({
          snapshot: { ...manualDeliveryResponse().delivery.snapshot, gmail_thread_id: null },
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench();

    expect(await screen.findByText("缺少可靠线程引用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认进入投递队列" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("delivery-confirmations"))).toBe(false);
  });

  it("refreshes second-confirmation expiry at minute intervals and disables local queue confirmation", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2099-07-30T12:00:00.000Z"));
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/manual-delivery-accounts/mine")) return jsonResponse({ items: [ownDeliveryAccount] });
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) {
        return jsonResponse(manualDeliveryResponse({ expires_at: "2099-07-30T12:00:30.000Z" }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench();

    const queueButton = await screen.findByRole("button", { name: "确认进入投递队列" });
    await waitFor(() => expect(queueButton).toBeEnabled());
    expect(screen.getByText("约 1 分钟后过期")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(await screen.findByText("二次确认窗口已过期")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认进入投递队列" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("delivery-confirmations"))).toBe(false);
  });

  it("keeps the local delivery request read-only for a non-reviewer and does not load their accounts", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [approvedDraftItem] });
      if (url.includes("/review-items/reply_approved")) return jsonResponse(detailFor(approvedDraftItem));
      if (url.endsWith("/review-decisions/decision_approved/delivery-request")) return jsonResponse(manualDeliveryResponse());
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench({
      user_id: "auth_user_operator",
      display_name: "Scoped Operator",
      departments: [{ code: "cross_border", role: "operator" }],
      capabilities: ["review:read", "draft:export"],
    });

    expect(await screen.findByText("当前身份仅可查看")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认进入投递队列" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/manual-delivery-accounts/mine"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("delivery-confirmations"))).toBe(false);
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

  it("lets a reviewer confirm an explicit decline without exposing draft, handoff, or sending controls", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 0, items: [] });
      if (url.includes("review_type=decline")) return jsonResponse({ ok: true, total: 1, items: [declineItem] });
      if (url.endsWith("/review-items/reply_decline/confirm-decline") && init?.method === "POST") {
        return jsonResponse({
          ok: true,
          confirmation: {
            id: "decline_1",
            department_code: "cross_border",
            creator_id: "creator_decline",
            inbound_reply_id: "reply_decline",
            actor_id: "auth_user_demo_admin",
            confirmed_at: "2026-07-29T21:00:00",
            created_at: "2026-07-29T21:00:00",
          },
          creator: { id: "creator_decline", current_status: "dropped", do_not_contact_status: "none" },
          reply: { ...declineItem.reply, processing_status: "reviewed" },
          closed_followup_task_ids: ["task_1"],
        });
      }
      if (url.includes("/review-items/reply_decline")) return jsonResponse(detailFor(declineItem));
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench();

    await user.click(await screen.findByRole("button", { name: /拒绝待确认/ }));
    expect(await screen.findByText("明确拒绝待人工确认")).toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制草稿" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载 .txt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发送（暂未接入）" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认拒绝" }));
    const confirmationButtons = await screen.findAllByRole("button", { name: "确认拒绝" });
    await user.click(confirmationButtons.at(-1)!);
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/review-items/reply_decline/confirm-decline") && init?.method === "POST",
      );
      expect(call).toBeDefined();
      expect(JSON.parse(call?.[1].body as string)).toEqual({});
    });
    expect(fetchMock.mock.calls.some(([url]) => /send/i.test(String(url)))).toBe(false);
  });

  it("keeps an explicit decline read-only for an operator without review decision capability", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 0, items: [] });
      if (url.includes("review_type=decline")) return jsonResponse({ ok: true, total: 1, items: [declineItem] });
      if (url.includes("/review-items/reply_decline")) return jsonResponse(detailFor(declineItem));
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderWorkbench({
      user_id: "auth_user_operator",
      display_name: "Scoped Operator",
      departments: [{ code: "cross_border", role: "operator" }],
      capabilities: ["review:read", "draft:export"],
    });

    await user.click(await screen.findByRole("button", { name: /拒绝待确认/ }));
    expect(await screen.findByText("当前身份没有终态确认权限，仅可查看该拒绝记录。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认拒绝" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("confirm-decline"))).toBe(false);
  });

  it("labels a confirmed DNC distinctly from a pending DNC confirmation", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("review_type=reply_ready")) return jsonResponse({ ok: true, total: 1, items: [confirmedDncItem] });
      if (url.includes("/review-items/reply_dnc")) return jsonResponse(detailFor(confirmedDncItem));
      throw new Error(`Unexpected request: ${url}`);
    });
    renderWorkbench();

    expect((await screen.findAllByText("DNC 已确认")).length).toBeGreaterThan(0);
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
    expect(screen.queryByRole("button", { name: "确认 DNC" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "驳回 DNC" })).not.toBeInTheDocument();
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
