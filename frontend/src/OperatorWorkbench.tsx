import {
  Alert,
  Avatar,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Input,
  List,
  Popconfirm,
  Skeleton,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  LockOutlined,
  MessageOutlined,
  ProfileOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  approveDncConfirmation,
  createDraftExportRecord,
  getReviewItem,
  getReviewQueue,
  rejectDncConfirmation,
  retryFailedReviewItem,
  submitReviewDecision,
} from "./api";
import type { AgentRun, ReviewContext, ReviewFilter, ReviewQueueItem, ReviewType } from "./types";

const { Paragraph, Text, Title } = Typography;

const filterOptions: Array<{
  description: string;
  icon: ReactNode;
  label: string;
  tone: "draft" | "generation" | "failure" | "terminal";
  value: Exclude<ReviewFilter, "all">;
}> = [
  {
    label: "人工回复草稿",
    description: "待审核草稿与已锁定待交接草稿",
    icon: <MessageOutlined />,
    tone: "draft",
    value: "reply_ready",
  },
  {
    label: "草稿生成中",
    description: "Agent 正在处理，暂不可编辑",
    icon: <RobotOutlined />,
    tone: "generation",
    value: "generation_pending",
  },
  {
    label: "模型生成失败",
    description: "可人工起草，或明确重新生成",
    icon: <ReloadOutlined />,
    tone: "failure",
    value: "model_failure",
  },
  {
    label: "明确拒绝",
    description: "终态记录，只读查看",
    icon: <CloseCircleOutlined />,
    tone: "terminal",
    value: "decline",
  },
  {
    label: "DNC 待确认",
    description: "人工确认停联，或驳回后重新审核",
    icon: <SafetyCertificateOutlined />,
    tone: "terminal",
    value: "dnc_confirmation",
  },
];

const typeLabels: Record<ReviewType, string> = {
  standard: "待审核",
  model_failure: "模型失败",
  generation_pending: "生成中",
  approved_draft: "已锁定待交接",
  decline: "终态只读",
  dnc_confirmation: "DNC 待确认",
  dnc_blocked: "DNC 已阻断",
};

const suggestedActionLabels: Record<string, string> = {
  send_campaign_details: "整理合作资料，待人工确认",
  clarify_terms: "核对合作条款，待人工确认",
  acknowledge_and_close: "确认收到并结束本次跟进",
  ask_clarifying_question: "补充询问合作需求",
  verify_contact_method: "核对有效联系方式",
  prepare_campaign_brief: "整理合作方案与资料",
};

const reviewReasonLabels: Record<string, string> = {
  human_approval_required: "需要人工确认后才能继续",
  "Human approval is required before any response is sent.": "需要人工确认后才能继续",
  negotiation_requires_manual_review: "涉及合作条款，需要人工复核",
  contact_delivery_failure: "联系方式可能失效，需要人工核对",
  sensitive_collaboration_detail: "涉及敏感合作细节，需要人工复核",
  unclear_reply: "回复意图不明确，需要人工判断",
  missing_creator_context: "达人资料不足，需要人工核对",
  missing_product_context: "产品资料不足，需要人工补充",
  missing_campaign_timeline: "缺少合作时间线",
  missing_campaign_deliverables: "缺少交付要求",
  missing_budget_guidance: "缺少预算指引",
  demo_seed_requires_human_approval: "演示数据：需要人工确认",
};

type HandoffAction = "copy" | "download";

interface TimelineEntry {
  at: string | null | undefined;
  body: string;
  id: string;
  kind: "incoming" | "outgoing";
  subject: string | null | undefined;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function suggestedReply(run: AgentRun | null): string {
  const value = run?.output?.suggested_reply;
  return typeof value === "string" ? value : "";
}

function suggestedActionLabel(value: unknown): string {
  return typeof value === "string" ? suggestedActionLabels[value] || "待人工判断下一步" : "未提供";
}

function reviewReasonLabel(value: unknown): string {
  return typeof value === "string" ? reviewReasonLabels[value] || "其他需要人工复核事项" : "需要人工复核";
}

function confidencePresentation(value: unknown): { color?: "green" | "gold" | "red"; text: string } {
  if (typeof value !== "number" || !Number.isFinite(value)) return { text: "未提供" };
  const percentage = Math.round(Math.max(0, Math.min(1, value)) * 100);
  if (value >= 0.85) return { color: "green", text: `高（${percentage}%）` };
  if (value >= 0.6) return { color: "gold", text: `中（${percentage}%）` };
  return { color: "red", text: `低（${percentage}%）` };
}

function typeColor(reviewType: ReviewType): string {
  if (reviewType === "approved_draft") return "success";
  if (reviewType === "model_failure") return "error";
  if (reviewType === "generation_pending") return "processing";
  if (reviewType === "standard") return "blue";
  return "gold";
}

function buildTimeline(context: ReviewContext): TimelineEntry[] {
  const incoming = context.recent_inbound_replies.map((reply) => ({
    at: reply.message_at,
    body: reply.body || "（无正文）",
    id: `incoming-${reply.id}`,
    kind: "incoming" as const,
    subject: reply.subject,
  }));
  const currentId = `incoming-${context.inbound_reply.id}`;
  if (!incoming.some((entry) => entry.id === currentId)) {
    incoming.push({
      at: context.inbound_reply.message_at || context.inbound_reply.created_at,
      body: context.inbound_reply.body || "（无正文）",
      id: currentId,
      kind: "incoming",
      subject: context.inbound_reply.subject,
    });
  }
  const outgoing = context.recent_outreach_emails.map((email) => ({
    at: email.sent_at || email.message_at,
    body: email.body || "（无正文）",
    id: `outgoing-${email.id}`,
    kind: "outgoing" as const,
    subject: email.subject,
  }));

  return [...incoming, ...outgoing].sort((left, right) => {
    const leftTime = left.at ? Date.parse(left.at) : 0;
    const rightTime = right.at ? Date.parse(right.at) : 0;
    return leftTime - rightTime;
  });
}

async function copyDraftToClipboard(content: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(content);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = content;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("浏览器未授予复制权限，请改用 .txt 下载。");
}

function downloadDraftAsText(content: string): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = "locked-manual-handoff-draft.txt";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

function SuggestionMetadata({ output }: { output: Record<string, unknown> | null | undefined }) {
  const confidence = confidencePresentation(output?.confidence);
  const reasons = Array.isArray(output?.review_reasons) ? output.review_reasons.map(reviewReasonLabel) : [];
  return (
    <Space direction="vertical" size={8} className="full-width">
      <Space wrap>
        <Tag>建议下一步：{suggestedActionLabel(output?.next_action)}</Tag>
        <Tag color={confidence.color}>判断把握：{confidence.text}</Tag>
      </Space>
      {reasons.length > 0 && <Text type="secondary">复核提示：{reasons.join("；")}</Text>}
    </Space>
  );
}

function QueueItem({ item, selected, onSelect }: { item: ReviewQueueItem; selected: boolean; onSelect: () => void }) {
  const subject = item.reply.subject || item.reply.body.slice(0, 46);
  return (
    <button className={`queue-item ${selected ? "queue-item-selected" : ""}`} onClick={onSelect} type="button">
      <div className="queue-item-topline">
        <Text strong ellipsis>{item.reply.from_email || item.reply.creator_id}</Text>
        <Tag color={typeColor(item.review_type)}>{typeLabels[item.review_type]}</Tag>
      </div>
      <Text className="queue-item-subject" ellipsis>{subject}</Text>
      <div className="queue-item-meta">
        <Text type="secondary">{item.reply.reply_category || "待判断"}</Text>
        <Text type="secondary">{formatDate(item.reply.message_at || item.reply.created_at)}</Text>
      </div>
      {item.review_type === "model_failure" && <Text type="danger">{item.run?.llm_status || "模型处理失败"}</Text>}
    </button>
  );
}

function ConversationTimeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="conversation-stream" aria-label="对话上下文">
      {entries.map((entry) => (
        <article className={`chat-row chat-row-${entry.kind}`} key={entry.id}>
          <Avatar className={`chat-avatar chat-avatar-${entry.kind}`} size="small">
            {entry.kind === "incoming" ? "达" : "BD"}
          </Avatar>
          <div className="chat-message-wrap">
            <div className="chat-message-label">
              {entry.kind === "incoming" ? "达人回复" : "历史建联记录"} · {formatDate(entry.at)}
            </div>
            <div className={`chat-bubble chat-bubble-${entry.kind}`}>
              {entry.subject && <Text className="chat-subject">{entry.subject}</Text>}
              <Paragraph className="chat-body">{entry.body}</Paragraph>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function RunTrace({ run }: { run: AgentRun }) {
  return (
    <div className="run-trace-row">
      <Space wrap size={6}>
        <Tag color={run.execution_status === "failed" ? "error" : run.execution_status === "succeeded" ? "success" : "processing"}>
          {run.execution_status}
        </Tag>
        <Tag>{run.llm_status}</Tag>
        {run.prompt_version && <Text type="secondary">{run.prompt_version}</Text>}
      </Space>
      <Text type="secondary">{formatDate(run.created_at)} · {run.duration_ms ?? 0} ms</Text>
      {run.validation_error && <Text type="danger">{run.validation_error}</Text>}
      {run.error_summary && <Text type="danger">{run.error_summary}</Text>}
    </div>
  );
}

export function OperatorWorkbench() {
  const [filter, setFilter] = useState<Exclude<ReviewFilter, "all">>("reply_ready");
  const [selectedReplyId, setSelectedReplyId] = useState<string>();
  const [draft, setDraft] = useState("");
  const [messageApi, messageContext] = message.useMessage();
  const queryClient = useQueryClient();
  const queueQuery = useQuery({
    queryKey: ["review-queue", filter],
    queryFn: () => getReviewQueue(filter),
  });
  const queueItems = queueQuery.data?.items ?? [];

  useEffect(() => {
    if (!queueItems.some((item) => item.reply.id === selectedReplyId)) {
      setSelectedReplyId(queueItems[0]?.reply.id);
    }
  }, [queueItems, selectedReplyId]);

  const detailQuery = useQuery({
    queryKey: ["review-item", selectedReplyId],
    queryFn: () => getReviewItem(selectedReplyId!),
    enabled: Boolean(selectedReplyId),
  });
  const detail = detailQuery.data;
  const detailItem = detail?.item;

  useEffect(() => {
    if (!detail) return;
    setDraft(detail.item.review_type === "model_failure" ? "" : suggestedReply(detail.item.run));
  }, [detail]);

  const decisionMutation = useMutation({
    mutationFn: submitReviewDecision,
    onSuccess: (response, variables) => {
      if (variables.outcome === "approve_draft") {
        messageApi.success("草稿已锁定，等待 BD 手动复制交接；系统不会发送消息。");
      } else {
        messageApi.success("该回复已关闭，不使用草稿。");
        setSelectedReplyId(undefined);
      }
      setDraft("");
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-item", response.reply.id] });
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "审核操作失败"),
  });

  const handoffMutation = useMutation({
    mutationFn: async ({ action, content, decisionId }: { action: HandoffAction; content: string; decisionId: string }) => {
      await createDraftExportRecord(decisionId);
      if (action === "copy") await copyDraftToClipboard(content);
      else downloadDraftAsText(content);
      return action;
    },
    onSuccess: (action) => {
      messageApi.success(action === "copy" ? "草稿已复制，并已记录交接审计。" : "草稿已下载，并已记录交接审计。");
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "交接操作失败；未发送任何消息。"),
  });

  const dncConfirmationMutation = useMutation({
    mutationFn: approveDncConfirmation,
    onSuccess: () => {
      messageApi.success("DNC 已由人工确认；系统不会向该达人发送消息。");
      setSelectedReplyId(undefined);
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "确认 DNC 失败"),
  });

  const dncRejectionMutation = useMutation({
    mutationFn: rejectDncConfirmation,
    onSuccess: () => {
      messageApi.success("已驳回 DNC 判断，并重新进入草稿生成队列。");
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-item"] });
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "驳回 DNC 失败"),
  });

  const retryMutation = useMutation({
    mutationFn: retryFailedReviewItem,
    onSuccess: () => {
      messageApi.success("已创建新的 Agent run，等待生成草稿；系统不会发送消息。");
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-item"] });
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "重新生成草稿失败"),
  });

  const dncBlocked = detailItem?.review_type === "dnc_confirmation" || detailItem?.review_type === "dnc_blocked";
  const terminal = detailItem?.review_type === "decline" || dncBlocked;
  const modelFailure = detailItem?.review_type === "model_failure";
  const generationPending = detailItem?.review_type === "generation_pending";
  const approvedDraft = detailItem?.review_type === "approved_draft" && !dncBlocked;
  const pendingDncConfirmation = detailItem?.review_type === "dnc_confirmation" && detailItem.dnc_confirmation?.status === "pending_confirmation";
  const canDecide = Boolean(detailItem?.decision_available && detailItem.run && !terminal);
  const canHandoff = Boolean(!dncBlocked && approvedDraft && detailItem?.decision?.outcome === "approve_draft" && detailItem.decision.final_draft);
  const conversation = useMemo(() => (detail ? buildTimeline(detail.context) : []), [detail]);
  const displayTitle = detailItem?.reply.subject || detailItem?.reply.body.slice(0, 72) || "选择一条待处理回复";

  const approve = () => {
    if (!detailItem?.run || !draft.trim()) {
      messageApi.warning("请先填写最终草稿，再锁定交接。");
      return;
    }
    decisionMutation.mutate({ runId: detailItem.run.id, outcome: "approve_draft", finalDraft: draft });
  };

  const closeWithoutDraft = () => {
    if (detailItem?.run) decisionMutation.mutate({ runId: detailItem.run.id, outcome: "close_without_draft" });
  };

  return (
    <div className="operator-workbench">
      {messageContext}
      <header className="workbench-header">
        <Space direction="vertical" size={1}>
          <Space size={10}>
            <SafetyCertificateOutlined className="header-icon" />
            <Title level={3}>运营审核工作台</Title>
          </Space>
          <Text type="secondary">会话式人工审核 · 演示审计身份：demo_operator</Text>
        </Space>
        <Tag color="blue">仅复制 / 下载交接，不提供发送能力</Tag>
      </header>

      <main className="workbench-grid">
        <aside className="workbench-panel queue-panel" aria-label="待处理会话">
          <div className="panel-heading">
            <Title level={5}>待处理会话</Title>
            <Text type="secondary">选择一位达人，集中查看对话与草稿</Text>
          </div>
          <div className="queue-filter-list" role="group" aria-label="审核队列分类">
            {filterOptions.map((option) => {
              const selected = filter === option.value;
              return (
                <button
                  aria-pressed={selected}
                  className={`queue-filter-option queue-filter-option-${option.tone} ${selected ? "queue-filter-option-selected" : ""}`}
                  key={option.value}
                  onClick={() => setFilter(option.value)}
                  type="button"
                >
                  <span className="queue-filter-icon" aria-hidden="true">{option.icon}</span>
                  <span className="queue-filter-copy">
                    <span className="queue-filter-label">{option.label}</span>
                    <span className="queue-filter-description">{option.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {queueQuery.isLoading && <Skeleton active paragraph={{ rows: 7 }} />}
          {queueQuery.isError && <Alert type="error" message="队列加载失败" description="请确认 FastAPI 服务正在运行。" />}
          {!queueQuery.isLoading && !queueQuery.isError && (
            <List
              className="queue-list"
              dataSource={queueItems}
              locale={{ emptyText: <Empty description="当前分类暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              renderItem={(item) => (
                <List.Item className="queue-list-row">
                  <QueueItem item={item} selected={selectedReplyId === item.reply.id} onSelect={() => setSelectedReplyId(item.reply.id)} />
                </List.Item>
              )}
            />
          )}
        </aside>

        <section className="workbench-panel conversation-panel" aria-label="达人会话">
          {detailQuery.isLoading && <Skeleton active paragraph={{ rows: 15 }} />}
          {detailQuery.isError && <Alert type="error" message="会话加载失败" description="该项可能刚刚被其他人工操作完成。" />}
          {!selectedReplyId && !queueQuery.isLoading && <Empty description="从左侧选择一条会话" />}
          {detail && detailItem && (
            <>
              <header className="conversation-header">
                <Avatar size={44} className="creator-avatar">{detail.context.creator.display_name?.slice(0, 1) || "达"}</Avatar>
                <div className="conversation-title">
                  <Space wrap size={8}>
                    <Title level={4}>{detail.context.creator.display_name || detail.context.creator.handle || detailItem.reply.from_email}</Title>
                    <Tag color={typeColor(detailItem.review_type)}>{typeLabels[detailItem.review_type]}</Tag>
                  </Space>
                  <Text type="secondary">{detail.context.creator.handle || detailItem.reply.from_email} · {displayTitle}</Text>
                </div>
              </header>

              <ConversationTimeline entries={conversation} />

              {generationPending && (
                <Alert className="conversation-state" type="info" showIcon message="草稿生成中" description="Agent 已在队列中处理。完成前不能编辑、批准或导出草稿。" />
              )}
              {modelFailure && (
                <Alert className="conversation-state" type="warning" showIcon message="模型未生成可用建议" description="可以从空白草稿起草，也可以在右侧明确点击人工重新生成。" />
              )}
              {terminal && detailItem.review_type === "decline" && (
                <Alert className="conversation-state" type="warning" showIcon message="达人已明确拒绝" description="这是只读终态记录，不可起草、批准、复制或下载。" />
              )}
              {dncBlocked && !pendingDncConfirmation && (
                <Alert className="conversation-state" type="error" showIcon message="DNC 已确认并阻断" description="该达人此前的草稿已隐藏，不能复制、下载、交接或发送。" />
              )}
              {pendingDncConfirmation && (
                <Card className="terminal-action-card" size="small">
                  <Space direction="vertical" className="full-width">
                    <Text strong>DNC 待人工确认</Text>
                    <Text type="secondary">确认后永久停止后续处理；驳回后只会重新进入草稿生成队列，不会发送消息。</Text>
                    <Space wrap>
                      <Popconfirm
                        title="确认永久 DNC"
                        description="确认后将停止该达人的后续 AI 处理和草稿导出。"
                        okText="确认 DNC"
                        cancelText="取消"
                        onConfirm={() => detailItem.dnc_confirmation && dncConfirmationMutation.mutate(detailItem.dnc_confirmation.id)}
                      >
                        <Button danger type="primary" loading={dncConfirmationMutation.isPending}>确认 DNC</Button>
                      </Popconfirm>
                      <Popconfirm
                        title="驳回并重新审核"
                        description="该回复将重新进入 Agent 草稿生成队列。"
                        okText="驳回并重新审核"
                        cancelText="取消"
                        onConfirm={() => detailItem.dnc_confirmation && dncRejectionMutation.mutate(detailItem.dnc_confirmation.id)}
                      >
                        <Button loading={dncRejectionMutation.isPending}>驳回 DNC</Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Card>
              )}
              {canDecide && (
                <Card className="draft-composer" size="small" title="人工草稿编辑器">
                  <Space direction="vertical" className="full-width" size="middle">
                    <Text type="secondary">AI 草稿只作参考。锁定后只能复制或下载，由 BD 在外部沟通工具中手动交接。</Text>
                    <Input.TextArea
                      aria-label="最终草稿"
                      autoSize={{ minRows: 5, maxRows: 10 }}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder={modelFailure ? "从空白草稿开始填写人工回复" : "编辑将要交接给 BD 的最终草稿"}
                      value={draft}
                    />
                    <Space wrap>
                      <Button type="primary" icon={<LockOutlined />} loading={decisionMutation.isPending} onClick={approve}>批准并锁定草稿</Button>
                      <Popconfirm
                        title="关闭，不使用草稿"
                        description="关闭后不能再恢复该条审核项。"
                        okText="关闭"
                        cancelText="取消"
                        onConfirm={closeWithoutDraft}
                      >
                        <Button danger loading={decisionMutation.isPending}>关闭，不使用草稿</Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Card>
              )}
              {canHandoff && detailItem.decision?.final_draft && (
                <Card className="locked-draft-card" size="small">
                  <Space direction="vertical" className="full-width" size="middle">
                    <Space wrap>
                      <CheckCircleOutlined className="locked-draft-icon" />
                      <Text strong>草稿已锁定待交接</Text>
                      <Tag color="success">人工批准</Tag>
                    </Space>
                    <Paragraph className="locked-draft-content">{detailItem.decision.final_draft}</Paragraph>
                    <Text type="secondary">复制或下载会记录审计快照；系统不会把此草稿发送到任何渠道。</Text>
                    <Space wrap>
                      <Button icon={<CopyOutlined />} loading={handoffMutation.isPending} onClick={() => handoffMutation.mutate({ action: "copy", content: detailItem.decision!.final_draft!, decisionId: detailItem.decision!.id })}>复制草稿</Button>
                      <Button icon={<DownloadOutlined />} loading={handoffMutation.isPending} onClick={() => handoffMutation.mutate({ action: "download", content: detailItem.decision!.final_draft!, decisionId: detailItem.decision!.id })}>下载 .txt</Button>
                      <Tooltip title="外部发送渠道尚未接入。请复制或下载草稿后，由 BD 在外部沟通工具中手动完成发送。">
                        <span><Button disabled>发送（暂未接入）</Button></span>
                      </Tooltip>
                    </Space>
                  </Space>
                </Card>
              )}
            </>
          )}
        </section>

        <aside className="workbench-panel copilot-panel" aria-label="AI 建议与上下文">
          {!detail && !detailQuery.isLoading && <Empty description="选择会话后显示 AI 建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          {detail && detailItem && (
            <Space direction="vertical" size="middle" className="full-width">
              <div className="panel-heading">
                <Title level={5}><RobotOutlined /> AI 协作建议</Title>
                <Text type="secondary">只提供分类、上下文、草稿与建议，不会自动发送或改变达人状态。</Text>
              </div>
              <Card className="copilot-suggestion-card" size="small" title="AI 草稿与判断">
                <Space direction="vertical" className="full-width" size="middle">
                  {dncBlocked ? (
                    <Alert type="error" showIcon message="DNC 已阻断草稿" description="为避免误联系，系统不会显示此前的 AI 草稿，也不提供复制、下载、交接或发送入口。" />
                  ) : modelFailure ? (
                    <>
                      <Alert type="warning" showIcon message="模型未生成可用建议" description={detailItem.run?.validation_error || detailItem.run?.error_summary || "请人工起草或重新生成。"} />
                      <Button icon={<ReloadOutlined />} loading={retryMutation.isPending} onClick={() => retryMutation.mutate(detailItem.reply.id)}>人工重新生成草稿</Button>
                    </>
                  ) : suggestedReply(detailItem.run) ? (
                    <>
                      <Paragraph className="ai-draft-preview">{suggestedReply(detailItem.run)}</Paragraph>
                      {canDecide && <Button onClick={() => setDraft(suggestedReply(detailItem.run))}>填入草稿编辑器</Button>}
                      <SuggestionMetadata output={detailItem.run?.output} />
                    </>
                  ) : generationPending ? (
                    <Text type="secondary">等待 Agent 完成后，这里会出现草稿和建议。</Text>
                  ) : (
                    <Text type="secondary">当前项没有可用的 AI 草稿。</Text>
                  )}
                </Space>
              </Card>
              <Collapse
                className="context-collapse"
                defaultActiveKey={["profile"]}
                items={[
                  {
                    key: "profile",
                    label: <Space><ProfileOutlined />达人与产品资料</Space>,
                    children: (
                      <Descriptions column={1} size="small">
                        <Descriptions.Item label="达人">{detail.context.creator.display_name || detail.context.creator.handle || "未提供"}</Descriptions.Item>
                        <Descriptions.Item label="负责人">{detail.context.creator.owner_bd || "未分配"}</Descriptions.Item>
                        <Descriptions.Item label="产品">{detail.context.product?.name || "未关联"}</Descriptions.Item>
                        <Descriptions.Item label="合作建议">{detail.context.creator.recommended_collab_type || "未提供"}</Descriptions.Item>
                        <Descriptions.Item label="产品卖点">{detail.context.product?.selling_points.join("；") || "未提供"}</Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                  {
                    key: "trace",
                    label: <Space><FileSearchOutlined />规则分类与 Agent 留痕</Space>,
                    children: (
                      <Space direction="vertical" className="full-width" size="small">
                        <Space wrap>
                          <Tag>{detailItem.reply.reply_category || "待判断"}</Tag>
                          {detailItem.reply.classification_confidence !== null && <Tag>规则置信度：{Math.round(detailItem.reply.classification_confidence * 100)}%</Tag>}
                        </Space>
                        {detail.runs.length > 0 ? detail.runs.map((run) => <RunTrace key={run.id} run={run} />) : <Text type="secondary">暂无 Agent run 留痕</Text>}
                      </Space>
                    ),
                  },
                  {
                    key: "reference",
                    label: "参考资料与开放待办",
                    children: (
                      <Space direction="vertical" className="full-width" size="small">
                        <Text>参考资料：{detail.context.reference_materials.length} 条</Text>
                        {detail.context.open_followup_tasks.length > 0
                          ? detail.context.open_followup_tasks.map((task) => <Text key={task.id}>{task.task_type} · {task.status}</Text>)
                          : <Text type="secondary">暂无开放待办</Text>}
                      </Space>
                    ),
                  },
                ]}
              />
            </Space>
          )}
        </aside>
      </main>
    </div>
  );
}
