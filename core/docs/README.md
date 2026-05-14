# X9 跨境数据库 (Database)

后续所有 AI 项目（爬虫 / 邀约话术 / 自动邮件 / 广告跟踪 / 视频脚本生成）的**唯一数据源**。

> 📖 **完整操作手册（含权限、启停、协作、突发故障、灾难恢复）**：[docs/操作手册.md](操作手册.md)
> 📖 与廖的协作规则：[docs/协作约定.md](协作约定.md)
> 📖 给廖的 API 使用指南：[docs/廖_API使用指南.md](廖_API使用指南.md)
> 📖 字段权威定义：[docs/schema.md](schema.md)
> 📖 变更日志：[docs/CHANGELOG.md](CHANGELOG.md)

**最常见操作速查**：
- 启动 → 双击 `run.bat`
- 停止 → 双击 `stop.bat`
- 重启 → 双击 `restart.bat`
- 改 .py 代码 → 直接保存，1-2s 自动热重启
- 加新管理员 → 前台 → 设置 → 用户管理 → 新建用户 → 签 Key（**绝不要把自己的 Key 给别人**）
- Key 丢了 → 看 [操作手册 §3](操作手册.md)
- **遇到任何疑问** → 前台 "🤖 AI 助手" tab 直接问（加载了所有运维文档）

## 当前规模 (首次导入)

- **产品 (product)**: 44 个 SKU，覆盖女性护理 / 成人护理 / 宠物 / 母婴 / 家居护理 / 口罩 6 大类目，含 19 个主推
- **达人 (creator)**: 66 个 TikTok 达人，含粉丝量 / 等级 / 状态 / 对接人
- **建联流水 (outreach)**: 101 条事件，从 3 份每周表导入并去重
- **产品图片 (product_image)**: 3143 条链接，覆盖 21 张 TK_Content 参考板 + 374 张实习生 A 社媒原图

## 一、目录结构

```
F:\Claude_Project\Database\
├─ database.db              SQLite 主库 (单一可信源)
├─ schema.sql               建表脚本
├─ run.bat                  双击启动 → 浏览器 http://localhost:18765/
├─ reimport.bat             重新跑所有导入 + 导出
├─ app\                     FastAPI 后端 + 前端
│  ├─ main.py
│  └─ static\index.html     前台单页
├─ scripts\
│  ├─ db_init.py            建库
│  ├─ import_products.py    44 SKUs 入库
│  ├─ import_images.py      图片归类入库
│  ├─ import_creators.py    66 达人 + 101 流水入库
│  ├─ export_json.py        导出 products.json / creators.json / outreach.json / tk_content_products.json
│  └─ export_xlsx.py        导出 产品总表.xlsx / 达人总表.xlsx / 建联流水.xlsx
├─ assets\
│  ├─ products\<sku>\       (留空, 之后手工放每 SKU 主图)
│  └─ reference-images\     21 张 TK_Content 规格板已就位
├─ exports\                 自动生成的 JSON / xlsx 镜像
└─ docs\
   ├─ README.md             本文档
   └─ schema.md             字段说明
```

## 二、首次启动 / 启动停止重启

| 操作 | 双击哪个文件 | 备注 |
|---|---|---|
| 启动 | `run.bat` | 浏览器自动打开 `http://localhost:18765/` |
| **停止** | `stop.bat` | 不要直接关 cmd 窗口，会留僵尸进程占住端口 |
| **重启** | `restart.bat` | 停 + 启动一气呵成 |

**端口被占用？** 编辑 `run.bat` 把 `set PORT=18765` 改成空闲端口（如 18766、8910、9100），同时编辑 `stop.bat` 同步改 `set PORT=` 那行。

### 关于"为什么关不掉服务"

`run.bat` 默认开了 `--reload`（你改 Python 代码时自动热重启），但这模式下 uvicorn 在 Windows 会派生**主进程 + worker 子进程**。直接 X 掉 cmd 窗口或 Ctrl+C 时，主进程退出但子进程偶尔会留下来占着端口。

**正确关闭姿势**：双击 `stop.bat` —— 它会找到正在监听 18765 的 python，连同子进程一起杀掉，再确认端口已空。

## 三、日常使用

### 浏览/编辑数据
- 直接在前台点击行 → 弹窗里改 → 保存
- 新增 SKU: 产品页 → "+ 新增 SKU"
- 新增达人: 达人页 → "+ 新增达人"
- 修改后立即写入 SQLite 并记审计日志 (audit_log 表)

### 重新导入原始数据
- 当 `F:\实习生\C达人建联\` 出现新的每周表，或更新了价格表 → 双击 `reimport.bat`
- 已存在的记录会被 **upsert** (按 sku_code / handle 去重)，不会丢手工新增的字段

### 导出 xlsx 给非技术同学
- `reimport.bat` 跑完后看 `exports\` 目录下三份总表
- xlsx 是只读镜像；改 xlsx **不会**回写到 DB

### 给 TK_Content 工作台喂数据
- `exports\tk_content_products.json` 是 PRODUCT_LIBRARY 兼容格式
- 后续 TK_Content 视频脚本工具可以直接 fetch 这个文件做产品下拉选择

## 四、扩展思路 (后续 AI 项目)

所有后续模块**走统一的 `/api/v1/*` 接口**，不需要后端再加端点。

| 项目 | 怎么接入 |
|---|---|
| AI 爬虫抓达人 | `POST /api/v1/data/creators/bulk` |
| AI 话术定制 | `GET /api/v1/queries/creators_to_contact` + `GET /api/v1/data/products/{sku}` |
| AI 自动邮件 | `GET /api/v1/queries/creators_follow_up` → `POST /api/v1/data/outreach/bulk` |
| 视频曝光跟踪 | `GET /api/v1/queries/outreach_video_tracking` → `PATCH /api/v1/data/outreach/{id}` |
| 广告跟踪 | `POST /api/v1/tables` 自助建 `ad_campaigns` 表，立即可用 |
| 订单同步 / 评论分析 / ... | 同上，新模块自助建表，张这边 UI 自动识别 |

详细接口文档（含 curl + Python 例子）：[`廖_API使用指南.md`](廖_API使用指南.md)

## 五、LLM 配置中心

后续所有 AI 任务（话术生成 / 内容分析 / 关键词分析 / ……）都从一个统一入口走，前端有个 "设置" tab 管理：

- 内置 3 个 Provider：**Anthropic Claude / OpenAI / DeepSeek**
- 支持自定义添加 OpenAI 兼容协议的 Provider（Moonshot Kimi / 智谱 / 通义 / 任意私有部署）
- 每个 Provider 单独配 Key + Base URL + 默认模型 + 额外 Header
- 同一时间只有 1 个 Provider 是 Active；同事调 `/api/v1/llm/complete` 时不传 provider 参数就走这个 Active
- 一键 "测试连通"：用 5 个 token 的 ping 探活，结果回写到 last_test_status
- API 响应里 Key 永远脱敏（`sk-a******cdef`），原始 Key 仅本机 SQLite 文件里有

**廖那边永远不接触 Key**：他调 `POST /api/v1/llm/complete` 就行，AI Key 由张统一保管。

## 五、字段细节

见 [`schema.md`](schema.md) 或直接看 [`schema.sql`](../schema.sql)。

## 六、待补字段 (TODO)

下列字段当前留空，等后续补料：
- `product.amazon_url` / `short_url` — 你 docx 里提到要补
- `product.pcs_per_pack` 部分缺失 — 需要核对
- `creator.email` / `whatsapp` — 现有触达全走 TK 私信，邮箱待收集
- `creator.followers` — 仅 1 个达人 (la_patrona_diana) 有粉丝数据，其他 65 个标 tier=C 占位，等 AI 爬虫补充

## 七、迁移到云

SQLite → Postgres / MySQL：把 `app/main.py` 里的 `sqlite3.connect(...)` 换成 SQLAlchemy + 一行连接串即可，schema 不动。
