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

const dncItem: ReviewQueueItem = {
  ...standardItem,
  review_type: "dnc_confirmation",
  decision_available: false,
  reply: { ...standardItem.reply, id: "reply_dnc", body: "Please unsubscribe me.", reply_category: "not_interested" },
  run: null,
  dnc_confirmation: { id: "dnc_1", reason: "explicit_opt_out", status: "pending_confirmation", created_at: "2026-07-22T11:00:00" },
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
      recent_inbound_replies: [],
      recent_outreach_emails: [],
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

  it("edits and submits a human-approved standard draft through the real review API contract", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      if (url.endsWith("/review-decisions") && init?.method === "POST") {
        return jsonResponse({ ok: true, decision: { id: "decision_1", outcome: "approve_draft", final_draft: "Human final draft." }, reply: standardItem.reply });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const user = userEvent.setup();
    renderWorkbench();

    const draft = await screen.findByLabelText("最终草稿");
    await user.clear(draft);
    await user.type(draft, "Human final draft.");
    await user.click(screen.getByRole("button", { name: /批准草稿/ }));

    await waitFor(() => {
      const decisionCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/review-decisions") && init?.method === "POST");
      expect(decisionCall).toBeDefined();
      expect(JSON.parse(decisionCall?.[1].body as string)).toEqual({
        agent_followup_run_id: "run_standard",
        outcome: "approve_draft",
        final_draft: "Human final draft.",
        actor_id: "demo_operator",
      });
    });
  });

  it("renders AI actions, confidence, and review prompts in operator-friendly Chinese", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench();

    expect(await screen.findByText("建议下一步：整理合作资料，待人工确认")).toBeInTheDocument();
    expect(screen.getByText("判断把握：高（88%）")).toBeInTheDocument();
    expect(screen.getByText("复核提示：需人工确认后才能继续")).toBeInTheDocument();
    expect(screen.queryByText("send_campaign_details")).not.toBeInTheDocument();
    expect(screen.queryByText("human_approval_required")).not.toBeInTheDocument();
  });

  it("shows complete queue category labels and operational guidance", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [standardItem] });
      if (url.includes("/review-items/reply_standard")) return jsonResponse(detailFor(standardItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    const user = userEvent.setup();
    renderWorkbench();

    expect(await screen.findByText("查看全部待审项目")).toBeInTheDocument();
    expect(screen.getByText("AI 已生成草稿，可编辑后决定")).toBeInTheDocument();
    expect(screen.getByText("AI 未产出有效草稿，需人工起草")).toBeInTheDocument();
    expect(screen.getByText("终态项目，仅供查看")).toBeInTheDocument();
    expect(screen.getByText("确认永久停止联系，或驳回后重新审核")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /模型失败.*AI 未产出有效草稿/ }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("review_type=model_failure"))).toBe(true);
    });
    expect(screen.getByRole("button", { name: /模型失败.*AI 未产出有效草稿/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("renders pending DNC items without draft or sending controls, but with human confirmation and rejection actions", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [dncItem] });
      if (url.includes("/review-items/reply_dnc")) return jsonResponse(detailFor(dncItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench();

    expect(await screen.findByText("DNC 待人工确认")).toBeInTheDocument();
    expect(screen.queryByLabelText("最终草稿")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /批准草稿/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认 DNC" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "驳回 DNC" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /发送/ })).not.toBeInTheDocument();
  });

  it("confirms DNC through the dedicated human-review API without any sending action", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [dncItem] });
      if (url.includes("/review-items/reply_dnc")) return jsonResponse(detailFor(dncItem));
      if (url.endsWith("/dnc-confirmations/dnc_1/approve") && init?.method === "POST") {
        return jsonResponse({
          ok: true,
          confirmation: { ...dncItem.dnc_confirmation, status: "confirmed", reviewed_by: "demo_operator", reviewed_at: "2026-07-22T11:05:00" },
          creator: { id: "creator_1", do_not_contact_status: "confirmed" },
          reply: { ...dncItem.reply, processing_status: "reviewed" },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const user = userEvent.setup();
    renderWorkbench();

    await screen.findByText("DNC 待人工确认");
    await user.click(screen.getByRole("button", { name: "确认 DNC" }));
    await user.click(await screen.findByRole("button", { name: "确认永久 DNC" }));

    await waitFor(() => {
      const confirmationCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/dnc-confirmations/dnc_1/approve") && init?.method === "POST");
      expect(confirmationCall).toBeDefined();
      expect(JSON.parse(confirmationCall?.[1].body as string)).toEqual({ actor_id: "demo_operator" });
    });
  });

  it("rejects DNC and queues a new ordinary review without any sending action", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [dncItem] });
      if (url.includes("/review-items/reply_dnc")) return jsonResponse(detailFor(dncItem));
      if (url.endsWith("/dnc-confirmations/dnc_1/reject") && init?.method === "POST") {
        return jsonResponse({
          ok: true,
          confirmation: { ...dncItem.dnc_confirmation, status: "rejected", reviewed_by: "demo_operator", reviewed_at: "2026-07-22T11:05:00" },
          creator: { id: "creator_1", do_not_contact_status: "none" },
          reply: { ...dncItem.reply, reply_category: "unclear" },
          run: { ...standardItem.run!, id: "run_dnc_retry", inbound_reply_id: "reply_dnc", execution_status: "queued", llm_status: "pending", created_by: "demo_operator" },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const user = userEvent.setup();
    renderWorkbench();

    await screen.findByText("DNC 待人工确认");
    await user.click(screen.getByRole("button", { name: "驳回 DNC" }));
    await user.click(await screen.findByRole("button", { name: "驳回并重新审核" }));

    await waitFor(() => {
      const rejectionCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/dnc-confirmations/dnc_1/reject") && init?.method === "POST");
      expect(rejectionCall).toBeDefined();
      expect(JSON.parse(rejectionCall?.[1].body as string)).toEqual({ actor_id: "demo_operator" });
    });
    expect(screen.queryByRole("button", { name: /发送/ })).not.toBeInTheDocument();
  });

  it("starts a model-failure review with an empty human-authored draft", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [modelFailureItem] });
      if (url.includes("/review-items/reply_failure")) return jsonResponse(detailFor(modelFailureItem));
      throw new Error(`Unexpected request: ${url}`);
    });

    renderWorkbench();

    expect(await screen.findByText("模型未生成可用建议")).toBeInTheDocument();
    expect(await screen.findByLabelText("最终草稿")).toHaveValue("");
    expect(screen.getByText("suggested_reply: Field required")).toBeInTheDocument();
  });

  it("queues a new audited run when a human retries a model failure", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/review-queue")) return jsonResponse({ ok: true, total: 1, items: [modelFailureItem] });
      if (url.includes("/review-items/reply_failure")) return jsonResponse(detailFor(modelFailureItem));
      if (url.endsWith("/review-items/reply_failure/retry") && init?.method === "POST") {
        return jsonResponse({
          ok: true,
          reply: modelFailureItem.reply,
          run: { ...modelFailureItem.run!, id: "run_failure_retry", execution_status: "queued", llm_status: "pending", created_by: "demo_operator" },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const user = userEvent.setup();
    renderWorkbench();

    await screen.findByText("模型未生成可用建议");
    await user.click(screen.getByRole("button", { name: "人工重新生成草稿" }));

    await waitFor(() => {
      const retryCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/review-items/reply_failure/retry") && init?.method === "POST");
      expect(retryCall).toBeDefined();
      expect(JSON.parse(retryCall?.[1].body as string)).toEqual({ actor_id: "demo_operator" });
    });
  });
});
