import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  List,
  Popconfirm,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { approveDncConfirmation, getReviewItem, getReviewQueue, rejectDncConfirmation, retryFailedReviewItem, submitReviewDecision } from "./api";
import type { AgentRun, ReviewFilter, ReviewQueueItem, ReviewType } from "./types";

const { Paragraph, Text, Title } = Typography;

const filterOptions: Array<{
  description: string;
  icon: ReactNode;
  label: string;
  tone: "all" | "standard" | "model_failure" | "terminal";
  value: ReviewFilter;
}> = [
  { label: "全部待审", description: "查看全部待审项目", icon: <FileSearchOutlined />, tone: "all", value: "all" },
  { label: "普通回复", description: "AI 已生成草稿，可编辑后决定", icon: <MessageOutlined />, tone: "standard", value: "standard" },
  { label: "模型失败", description: "AI 未产出有效草稿，需人工起草", icon: <RobotOutlined />, tone: "model_failure", value: "model_failure" },
  { label: "明确拒绝", description: "终态项目，仅供查看", icon: <CloseCircleOutlined />, tone: "terminal", value: "decline" },
  { label: "DNC 待确认", description: "确认永久停止联系，或驳回后重新审核", icon: <SafetyCertificateOutlined />, tone: "terminal", value: "dnc_confirmation" },
];

const typeLabels: Record<ReviewType, string> = {
  standard: "普通回复",
  model_failure: "模型失败",
  decline: "拒绝",
  dnc_confirmation: "DNC 待确认",
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
  human_approval_required: "需人工确认后才能继续",
  "Human approval is required before any response is sent.": "需人工确认后才能继续",
  negotiation_requires_manual_review: "涉及合作条款，需人工复核",
  contact_delivery_failure: "联系方式可能失效，需人工核对",
  sensitive_collaboration_detail: "涉及敏感合作细节，需人工复核",
  unclear_reply: "回复意图不明确，需人工判断",
  missing_creator_context: "达人资料不足，需人工核对",
  missing_product_context: "产品资料不足，需人工补充",
  missing_campaign_timeline: "缺少合作时间线",
  missing_campaign_deliverables: "缺少交付要求",
  missing_budget_guidance: "缺少预算指引",
  demo_seed_requires_human_approval: "演示数据：需人工确认",
};

function suggestedActionLabel(value: unknown): string {
  return typeof value === "string" ? suggestedActionLabels[value] || "待人工判断下一步" : "未提供";
}

function confidencePresentation(value: unknown): { color?: "green" | "gold" | "red"; text: string } {
  if (typeof value !== "number" || !Number.isFinite(value)) return { text: "未提供" };

  const percentage = Math.round(Math.max(0, Math.min(1, value)) * 100);
  if (value >= 0.85) return { color: "green", text: `高（${percentage}%）` };
  if (value >= 0.6) return { color: "gold", text: `中（${percentage}%）` };
  return { color: "red", text: `低（${percentage}%）` };
}

function reviewReasonLabel(value: unknown): string {
  if (typeof value !== "string") return "需人工复核";
  return reviewReasonLabels[value] || "其他需人工复核事项";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function suggestedReply(run: AgentRun | null): string {
  const value = run?.output?.suggested_reply;
  return typeof value === "string" ? value : "";
}

function SuggestionMetadata({ output }: { output: Record<string, unknown> | null | undefined }) {
  const confidence = confidencePresentation(output?.confidence);
  const reasons = Array.isArray(output?.review_reasons) ? output.review_reasons.map(reviewReasonLabel) : [];

  return (
    <>
      <Space wrap>
        <Tag>建议下一步：{suggestedActionLabel(output?.next_action)}</Tag>
        <Tag color={confidence.color}>判断把握：{confidence.text}</Tag>
      </Space>
      {reasons.length > 0 && <Text type="secondary">复核提示：{reasons.join("、")}</Text>}
    </>
  );
}

function RunTrace({ run }: { run: AgentRun }) {
  return (
    <List.Item className="run-trace-row">
      <Space direction="vertical" size={2} className="full-width">
        <Space wrap>
          <Text strong>{run.id}</Text>
          <Tag color={run.execution_status === "failed" ? "error" : "processing"}>{run.execution_status}</Tag>
          <Tag>{run.llm_status}</Tag>
          {run.prompt_version && <Text type="secondary">{run.prompt_version}</Text>}
        </Space>
        <Text type="secondary">
          {formatDate(run.created_at)} · {run.duration_ms ?? 0} ms
        </Text>
        {run.created_by && <Text type="secondary">发起人：{run.created_by}</Text>}
        {run.validation_error && <Text type="danger">{run.validation_error}</Text>}
      </Space>
    </List.Item>
  );
}

function QueueItem({ item, selected, onSelect }: { item: ReviewQueueItem; selected: boolean; onSelect: () => void }) {
  const subject = item.reply.subject || item.reply.body.slice(0, 44);
  const color = item.review_type === "model_failure" ? "error" : item.review_type === "standard" ? "blue" : "gold";
  return (
    <button className={`queue-item ${selected ? "queue-item-selected" : ""}`} onClick={onSelect} type="button">
      <Space direction="vertical" size={4} className="full-width">
        <Space className="queue-item-header" align="start">
          <Text strong>{item.reply.from_email || item.reply.creator_id}</Text>
          <Tag color={color}>{typeLabels[item.review_type]}</Tag>
        </Space>
        <Text className="queue-item-subject" ellipsis>
          {subject}
        </Text>
        <Space size={6} wrap>
          <Text type="secondary">{item.reply.reply_category || "unclear"}</Text>
          <Text type="secondary">{formatDate(item.reply.message_at || item.reply.created_at)}</Text>
        </Space>
        {item.review_type === "model_failure" && <Text type="danger">{item.run?.llm_status || "模型处理失败"}</Text>}
      </Space>
    </button>
  );
}

export function OperatorWorkbench() {
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [selectedReplyId, setSelectedReplyId] = useState<string>();
  const [draft, setDraft] = useState("");
  const [messageApi, messageContext] = message.useMessage();
  const queryClient = useQueryClient();
  const queueQuery = useQuery({
    queryKey: ["review-queue", filter],
    queryFn: () => getReviewQueue(filter === "all" ? undefined : filter),
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

  useEffect(() => {
    if (!detail) return;
    setDraft(detail.item.review_type === "model_failure" ? "" : suggestedReply(detail.item.run));
  }, [detail]);

  const decisionMutation = useMutation({
    mutationFn: submitReviewDecision,
    onSuccess: (_, variables) => {
      messageApi.success(variables.outcome === "approve_draft" ? "草稿已由人工批准" : "已关闭，不使用草稿");
      setDraft("");
      setSelectedReplyId(undefined);
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: (error) => {
      messageApi.error(error instanceof Error ? error.message : "审核操作失败");
    },
  });

  const dncConfirmationMutation = useMutation({
    mutationFn: approveDncConfirmation,
    onSuccess: () => {
      messageApi.success("DNC 已由人工确认；系统不会向该达人发送消息。");
      setSelectedReplyId(undefined);
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: (error) => {
      messageApi.error(error instanceof Error ? error.message : "确认 DNC 失败");
    },
  });

  const dncRejectionMutation = useMutation({
    mutationFn: rejectDncConfirmation,
    onSuccess: () => {
      messageApi.success("DNC 判定已驳回；该回复已重新进入普通 Agent 审核队列。");
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-item"] });
    },
    onError: (error) => {
      messageApi.error(error instanceof Error ? error.message : "驳回 DNC 失败");
    },
  });

  const retryMutation = useMutation({
    mutationFn: retryFailedReviewItem,
    onSuccess: () => {
      messageApi.success("已创建新的 Agent run，等待 Worker 生成草稿；系统不会发送消息。");
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-item"] });
    },
    onError: (error) => {
      messageApi.error(error instanceof Error ? error.message : "重新生成草稿失败");
    },
  });

  const detailItem = detail?.item;
  const terminal = detailItem?.review_type === "decline" || detailItem?.review_type === "dnc_confirmation";
  const pendingDncConfirmation = detailItem?.review_type === "dnc_confirmation" && detailItem.dnc_confirmation?.status === "pending_confirmation";
  const dncDecisionPending = dncConfirmationMutation.isPending || dncRejectionMutation.isPending;
  const modelFailure = detailItem?.review_type === "model_failure";
  const canDecide = Boolean(detailItem?.decision_available && detailItem.run && !terminal);
  const referenceCount = detail?.context.reference_materials.length ?? 0;
  const title = useMemo(() => {
    if (!detailItem) return "选择一条待处理回复";
    return detailItem.reply.subject || detailItem.reply.body.slice(0, 72);
  }, [detailItem]);

  const approve = () => {
    if (!detailItem?.run || !draft.trim()) {
      messageApi.warning("请先填写最终草稿，再执行批准。 ");
      return;
    }
    decisionMutation.mutate({ runId: detailItem.run.id, outcome: "approve_draft", finalDraft: draft });
  };

  const closeWithoutDraft = () => {
    if (!detailItem?.run) return;
    decisionMutation.mutate({ runId: detailItem.run.id, outcome: "close_without_draft" });
  };

  const approveDnc = () => {
    const confirmationId = detailItem?.dnc_confirmation?.id;
    if (!pendingDncConfirmation || !confirmationId) return;
    dncConfirmationMutation.mutate(confirmationId);
  };

  const rejectDnc = () => {
    const confirmationId = detailItem?.dnc_confirmation?.id;
    if (!pendingDncConfirmation || !confirmationId) return;
    dncRejectionMutation.mutate(confirmationId);
  };

  const retryFailedReview = () => {
    if (!detailItem || !modelFailure) return;
    retryMutation.mutate(detailItem.reply.id);
  };

  return (
    <div className="workbench-shell">
      {messageContext}
      <header className="workbench-header">
        <Space direction="vertical" size={0}>
          <Space>
            <SafetyCertificateOutlined className="header-icon" />
            <Title level={3}>Operator Workbench</Title>
          </Space>
          <Text type="secondary">人工审核工作台 · 演示审计身份：demo_operator</Text>
        </Space>
        <Tag color="blue">无外发能力</Tag>
      </header>

      <main className="workbench-grid">
        <aside className="workbench-panel queue-panel" aria-label="待处理队列">
          <Space direction="vertical" size="middle" className="full-width">
            <div>
              <Title level={5}>待处理队列</Title>
              <Text type="secondary">仅显示需要人工核对的回复</Text>
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
            {queueQuery.isLoading && <Skeleton active paragraph={{ rows: 6 }} />}
            {queueQuery.isError && <Alert type="error" message="队列加载失败" description="请确认 FastAPI 服务正在运行。" />}
            {!queueQuery.isLoading && !queueQuery.isError && (
              <List
                className="queue-list"
                dataSource={queueItems}
                locale={{ emptyText: <Empty description="暂无待处理项" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(item) => (
                  <List.Item className="queue-list-row">
                    <QueueItem item={item} selected={selectedReplyId === item.reply.id} onSelect={() => setSelectedReplyId(item.reply.id)} />
                  </List.Item>
                )}
              />
            )}
          </Space>
        </aside>

        <section className="workbench-panel detail-panel" aria-label="审核详情">
          {detailQuery.isLoading && <Skeleton active paragraph={{ rows: 16 }} />}
          {detailQuery.isError && <Alert type="error" message="详情加载失败" description="该项可能已由其他人工操作完成。" />}
          {!selectedReplyId && !queueQuery.isLoading && <Empty description="选择左侧待处理项以查看详情" />}
          {detail && (
            <Space direction="vertical" size="large" className="full-width">
              <div>
                <Space wrap>
                  <Tag color={detailItem?.review_type === "model_failure" ? "error" : "blue"}>{typeLabels[detail.item.review_type]}</Tag>
                  <Text type="secondary">规则分类：{detail.item.reply.reply_category || "unclear"}</Text>
                  <Text type="secondary">{formatDate(detail.item.reply.message_at)}</Text>
                </Space>
                <Title level={4}>{title}</Title>
              </div>

              <Card size="small" title="当前入站消息">
                <Paragraph className="message-body">{detail.context.inbound_reply.body}</Paragraph>
                <Text type="secondary">分类依据：{detail.item.reply.classification_reason || "无规则命中"}</Text>
              </Card>

              <Card size="small" title="达人资料">
                <Descriptions size="small" column={2}>
                  <Descriptions.Item label="达人">{detail.context.creator.display_name || detail.context.creator.handle}</Descriptions.Item>
                  <Descriptions.Item label="平台">{detail.context.creator.platform}</Descriptions.Item>
                  <Descriptions.Item label="负责人">{detail.context.creator.owner_bd || "未分配"}</Descriptions.Item>
                  <Descriptions.Item label="粉丝量">{detail.context.creator.followers_count?.toLocaleString() || "未提供"}</Descriptions.Item>
                  <Descriptions.Item label="合作类型" span={2}>{detail.context.creator.recommended_collab_type || "未提供"}</Descriptions.Item>
                </Descriptions>
                {detail.context.creator.bio && <Paragraph type="secondary">{detail.context.creator.bio}</Paragraph>}
              </Card>

              <Card size="small" title="产品与参考资料" extra={<Text type="secondary">{referenceCount} 条资料</Text>}>
                {detail.context.product ? (
                  <Space direction="vertical" size={4}>
                    <Text strong>{detail.context.product.name}</Text>
                    <Paragraph>{detail.context.product.summary}</Paragraph>
                    <Space wrap>{detail.context.product.selling_points.map((point) => <Tag key={point}>{point}</Tag>)}</Space>
                  </Space>
                ) : (
                  <Text type="secondary">尚未匹配可用产品资料</Text>
                )}
              </Card>

              <Card size="small" title="沟通与 Agent 留痕">
                <Space direction="vertical" size="middle" className="full-width">
                  <div>
                    <Text strong>历史入站回复</Text>
                    <List
                      size="small"
                      dataSource={detail.context.recent_inbound_replies}
                      locale={{ emptyText: "暂无历史入站消息" }}
                      renderItem={(row) => <List.Item>{row.body}</List.Item>}
                    />
                  </div>
                  <div>
                    <Text strong>历史建联邮件</Text>
                    <List
                      size="small"
                      dataSource={detail.context.recent_outreach_emails}
                      locale={{ emptyText: "暂无历史建联邮件" }}
                      renderItem={(row) => <List.Item>{row.subject || row.body}</List.Item>}
                    />
                  </div>
                  <div>
                    <Text strong>Agent run</Text>
                    <List size="small" dataSource={detail.runs} renderItem={(run) => <RunTrace run={run} />} />
                  </div>
                </Space>
              </Card>
            </Space>
          )}
        </section>

        <aside className="workbench-panel action-panel" aria-label="人工审核操作">
          {!detail && <Empty description="等待选择审核项" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          {detail && terminal && (
            <Space direction="vertical" size="middle" className="full-width">
              <Alert
                showIcon
                type="warning"
                message={detail.item.review_type === "dnc_confirmation" ? "DNC 待人工确认" : "拒绝终态项仅供查看"}
                description={detail.item.review_type === "dnc_confirmation" ? "可确认永久停止后续联系，或驳回该 DNC 判定并重新进入普通审核；系统不会发送任何消息。" : "拒绝项仅供查看，不提供草稿编辑、复制或导出操作。"}
              />
              <Card size="small" title="终态依据">
                <Text>{detail.item.dnc_confirmation?.reason || detail.item.reply.classification_reason || "明确拒绝"}</Text>
              </Card>
              {pendingDncConfirmation && (
                <Space wrap>
                  <Popconfirm
                    cancelText="取消"
                    description="此操作会将达人标记为永久 DNC，并保留审核留痕；不会发送邮件。"
                    okButtonProps={{ danger: true, loading: dncConfirmationMutation.isPending }}
                    okText="确认永久 DNC"
                    onConfirm={approveDnc}
                    title="确认该达人不再接收后续联系？"
                  >
                    <Button aria-label="确认 DNC" danger disabled={dncDecisionPending} icon={<SafetyCertificateOutlined />} loading={dncConfirmationMutation.isPending} type="primary">
                      确认 DNC
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    cancelText="取消"
                    description="该回复会转为普通审核，并创建新的 Agent run；不会发送邮件或恢复已暂停的旧待办。"
                    okButtonProps={{ loading: dncRejectionMutation.isPending }}
                    okText="驳回并重新审核"
                    onConfirm={rejectDnc}
                    title="驳回此次 DNC 判定？"
                  >
                    <Button aria-label="驳回 DNC" disabled={dncDecisionPending} loading={dncRejectionMutation.isPending}>
                      驳回 DNC
                    </Button>
                  </Popconfirm>
                </Space>
              )}
            </Space>
          )}
          {detail && !terminal && (
            <Space direction="vertical" size="middle" className="full-width">
              <div>
                <Space>
                  <FileSearchOutlined className="header-icon" />
                  <Title level={5}>人工审核操作</Title>
                </Space>
                <Text type="secondary">AI 建议只供人工参考，不会自动改变达人状态。</Text>
              </div>
              {modelFailure ? (
                <Space direction="vertical" size="small" className="full-width">
                  <Alert
                    type="error"
                    showIcon
                    message="模型未生成可用建议"
                    description={`失败留痕：${detail.item.run?.validation_error || detail.item.run?.error_summary || detail.item.run?.llm_status}`}
                  />
                  <Button loading={retryMutation.isPending} onClick={retryFailedReview}>
                    人工重新生成草稿
                  </Button>
                  <Text type="secondary">点击后仅创建新的 Agent run，等待 Worker 处理；不会发送消息。</Text>
                </Space>
              ) : (
                <Card size="small" title="AI 建议">
                  <Space direction="vertical" size={6} className="full-width">
                    <Paragraph>{suggestedReply(detail.item.run) || "当前 run 未提供草稿。"}</Paragraph>
                    <SuggestionMetadata output={detail.item.run?.output} />
                  </Space>
                </Card>
              )}

              <div>
                <Text strong>最终草稿</Text>
                <Input.TextArea
                  aria-label="最终草稿"
                  autoSize={{ minRows: 9, maxRows: 18 }}
                  disabled={!canDecide || decisionMutation.isPending}
                  placeholder={modelFailure ? "模型失败，请由人工从空白草稿起草。" : "编辑后由人工确认。"}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
              </div>
              <Space wrap>
                <Button
                  icon={<CheckCircleOutlined />}
                  loading={decisionMutation.isPending}
                  type="primary"
                  disabled={!canDecide}
                  onClick={approve}
                >
                  批准草稿
                </Button>
                <Button
                  icon={<CloseCircleOutlined />}
                  loading={decisionMutation.isPending}
                  disabled={!canDecide}
                  onClick={closeWithoutDraft}
                >
                  关闭不用草稿
                </Button>
              </Space>
              <Alert
                showIcon
                type="info"
                icon={<ExclamationCircleOutlined />}
                message="本阶段不提供复制、导出或发送能力"
                description="批准仅保存人工审核决定；不会向任何渠道发送消息。"
              />
            </Space>
          )}
        </aside>
      </main>
    </div>
  );
}
