# 建联（Outreach）模块说明

定制 + 发送达人建联邮件的端到端模块。MVP 阶段 **人工审核 → 一键发送**，
所有发送都要在弹窗里点"发送"按钮触发，不会自动批量寄件。

## 功能流程

1. 推荐列表每行末尾出现 **"建联"** 按钮。
2. 点击后弹窗显示：
   - 自动选好的话术模板（按 `recommended_collab_type` 匹配）
   - 自动渲染好的主题、正文、收件人
   - 底部 Gmail 连接状态条（未连 / 已连 / 报错）
3. 用户可以编辑任何字段、切换模板、点 **重新生成**。
4. **保存草稿** 把当前内容存进 `outreach_emails`，状态 `draft`。
5. **发送邮件** 经 Gmail API 出件，成功后：
   - 邮件状态变 `sent`，记录 `gmail_message_id`
   - 达人 `current_status` 自动改为 `已建联`（原值为空或"待建联"时）

## 数据库

新增两张表（首次启动时自动建表 + 自动填充默认模板）：

| 表名 | 用途 |
| --- | --- |
| `outreach_templates` | 话术模板（主题 + 正文 + 占位符） |
| `outreach_emails` | 每一封草稿 / 已发送 / 失败记录 |

## REST API（前缀 `/api/local/outreach`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/templates` | 列出所有模板 |
| POST | `/templates` | 新增模板 |
| PATCH | `/templates/{tpl_id}` | 更新模板 |
| DELETE | `/templates/{tpl_id}` | 删除模板 |
| POST | `/preview/{creator_id}` | 实时渲染（不入库） |
| POST | `/draft` | 创建草稿 |
| GET | `/drafts` | 列出草稿/已发送 |
| GET | `/history/{creator_id}` | 单个达人的历史 |
| PATCH | `/draft/{draft_id}` | 编辑草稿 |
| DELETE | `/draft/{draft_id}` | 取消草稿 |
| POST | `/send/{draft_id}` | 发送 |
| GET | `/gmail/status` | 是否已连 Gmail |
| GET | `/gmail/auth-url` | 获取 Google OAuth 授权链接 |
| GET | `/gmail/callback` | OAuth 回调（被 Google 重定向到） |
| POST | `/gmail/disconnect` | 删除本地 token |

## Gmail OAuth 配置

安装依赖：
```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

接下来你有 **两条路** 选一个走：

### A. 内置 OAuth 客户端（推荐 · 全团队零配置）

**项目维护者一次性配置**，所有 BD 成员后续直接点「连接 Gmail」就完事，
不用再碰 Google Cloud。

1. 去 [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials：
   - 启用 **Gmail API**
   - 新建 OAuth 2.0 Client ID，类型选 **Web application**
   - **Authorized JavaScript origins**（关键！必须登记）：
     ```
     http://localhost:8000
     http://localhost:8001
     http://localhost:8002
     http://localhost:8003
     http://localhost:8004
     http://localhost:8005
     ```
     登记 6 个的原因：应用启动时会动态选可用端口，避免被僵尸进程占用，
     范围是 8000-8005。Google 不支持通配符，所以每个端口单独登一行。
   - **Authorized redirect URIs**：留空即可。GIS 弹窗流程用 `postmessage`，
     不需要登记真实 URI。
2. 把 `client_id` 和 `client_secret` 写到环境变量（推荐放 `.env` 文件）：
   ```bash
   GMAIL_DEFAULT_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GMAIL_DEFAULT_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
   GMAIL_DEFAULT_PROJECT_ID=your-gcp-project-id
   ```
3. 重启后端。BD 成员的体验：
   - 推荐列表 → 点「建联」→ 弹窗
   - 点「Sign in with Google」按钮 → **弹一个 Google 小窗**
   - 在小窗里登录 / 授权 → 小窗自动关闭
   - 建联弹窗一直没动，状态条变绿 ✓

### B. 每个用户自己配（企业自托管 / 多组织部署）

适合每个团队/组织希望用自己的 Google Cloud 项目。

1. 去 Google Cloud Console 建 OAuth Client，类型选 **Desktop application**
2. 下载 JSON，**重命名为 `gmail_client_secret.json`**，放到：
   ```
   x9_creator_desktop_system/data/gmail_client_secret.json
   ```
   或者通过环境变量 `GMAIL_CLIENT_SECRET_PATH` 指向任意路径
3. 此文件存在时，会**优先用它**而不是内置默认客户端
4. token 自动迁移到 `gmail_accounts` 表里持久化，多账号共存

### 端口说明

应用启动时**自动选用 8000~8020 之间第一个空闲端口**，避免和别的服务冲突或被
僵尸进程占用。OAuth 回调的 `redirect_uri` 也会跟着动态变化（例如
`http://localhost:8003/api/local/outreach/gmail/callback`）。

因为 OAuth Client 类型是 **Desktop application**，Google 对 `http://localhost:<port>`
的回调一律放行，**不需要**在 Google Cloud Console 里登记每个端口。

> 企业 Workspace 也可以用 Service Account + Domain-Wide Delegation，
> 但普通 `@gmail.com` 账户必须走 OAuth2 流程（A 或 B 任选其一）。

### 使用流程（任一方式配置完后）

1. 推荐列表点任意「建联」按钮 → 弹窗
2. 弹窗下方点「连接 Gmail」→ 浏览器跳 Google 授权页
3. 授权完跳回控制台并自动重新打开建联弹窗
4. 选择发件人账号（多账号时） → 编辑邮件 → 一键发送

## 占位符（写模板时可用）

| 变量 | 说明 |
| --- | --- |
| `${handle}` | 达人 handle |
| `${display_name}` | 达人昵称 |
| `${profile_url}` | 主页链接 |
| `${bio_excerpt}` | 简介摘要（120 字内） |
| `${bio_hint}` | 自动包了一层"看了你简介里写的「…」，"的引子 |
| `${matched_keywords}` | 匹配到的关键词（前 3 个） |
| `${video_title}` | 来源视频标题 |
| `${video_hint}` | 自动包了一层"——尤其是《…》——"的引子 |
| `${product_type}` / `${product_label}` | 推荐产品代码 / 中文标签 |
| `${collab_type}` / `${collab_label}` | 合作类型代码 / 中文标签 |
| `${store_assigned}` | 分配店铺 |
| `${owner_bd}` | 对接人 |
| `${sender_name}` / `${sender_signature}` | 发件人署名 |

> 用 `string.Template.safe_substitute` 渲染——某个变量不存在不会抛异常，
> 而是保留原 `${var}` 文本，方便排错。

## 后接 AI 的钩子

`services/outreach_service.py::generate_with_ai` 已经预留接口：

```python
generate_with_ai(template, creator, use_ai=True)
```

只要在同目录新建 `ai_writer.py` 实现 `polish_email(subject, body, context)`
返回 `{"subject": ..., "body": ...}`，前端在 preview 接口传 `use_ai: true`
即可启用，整个 UI 和数据库结构无需变更。

## 测试

```bash
cd x9_creator_desktop_system
pytest backend/tests/test_outreach.py -v
```

测试用 `unittest.mock.patch` 把 Gmail send 替换成内存 stub，所以
**不需要装 google-* 也不需要联网就能跑通**。
