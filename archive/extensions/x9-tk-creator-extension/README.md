# TikTok Creator Lead Browser v2.2

X9 仪表盘上行采集 + TIKTOK全自动采集监控。

## 一键流程（用户操作）

1. Chrome → `chrome://extensions` → 开启右上角"开发者模式"
2. "加载已解压的扩展程序" → 选 `F:\AI Agent\Auto boker grab\tiktok-creator-lead-browser-extension-2.2`
3. **后端先起来**（要不然上传报错）：
   ```cmd
   cd F:\AI Agent\Auto boker grab\x9_creator_desktop_system
   start_desktop.bat
   ```
   后端在 `https://usx9.us`。
4. 浏览器开 `https://affiliate-us.tiktok.com/connection/creator`
5. 点扩展图标（或打开侧边栏） → 顶部红框 **TIKTOK全自动采集监控**
6. 后端地址默认 `https://usx9.us/api/local/collector/observations`
7. 点 **▶ 开始**

插件接管：
- **列表阶段**：自动下滑加载达人，逐行解析（handle / 名字 / Followers / GMV / 类别 / 邀约状态），即时上传到后端
- **详情阶段**：自动逐个点开达人详情页，等加载完，只采集原始可见文本 / DOM / 链接证据并立即上传，结构化解析交给后端
- **完成**：弹 Chrome 系统通知，统计区显示总数；不会自动下载 CSV/Excel

随时点 **⏸ 停止** 中断，下次按 **▶ 开始** 重新开一轮（不接续）。

## 状态面板

| 指标 | 含义 |
|---|---|
| 状态 pill | 闲置 / 运行中 / 已停止 / 已完成 / 错误 |
| 阶段 | 列表滚动采集中 / 详情逐个采集中 / 已完成 |
| 当前 | 现在正在处理的 @handle |
| 列表 | 列表阶段看到的去重 handle 总数 |
| 详情成功 | 详情页采集成功的数量，抓到后立即更新 |
| 详情失败 | 点不开 / 加载超时 |
| 错误 | 各阶段累计错误次数 |
| ⚠ 红字 | 最近一次错误简述 |

## 后端

需要后端能接收 `POST /api/local/collector/observations`，payload `platform = "tiktok_shop"` 走 TikTok Shop ingest service。这部分是 Stage 1 后端（已落地、41 + 16 + 7 + 5 个测试全过）。

采集完到 `https://usx9.us/portal/` 看入库的达人列表 / 详情；需要 CSV 时在后端页面手动导出。

## 常见排错

| 现象 | 原因 / 处理 |
|---|---|
| "active_tab_is_not_tiktok_shop" | 当前 tab URL 不是 affiliate-us/seller-us，切到列表页再点开始 |
| 启动后没动静 | DevTools (F12) → Console 看 content script 报错；可能页面还没完全渲染好 |
| 详情失败多 | TikTok Shop 用 SPA + 虚拟滚动，行被回收时再点击会失效；脚本会重试 3 次再放弃 |
| 上传失败 | 后端没起 / endpoint 写错；改 popup 里"后端地址"再试 |
| handle 不对 | 极少数情况：handle 字段把名字也吸进来了。后端有 handle 校验，会拒；详情失败计数会涨 |

## 文件清单

```
manifest.json          v2.2，匹配 www / affiliate-us / seller-us，permissions 加 alarms+notifications
background.js          (v2.0 原版) sidePanel 打开、storage 初始化
contentScript.js       (v2.0 原版) www.tiktok.com 走原 X9 流程
shop_collector.js      新：Shop 列表/详情解析 + 全自动编排（点击行→等待→采集→back→下一个）
shop_runner.js         新：service worker 状态机，监听消息 + 上传到后端
shop_panel.js          新：popup/sidepanel 上的 Shop UI（开始/停止/重置 + 实时计数）
popup.js               (v2.0 原版) 旧的 X9 / TikTok 控制逻辑
popup.html             (修改) 顶部插入 TIKTOK全自动采集监控面板
sidepanel.html         (修改) 顶部插入 TIKTOK全自动采集监控面板
popup.css              (v2.0 原版)
x9_sw.js               (修改 3 行) importScripts: background + x9_relay + shop_runner
x9_relay.js            (v2.0 原版) X9 dashboard 上行
```

## 与 v2.0 / 2.1 关系

- **v2.0** (`x9-tk-creator-extension.zip`)：只有 X9 dashboard relay + www.tiktok.com 采集
- **v2.1** (`tiktok-creator-lead-browser-extension-2.1/`, 之前合并尝试)：未完成的 v2.0 + 1.0.19 Shop 合并草稿
- **v2.2** (本目录)：以 v2.0 为底，添加 TikTok Shop **全自动**采集 + 上传到后端

## 不动的事
- 不点赞、不评论、不关注、不私信、不发帖
- 不绕过验证码、不使用代理
- 只采页面已经加载、可见的内容
- 触发频率有随机化（0.95–1.35 秒每次滚动），不开新 tab 并发，单线程跑
