/* X9 creator lead dashboard. Served directly by FastAPI, no build step. */
if (window.location.pathname === "/ui" || window.location.pathname === "/ui/") {
  window.location.replace("/portal/");
  throw new Error("Redirecting legacy /ui/ entry to /portal/.");
}

const API = "/api/local";
const LANG_KEY = "x9_ui_language";
const OPERATOR_KEY = "x9_operator_name";
let currentPage = "dashboard";
let currentLanguage = localStorage.getItem(LANG_KEY) === "en" ? "en" : "zh";
let currentOperatorName = localStorage.getItem(OPERATOR_KEY) || "";
let currentUser = null;
let hotKwTimer = null;
let assistantHistory = [];

const $ = (sel) => document.querySelector(sel);
const dash = () => "-";

const I18N = {
  zh: {
    "app.title": "X9 达人线索后台",
    "nav.dashboard": "仪表盘",
    "nav.collection": "采集监控",
    "nav.recommendations": "推荐列表",
    "nav.review": "人工审核",
    "nav.export": "导出/导入达人",
    "nav.settings": "设置",
    "actions.languageTitle": "切换中英文",
    "actions.collectExtension": "插件采集",
    "actions.collectExtensionTitle": "通知插件立即采集当前 TikTok 页面",
    "actions.downloadExtension": "下载插件",
    "actions.downloadExtensionTitle": "下载并安装浏览器采集插件",
    "extInstall.title": "插件安装指引",
    "extInstall.intro": "插件已下载为 x9-tk-creator-extension.zip。按下面 4 步装到 Chrome:",
    "extInstall.step1": "1. 解压 zip 到一个固定的文件夹(以后别删,Chrome 启动时会读)。",
    "extInstall.step2": "2. 打开 Chrome 地址栏输入 chrome://extensions 回车,右上角开启「开发者模式」。",
    "extInstall.step3": "3. 点左上「加载已解压的扩展程序」,选刚才解压出来的那个文件夹(里面要能看到 manifest.json)。",
    "extInstall.step4": "4. 装好后,打开任意 TikTok 创作者页就会自动开始采集,数据会回到这个后台。",
    "extInstall.openChrome": "打开 chrome://extensions",
    "extInstall.close": "知道了",
    "extInstall.downloadFailed": "下载失败:{message}",
    "actions.runPipeline": "手动重跑流程",
    "actions.refresh": "刷新",
    "dashboard.title": "系统仪表盘",
    "dashboard.backend": "后端服务",
    "dashboard.database": "数据库",
    "dashboard.extension": "浏览器插件",
    "dashboard.tiktok": "TikTok 登录",
    "dashboard.creatorsToday": "今日达人",
    "dashboard.observationsToday": "今日采集",
    "dashboard.recommended": "已推荐",
    "dashboard.pendingReview": "暂存线索",
    "dashboard.latestWorker": "最近插件状态",
    "dashboard.versionText": "系统 {system} · 评分 {score} · 标签 {tag} · 推荐 {rec}",
    "state.running": "运行中",
    "state.stopped": "已停止",
    "state.connected": "已连接",
    "state.error": "异常",
    "state.online": "在线",
    "state.offlineLastSeen": "离线（最近出现过）",
    "state.notConnected": "尚未连接",
    "state.loggedIn": "已登录",
    "state.loggedOut": "未登录",
    "state.unknown": "未知",
    "dashboard.extensionHelp": "安装并打开浏览器插件后，它会把心跳状态发送到这里。",
    "collection.title": "采集监控",
    "collection.extensionTitle": "插件连接状态",
    "collection.onlineWorker": "在线插件",
    "collection.offlineWorker": "离线插件",
    "collection.notConnected": "尚未收到插件心跳",
    "collection.workerId": "Worker ID",
    "collection.version": "版本",
    "collection.tiktokLogin": "TikTok 登录",
    "collection.currentPage": "当前页面",
    "collection.lastHeartbeat": "最近心跳",
    "collection.currentUrl": "当前地址",
    "collection.noUrl": "暂无页面",
    "collection.heartbeatAgo": "{time}前",
    "collection.justNow": "刚刚",
    "collection.secondsShort": "{n} 秒",
    "collection.minutesShort": "{n} 分钟",
    "collection.hoursShort": "{n} 小时",
    "collection.daysShort": "{n} 天",
    "collection.progressTitle": "当前采集任务",
    "collection.guideTitle": "采集操作步骤",
    "collection.guideStep1": "下载并安装浏览器采集插件。",
    "collection.guideStep2": "打开 Chrome，登录 TikTok 账号，并保持插件启用。",
    "collection.guideStep3": "在 TikTok 搜索目标关键词，或打开要采集的达人主页。",
    "collection.guideStep4": "手动浏览达人内容，插件会自动上传有效线索和任务状态。",
    "collection.guideStep5": "回到本页查看当前任务概况，再到推荐列表处理达人。",
    "collection.keywordPlaceholder": "搜索关键词（覆盖 URL 里的 ?q=）",
    "collection.maxProfilesPlaceholder": "最多主页数",
    "collection.startAuto": "开始自动运行",
    "collection.stop": "停止",
    "collection.recentTitle": "最近采集记录",
    "collection.recentHelp": "浏览器插件上传的最近采集记录。",
    "collection.worker": "插件",
    "collection.account": "账号",
    "collection.keyword": "关键词",
    "collection.hash": "记录哈希",
    "collection.noProgress": "当前没有正在采集的任务",
    "collection.autoRun": "采集任务",
    "collection.step": "步骤",
    "collection.profiles": "主页",
    "collection.leads": "线索",
    "collection.pace": "速度",
    "collection.keywordInline": "关键词：{keyword}",
    "collection.skippedQueue": "跳过 {skipped} · 队列 {queue}",
    "collection.paceText": "{scrolls} 次滚动 · {rests} 次休息",
    "collection.running": "运行中",
    "collection.finished": "已结束",
    "collection.idle": "空闲",
    "collection.noObservations": "暂无采集记录",
    "collection.startSent": "已发送自动运行指令给插件",
    "collection.startFailed": "启动失败：{message}",
    "collection.stopSent": "已发送停止指令给插件",
    "collection.stopFailed": "停止失败：{message}",
    "recommendations.title": "达人推荐列表",
    "recommendations.handlePlaceholder": "搜索账号",
    "recommendations.contactPlaceholder": "联系方式关键词",
    "recommendations.bioPlaceholder": "简介关键词",
    "recommendations.filtering": "筛选中...",
    "recommendations.resultCount": "共 {count} 条",
    "recommendations.filterFailed": "筛选失败：{message}",
    "recommendations.profileLink": "达人主页",
    "filters.all": "全部",
    "filters.contactType": "类型",
    "filters.contactAll": "全部方式",
    "filters.contactAny": "有联系方式",
    "filters.noContact": "无联系方式",
    "filters.sortLabel": "排序",
    "filters.apply": "筛选",
    "filters.clear": "清空筛选",
    "filters.advancedToggle": "高级筛选 ▾",
    "filters.advancedHide": "收起筛选 ▴",
    "filters.advancedToggleTitle": "展开或收起高级筛选",
    "filters.allPriority": "全部优先级",
    "filters.allStatus": "全部状态",
    "filters.allQueue": "全部队列",
    "filters.reasonPlaceholder": "推荐原因",
    "filters.followersInvalid": "粉丝数格式不正确，请输入 ≥1K、≤10K 或 1K-100K",
    "filters.min": "最小",
    "filters.max": "最大",
    "filters.scoreHint": "推荐分≥",
    "filters.scoreHintTitle": "按推荐分过滤，输入最低分（0-100）",
    "filters.fitHint": "匹配分≥",
    "filters.fitHintTitle": "按匹配度过滤，输入最低分（0-100）",
    "filters.followersHint": "≥1K 或 1K-100K",
    "filters.followersHintTitle": "例：≥1K（一千以上）/ 1K-100K（一千到十万）/ ≤10K（一万以内）/ 5M（五百万以上），支持 K/M/B 后缀",
    "filters.keyword": "关键词",
    "filters.timeAll": "全部时间",
    "filters.lastDay": "最近一天",
    "filters.lastWeek": "最近一周",
    "filters.lastMonth": "最近一月",
    "filters.pickDate": "选择日期",
    "filters.pickDateTitle": "选择搜集日期",
    "sort.recommended": "综合推荐",
    "sort.collectedAt": "最新搜集",
    "sort.followers": "粉丝最多",
    "sort.score": "分数最高",
    "sort.fit": "匹配度最高",
    "sort.priority": "优先级最高",
    "sort.contactable": "可联系优先",
    "sort.micro": "小号测试优先",
    "table.creatorInfo": "博主信息",
    "table.storeOwner": "店铺/对接人",
    "table.contact": "联系方式",
    "table.profileBio": "达人简介",
    "table.collectedAt": "搜集时间",
    "table.followers": "粉丝数",
    "table.priority": "优先级",
    "table.queue": "队列",
    "table.product": "产品",
    "table.collab": "合作",
    "table.productCollab": "产品/合作",
    "table.score": "分数",
    "table.fit": "匹配度",
    "table.scoreFit": "评分",
    "table.scoreShort": "分",
    "filters.allProducts": "全部产品",
    "filters.allCollabs": "全部合作",
    "filters.scoreMin": "分≥",
    "filters.fitMin": "匹配≥",
    "table.status": "当前状态",
    "table.reason": "原因",
    "table.actions": "操作",
    "outreach.button": "建联",
    "outreach.title": "建联邮件 · @{handle}",
    "outreach.template": "话术模板",
    "outreach.scriptKeywords": "话术关键词",
    "outreach.scriptKeywordsPlaceholder": "如：baby diapers, pet review, authentic mom, TikTok Shop",
    "outreach.recipient": "收件人",
    "outreach.subject": "主题",
    "outreach.body": "邮件正文",
    "outreach.regenerate": "重新生成",
    "outreach.aiPersonalize": "AI \u4e2a\u6027\u5316",
    "outreach.aiHint": "\u6839\u636e\u8fbe\u4eba\u7b80\u4ecb\u3001\u63a8\u8350\u7406\u7531\u548c\u4ea7\u54c1\u65b9\u5411\u91cd\u5199\u8bdd\u672f",
    "outreach.tone": "\u8bed\u6c14",
    "outreach.toneFriendly": "\u53cb\u597d",
    "outreach.toneCasual": "\u81ea\u7136",
    "outreach.toneFormal": "\u6b63\u5f0f",
    "outreach.language": "\u8bed\u8a00",
    "outreach.generatingAi": "AI \u6b63\u5728\u751f\u6210\u8bdd\u672f...",
    "outreach.generatingTemplate": "\u6b63\u5728\u5957\u7528\u6a21\u677f...",
    "outreach.generatedAi": "AI \u8bdd\u672f\u5df2\u751f\u6210\uff0c\u8bf7\u68c0\u67e5\u540e\u4fdd\u5b58\u6216\u53d1\u9001\u3002",
    "outreach.generatedTemplate": "\u6a21\u677f\u8bdd\u672f\u5df2\u751f\u6210\u3002",
    "outreach.generatedKeyword": "\u5173\u952e\u8bcd\u8bdd\u672f\u5df2\u751f\u6210\u3002",
    "outreach.aiFallback": "AI \u672a\u751f\u6210\u6210\u529f\uff0c\u5df2\u5148\u586b\u5165\u6a21\u677f\u8bdd\u672f\u3002",
    "outreach.aiNotConfigured": "AI \u672a\u914d\u7f6e\uff0c\u5df2\u4f7f\u7528\u6a21\u677f\u8bdd\u672f\u3002",
    "outreach.aiUnavailable": "AI \u751f\u6210\u5668\u6682\u4e0d\u53ef\u7528\uff0c\u5df2\u4f7f\u7528\u6a21\u677f\u8bdd\u672f\u3002",
    "outreach.aiError": "AI \u751f\u6210\u5931\u8d25\uff0c\u5df2\u4f7f\u7528\u6a21\u677f\u8bdd\u672f\u3002",
    "outreach.variants": "\u53ef\u9009\u7248\u672c",
    "outreach.variant": "\u7248\u672c {index}",
    "outreach.saveDraft": "保存草稿",
    "outreach.send": "发送邮件",
    "outreach.cancel": "取消",
    "outreach.connectGmail": "连接 Gmail",
    "outreach.disconnectGmail": "断开 Gmail",
    "outreach.gmailReady": "Gmail 已连接：{email}",
    "outreach.gmailNotReady": "Gmail 尚未连接，无法发送，请先点击右上角\"连接 Gmail\"。",
    "outreach.gmailNotConfigured": "Gmail 未配置：把 OAuth 客户端 JSON 放到 data/gmail_client_secret.json，再点击连接。",
    "outreach.noEmail": "该达人没有邮箱，请手动填写收件人。",
    "outreach.confirmSend": "确认要把这封邮件发出去吗？",
    "outreach.sent": "成功发送",
    "outreach.sendFailed": "发送失败：{message}",
    "outreach.draftSaved": "草稿已保存",
    "outreach.regenerateFailed": "生成失败：{message}",
    "outreach.history": "建联历史",
    "outreach.noHistory": "暂无建联记录",
    "outreach.statusDraft": "草稿",
    "outreach.statusSent": "已发送",
    "outreach.statusFailed": "失败",
    "outreach.statusCancelled": "已取消",
    "outreach.statusQueued": "排队中",
    "outreach.openOAuth": "已打开浏览器请授权",
    "outreach.sender": "发件人",
    "outreach.accountUnit": "个账号",
    "outreach.defaultBadge": "默认",
    "outreach.setDefault": "设为默认",
    "outreach.removeAccount": "删除",
    "outreach.removeAccountConfirm": "确定删除这个 Gmail 账号？删除后该账号不能继续发件。",
    "outreach.addAccount": "添加 Gmail 账号",
    "assignment.store": "店铺",
    "assignment.owner": "对接人",
    "assignment.ownerPlaceholder": "对接人",
    "assignment.claim": "认领",
    "assignment.release": "释放",
    "assignment.taken": "已分配",
    "assignment.prompt": "请输入你的对接人姓名",
    "assignment.claimed": "已认领 @{handle}",
    "assignment.released": "已释放 @{handle}",
    "assignment.failed": "认领失败：{message}",
    "contact.email": "邮箱",
    "contact.whatsapp": "WhatsApp",
    "contact.instagram": "Instagram",
    "contact.link": "链接",
    "contact.telegram": "Telegram",
    "contact.line": "LINE",
    "contact.phone": "电话",
    "contact.facebook": "Facebook",
    "contact.dm": "私信",
    "recommendations.noMatch": "没有符合筛选条件的达人",
    "review.title": "人工审核",
    "review.creator": "博主",
    "review.riskTags": "风险标签",
    "review.action": "操作",
    "review.approve": "通过",
    "review.reject": "拒绝",
    "review.hold": "暂缓",
    "review.noTasks": "暂无待审核任务",
    "review.updated": "审核已更新：{action}",
    "review.failed": "处理失败：{message}",
    "export.title": "导出/导入达人",
    "export.help": "下载推荐达人 CSV。文件包含账号、主页链接、邮箱、简介联系方式、推荐产品、合作方式、触达优先级、推荐状态、推荐原因、风险标签和下一步动作。",
    "export.all": "导出全部推荐",
    "export.p1p2": "只导出 P1/P2",
    "import.creatorsTitle": "导入达人表格",
    "import.template": "下载模板",
    "import.run": "导入并自动运行流程",
    "import.pickFile": "请选择 CSV 或 XLSX 文件",
    "import.running": "导入中...",
    "import.done": "导入完成：新增 {inserted}，更新 {updated}，失败 {failed}",
    "import.failed": "导入失败：{message}",
    "settings.title": "设置",
    "settings.help": "当前后端配置。",
    "settings.groupApp": "应用",
    "settings.groupDb": "数据库",
    "settings.rawJson": "原始 JSON(调试用)",
    "dashboard.heroDetail": "浏览器扩展实时上传的创作者观察记录",
    "dashboard.systemStatus": "系统状态",
    "auth.loginTitle": "请先登录本地账号",
    "auth.loginHelp": "账号由用户自行注册，管理员审核通过后才能进入系统。Gmail 只用于登录后的发件授权。",
    "auth.loginButton": "去登录页",
    "auth.logout": "退出",
    "auth.notAllowed": "登录失败：{message}",
    "auth.allowedUsers": "允许登录邮箱",
    "auth.emailPlaceholder": "Gmail 邮箱",
    "auth.addUser": "添加/更新",
    "auth.email": "邮箱",
    "auth.role": "角色",
    "auth.status": "状态",
    "auth.active": "启用",
    "auth.disabled": "禁用",
    "auth.userSaved": "用户已保存",
    "auth.usersFailed": "用户列表失败：{message}",
    "pipeline.done": "流程已运行，处理 {count} 个达人",
    "pipeline.failed": "流程运行失败：{message}",
    "command.sent": "指令已发送给 {worker}",
    "command.collected": "已采集 {handle}：{action}",
    "command.unknownHandle": "未知账号",
    "command.done": "完成",
    "command.extensionError": "插件错误：{message}",
    "command.sendFailed": "发送指令失败：{message}",
    "queue.feminine_conversion_queue": "女性护理转化队列",
    "queue.feminine_warm_lead_queue": "女性护理暖线索",
    "queue.sample_collab_test_queue": "样品合作测试",
    "queue.affiliate_test_queue": "联盟合作测试",
    "queue.macro_brand_awareness_queue": "大号品牌曝光",
    "queue.manual_review_queue": "人工审核队列",
    "queue.low_confidence_hold": "低置信度暂存",
    "queue.general_lifestyle_hold": "泛生活暂缓",
    "queue.not_recommended_queue": "暂不推荐",
    "queue.no_contact_info_queue": "缺少联系方式",
    "product.feminine_care": "女性护理",
    "product.pet_care": "宠物护理",
    "product.home_care": "家居护理",
    "product.adult_care": "成人护理",
    "product.mom_baby": "母婴",
    "product.health_mask": "健康口罩",
    "product.general_lifestyle": "泛生活",
    "product.feminine_care_daily_liner": "日用护垫",
    "product.period_care_pad": "经期护理垫",
    "product.sensitive_skin_care": "敏感肌护理",
    "product.travel_hygiene_pack": "旅行卫生包",
    "product.postpartum_mom_care": "产后妈妈护理",
    "product.teen_first_period_care": "少女初潮护理",
    "product.wellness_self_care_bundle": "健康自护理组合",
    "collab.sample_collab": "寄样合作",
    "collab.gifted_review": "赠品测评",
    "collab.affiliate_collab": "联盟合作",
    "collab.paid_test_collab": "付费测试",
    "collab.brand_awareness_collab": "品牌曝光",
    "collab.do_not_contact_now": "暂不联系",
    "status.recommended": "推荐",
    "status.recommended_after_review": "审核后推荐",
    "status.low_cost_test": "低成本测试",
    "status.affiliate_test": "联盟测试",
    "status.brand_awareness_only": "仅品牌曝光",
    "status.manual_review_before_outreach": "触达前人工审核",
    "status.hold": "暂缓",
    "status.not_recommended_now": "暂不推荐",
    "status.no_contact_info": "无联系方式",
    "current_status.待建联": "待建联",
    "current_status.已建联": "已建联",
    "current_status.待回复": "待回复",
    "current_status.视频已发布": "视频已发布",
    "current_status.已寄样": "已寄样",
  },
  en: {
    "app.title": "X9 Creator Lead Dashboard",
    "nav.dashboard": "Dashboard",
    "nav.collection": "Collection Monitor",
    "nav.recommendations": "Recommendations",
    "nav.review": "Manual Review",
    "nav.export": "Export / Import Creators",
    "nav.settings": "Settings",
    "actions.languageTitle": "Switch language",
    "actions.collectExtension": "Collect via extension",
    "actions.collectExtensionTitle": "Ask the extension to collect the active TikTok page",
    "actions.downloadExtension": "Download extension",
    "actions.downloadExtensionTitle": "Download and install the TikTok collector extension",
    "extInstall.title": "How to install the extension",
    "extInstall.intro": "Downloaded as x9-tk-creator-extension.zip. Four steps to load it in Chrome:",
    "extInstall.step1": "1. Unzip into a folder you will keep (don't delete — Chrome reads it on each startup).",
    "extInstall.step2": "2. Open chrome://extensions, toggle on \"Developer mode\" in the top-right.",
    "extInstall.step3": "3. Click \"Load unpacked\" and pick the folder you just unzipped (it must contain manifest.json).",
    "extInstall.step4": "4. After loading, open any TikTok creator page. Collection starts automatically and data flows back to this dashboard.",
    "extInstall.openChrome": "Open chrome://extensions",
    "extInstall.close": "Got it",
    "extInstall.downloadFailed": "Download failed: {message}",
    "actions.runPipeline": "Re-run Pipeline",
    "actions.refresh": "Refresh",
    "dashboard.title": "System Dashboard",
    "dashboard.backend": "Backend",
    "dashboard.database": "Database",
    "dashboard.extension": "Browser Extension",
    "dashboard.tiktok": "TikTok Login",
    "dashboard.creatorsToday": "Creators Today",
    "dashboard.observationsToday": "Collections Today",
    "dashboard.recommended": "Recommended",
    "dashboard.pendingReview": "Held Leads",
    "dashboard.latestWorker": "Latest Extension Status",
    "dashboard.versionText": "System {system} · Score {score} · Tags {tag} · Rec {rec}",
    "state.running": "running",
    "state.stopped": "stopped",
    "state.connected": "connected",
    "state.error": "error",
    "state.online": "online",
    "state.offlineLastSeen": "offline (last seen)",
    "state.notConnected": "not connected",
    "state.loggedIn": "logged in",
    "state.loggedOut": "logged out",
    "state.unknown": "unknown",
    "dashboard.extensionHelp": "Install and open the browser extension. Its heartbeat will appear here.",
    "collection.title": "Collection Monitor",
    "collection.extensionTitle": "Extension Connection",
    "collection.onlineWorker": "Online Extension",
    "collection.offlineWorker": "Offline Extension",
    "collection.notConnected": "No extension heartbeat yet",
    "collection.workerId": "Worker ID",
    "collection.version": "Version",
    "collection.tiktokLogin": "TikTok Login",
    "collection.currentPage": "Current Page",
    "collection.lastHeartbeat": "Last Heartbeat",
    "collection.currentUrl": "Current URL",
    "collection.noUrl": "No page yet",
    "collection.heartbeatAgo": "{time} ago",
    "collection.justNow": "just now",
    "collection.secondsShort": "{n} sec",
    "collection.minutesShort": "{n} min",
    "collection.hoursShort": "{n} hr",
    "collection.daysShort": "{n} d",
    "collection.progressTitle": "Current Collection Task",
    "collection.guideTitle": "Collection Steps",
    "collection.guideStep1": "Download and install the browser collection extension.",
    "collection.guideStep2": "Open Chrome, sign in to TikTok, and keep the extension enabled.",
    "collection.guideStep3": "Search target keywords on TikTok, or open the creator profile you want to collect.",
    "collection.guideStep4": "Browse creator content manually; the extension uploads valid leads and task status.",
    "collection.guideStep5": "Return here to check the current task summary, then process creators in Recommendations.",
    "collection.keywordPlaceholder": "Search keyword (overrides URL ?q=)",
    "collection.maxProfilesPlaceholder": "Max profiles",
    "collection.startAuto": "Start Auto-run",
    "collection.stop": "Stop",
    "collection.recentTitle": "Recent Collections",
    "collection.recentHelp": "Recent collection records uploaded by the browser extension.",
    "collection.worker": "Worker",
    "collection.account": "Account",
    "collection.keyword": "Keyword",
    "collection.hash": "Hash",
    "collection.noProgress": "No collection task is currently running.",
    "collection.autoRun": "Collection Task",
    "collection.step": "Step",
    "collection.profiles": "Profiles",
    "collection.leads": "Leads",
    "collection.pace": "Pace",
    "collection.keywordInline": "keyword: {keyword}",
    "collection.skippedQueue": "skipped {skipped} · queue {queue}",
    "collection.paceText": "{scrolls} scrolls · {rests} rests",
    "collection.running": "running",
    "collection.finished": "finished",
    "collection.idle": "idle",
    "collection.noObservations": "No collection records yet",
    "collection.startSent": "Auto-run command sent to extension",
    "collection.startFailed": "Start failed: {message}",
    "collection.stopSent": "Stop command sent to extension",
    "collection.stopFailed": "Stop failed: {message}",
    "recommendations.title": "Creator Recommendations",
    "recommendations.handlePlaceholder": "Search handle",
    "recommendations.contactPlaceholder": "Contact keyword",
    "recommendations.bioPlaceholder": "Bio keyword",
    "recommendations.filtering": "Filtering...",
    "recommendations.resultCount": "{count} results",
    "recommendations.filterFailed": "Filter failed: {message}",
    "recommendations.profileLink": "Profile",
    "filters.all": "All",
    "filters.contactType": "Type",
    "filters.contactAll": "All methods",
    "filters.contactAny": "Has contact",
    "filters.noContact": "No contact",
    "filters.sortLabel": "Sort",
    "filters.apply": "Apply",
    "filters.clear": "Clear filters",
    "filters.advancedToggle": "More filters ▾",
    "filters.advancedHide": "Less filters ▴",
    "filters.advancedToggleTitle": "Show or hide advanced filters",
    "filters.allPriority": "All priority",
    "filters.allStatus": "All status",
    "filters.allQueue": "All queues",
    "filters.reasonPlaceholder": "Recommendation reason",
    "filters.followersInvalid": "Follower format is invalid. Try ≥1K, ≤10K, or 1K-100K.",
    "filters.min": "Min",
    "filters.max": "Max",
    "filters.scoreHint": "Score ≥",
    "filters.scoreHintTitle": "Filter by recommendation score (0-100)",
    "filters.fitHint": "Fit ≥",
    "filters.fitHintTitle": "Filter by primary product fit score (0-100)",
    "filters.followersHint": "≥1K or 1K-100K",
    "filters.followersHintTitle": "Examples: ≥1K (over 1k) / 1K-100K (1k–100k) / ≤10K (under 10k) / 5M (over 5m). Supports K/M/B suffixes.",
    "filters.keyword": "Keyword",
    "filters.timeAll": "All time",
    "filters.lastDay": "Last day",
    "filters.lastWeek": "Last week",
    "filters.lastMonth": "Last month",
    "filters.pickDate": "Pick date",
    "filters.pickDateTitle": "Pick collection date",
    "sort.recommended": "Recommended mix",
    "sort.collectedAt": "Newest collected",
    "sort.followers": "Most followers",
    "sort.score": "Highest score",
    "sort.fit": "Highest fit",
    "sort.priority": "Highest priority",
    "sort.contactable": "Contactable first",
    "sort.micro": "Micro test first",
    "table.creatorInfo": "Creator Info",
    "table.storeOwner": "Store / Owner",
    "table.contact": "Contact",
    "table.profileBio": "Profile Bio",
    "table.collectedAt": "Collection Time",
    "table.followers": "Followers",
    "table.priority": "Priority",
    "table.queue": "Queue",
    "table.product": "Product",
    "table.collab": "Collab",
    "table.productCollab": "Product / Collab",
    "table.score": "Score",
    "table.fit": "Fit",
    "table.scoreFit": "Score",
    "table.scoreShort": "pts",
    "filters.allProducts": "All products",
    "filters.allCollabs": "All collabs",
    "filters.scoreMin": "Score≥",
    "filters.fitMin": "Fit≥",
    "table.status": "Current Status",
    "table.reason": "Reason",
    "table.actions": "Actions",
    "outreach.button": "Outreach",
    "outreach.title": "Outreach email · @{handle}",
    "outreach.template": "Template",
    "outreach.scriptKeywords": "Script keywords",
    "outreach.scriptKeywordsPlaceholder": "e.g. baby diapers, pet review, authentic mom, TikTok Shop",
    "outreach.recipient": "To",
    "outreach.subject": "Subject",
    "outreach.body": "Body",
    "outreach.regenerate": "Regenerate",
    "outreach.aiPersonalize": "AI personalize",
    "outreach.aiHint": "Rewrite using the creator bio, recommendation reason, and product direction",
    "outreach.tone": "Tone",
    "outreach.toneFriendly": "Friendly",
    "outreach.toneCasual": "Casual",
    "outreach.toneFormal": "Formal",
    "outreach.language": "Language",
    "outreach.generatingAi": "AI is generating outreach copy...",
    "outreach.generatingTemplate": "Rendering template...",
    "outreach.generatedAi": "AI outreach copy is ready. Review before saving or sending.",
    "outreach.generatedTemplate": "Template copy is ready.",
    "outreach.generatedKeyword": "Keyword script is ready.",
    "outreach.aiFallback": "AI did not return a usable draft; template copy is shown.",
    "outreach.aiNotConfigured": "AI is not configured; template copy is shown.",
    "outreach.aiUnavailable": "AI writer is unavailable; template copy is shown.",
    "outreach.aiError": "AI generation failed; template copy is shown.",
    "outreach.variants": "Variants",
    "outreach.variant": "Version {index}",
    "outreach.saveDraft": "Save draft",
    "outreach.send": "Send email",
    "outreach.cancel": "Cancel",
    "outreach.connectGmail": "Connect Gmail",
    "outreach.disconnectGmail": "Disconnect Gmail",
    "outreach.gmailReady": "Gmail connected as {email}",
    "outreach.gmailNotReady": "Gmail is not connected. Click \"Connect Gmail\" to authorize.",
    "outreach.gmailNotConfigured": "Gmail OAuth client missing. Drop the JSON in data/gmail_client_secret.json then connect.",
    "outreach.noEmail": "This creator has no email on file — fill in the recipient manually.",
    "outreach.confirmSend": "Send this email now?",
    "outreach.sent": "Sent successfully",
    "outreach.sendFailed": "Send failed: {message}",
    "outreach.draftSaved": "Draft saved",
    "outreach.regenerateFailed": "Regenerate failed: {message}",
    "outreach.history": "Outreach history",
    "outreach.noHistory": "No outreach history",
    "outreach.statusDraft": "draft",
    "outreach.statusSent": "sent",
    "outreach.statusFailed": "failed",
    "outreach.statusCancelled": "cancelled",
    "outreach.statusQueued": "queued",
    "outreach.openOAuth": "Browser opened for Google authorization",
    "outreach.sender": "Sender",
    "outreach.accountUnit": "account(s)",
    "outreach.defaultBadge": "Default",
    "outreach.setDefault": "Set as default",
    "outreach.removeAccount": "Remove",
    "outreach.removeAccountConfirm": "Remove this Gmail account? It will no longer be available for sending.",
    "outreach.addAccount": "Add Gmail account",
    "assignment.store": "Store",
    "assignment.owner": "Owner",
    "assignment.ownerPlaceholder": "Owner",
    "assignment.claim": "Claim",
    "assignment.release": "Release",
    "assignment.taken": "Assigned",
    "assignment.prompt": "Enter your owner name",
    "assignment.claimed": "Claimed @{handle}",
    "assignment.released": "Released @{handle}",
    "assignment.failed": "Assignment failed: {message}",
    "contact.email": "Email",
    "contact.whatsapp": "WhatsApp",
    "contact.instagram": "Instagram",
    "contact.link": "Link",
    "contact.telegram": "Telegram",
    "contact.line": "LINE",
    "contact.phone": "Phone",
    "contact.facebook": "Facebook",
    "contact.dm": "DM",
    "recommendations.noMatch": "No creators match these filters",
    "review.title": "Manual Review",
    "review.creator": "Creator",
    "review.riskTags": "Risk Tags",
    "review.action": "Action",
    "review.approve": "Approve",
    "review.reject": "Reject",
    "review.hold": "Hold",
    "review.noTasks": "No pending review tasks",
    "review.updated": "Review updated: {action}",
    "review.failed": "Update failed: {message}",
    "export.title": "Export / Import Creators",
    "export.help": "Download a CSV of recommended creators. The file includes handle, profile link, email, bio contact methods, recommended product, collab type, outreach priority, recommendation status, reason, risk tags, and next action.",
    "export.all": "Export all recommended",
    "export.p1p2": "Export P1/P2 only",
    "import.creatorsTitle": "Import Creator Table",
    "import.template": "Download template",
    "import.run": "Import and run pipeline",
    "import.pickFile": "Choose a CSV or XLSX file",
    "import.running": "Importing...",
    "import.done": "Import done: {inserted} inserted, {updated} updated, {failed} failed",
    "import.failed": "Import failed: {message}",
    "settings.title": "Settings",
    "settings.help": "Current backend configuration.",
    "settings.groupApp": "App",
    "settings.groupDb": "Database",
    "settings.rawJson": "Raw JSON (debug)",
    "dashboard.heroDetail": "Live creator observations uploaded by the browser extension.",
    "dashboard.systemStatus": "System status",
    "auth.loginTitle": "Sign in with a local account",
    "auth.loginHelp": "Users register with username and password. Admin approval is required before access. Gmail is only used for sending email after login.",
    "auth.loginButton": "Open login page",
    "auth.logout": "Log out",
    "auth.notAllowed": "Sign-in failed: {message}",
    "auth.allowedUsers": "Allowed Gmail users",
    "auth.emailPlaceholder": "Gmail email",
    "auth.addUser": "Add / update",
    "auth.email": "Email",
    "auth.role": "Role",
    "auth.status": "Status",
    "auth.active": "Active",
    "auth.disabled": "Disabled",
    "auth.userSaved": "User saved",
    "auth.usersFailed": "User list failed: {message}",
    "pipeline.done": "Pipeline ran on {count} creators",
    "pipeline.failed": "Pipeline failed: {message}",
    "command.sent": "Command sent to {worker}",
    "command.collected": "Collected {handle}: {action}",
    "command.unknownHandle": "unknown handle",
    "command.done": "done",
    "command.extensionError": "Extension error: {message}",
    "command.sendFailed": "Send command failed: {message}",
    "queue.feminine_conversion_queue": "Feminine conversion queue",
    "queue.feminine_warm_lead_queue": "Feminine warm leads",
    "queue.sample_collab_test_queue": "Sample collab test",
    "queue.affiliate_test_queue": "Affiliate test",
    "queue.macro_brand_awareness_queue": "Macro brand awareness",
    "queue.manual_review_queue": "Manual review queue",
    "queue.low_confidence_hold": "Low-confidence hold",
    "queue.general_lifestyle_hold": "General lifestyle hold",
    "queue.not_recommended_queue": "Not recommended",
    "queue.no_contact_info_queue": "No contact info",
    "product.feminine_care": "Feminine care",
    "product.pet_care": "Pet care",
    "product.home_care": "Home care",
    "product.adult_care": "Adult care",
    "product.mom_baby": "Mom & baby",
    "product.health_mask": "Health mask",
    "product.general_lifestyle": "General lifestyle",
    "product.feminine_care_daily_liner": "Daily liner",
    "product.period_care_pad": "Period care pad",
    "product.sensitive_skin_care": "Sensitive skin care",
    "product.travel_hygiene_pack": "Travel hygiene pack",
    "product.postpartum_mom_care": "Postpartum mom care",
    "product.teen_first_period_care": "Teen first-period care",
    "product.wellness_self_care_bundle": "Wellness self-care bundle",
    "collab.sample_collab": "Sample collab",
    "collab.gifted_review": "Gifted review",
    "collab.affiliate_collab": "Affiliate collab",
    "collab.paid_test_collab": "Paid test collab",
    "collab.brand_awareness_collab": "Brand awareness",
    "collab.do_not_contact_now": "Do not contact now",
    "status.recommended": "Recommended",
    "status.recommended_after_review": "Recommended after review",
    "status.low_cost_test": "Low-cost test",
    "status.affiliate_test": "Affiliate test",
    "status.brand_awareness_only": "Brand awareness only",
    "status.manual_review_before_outreach": "Manual review before outreach",
    "status.hold": "Hold",
    "status.not_recommended_now": "Not recommended now",
    "status.no_contact_info": "No contact info",
    "current_status.待建联": "To contact",
    "current_status.已建联": "Contacted",
    "current_status.待回复": "Waiting reply",
    "current_status.视频已发布": "Video published",
    "current_status.已寄样": "Sample sent",
  },
};

function t(key, vars = {}) {
  const text = I18N[currentLanguage]?.[key] || I18N.zh[key] || key;
  return Object.entries(vars).reduce((out, [name, value]) => {
    return out.replaceAll(`{${name}}`, value ?? "");
  }, text);
}

function codeLabel(group, code) {
  if (!code) return dash();
  return I18N[currentLanguage]?.[`${group}.${code}`] || I18N.zh[`${group}.${code}`] || I18N.en[`${group}.${code}`] || code;
}

function applyI18n(root = document) {
  document.documentElement.lang = currentLanguage === "zh" ? "zh-CN" : "en";
  document.title = t("app.title");
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const value = t(el.dataset.i18nTitle);
    el.title = value;
    if (el.hasAttribute("aria-label")) el.setAttribute("aria-label", value);
  });
  syncLanguageToggle();
}

function syncLanguageToggle() {
  const btn = document.getElementById("btn-language");
  if (!btn) return;
  const label = btn.querySelector(".lang-current");
  if (label) label.textContent = currentLanguage === "zh" ? "中" : "EN";
  // Tooltip shows the destination, so the click intent is obvious.
  const tip = currentLanguage === "zh" ? "Switch to English" : "切换到中文";
  btn.title = tip;
  btn.setAttribute("aria-label", tip);
  btn.setAttribute("data-current", currentLanguage);
}

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const payload = await r.json().catch(() => ({}));
    throw new Error(payload.detail || `${path} -> ${r.status}`);
  }
  return r.json();
}

async function fetchCurrentUser() {
  try {
    const r = await api("/auth/me");
    return r.logged_in ? r.user : null;
  } catch {
    return null;
  }
}

function renderLoginScreen() {
  window.location.href = "/login";
  return;
  document.body.innerHTML = `
    <main class="page" style="max-width:520px;margin:80px auto">
      <h2>${escapeHtml(t("auth.loginTitle"))}</h2>
      <p class="subtle">${escapeHtml(t("auth.loginHelp"))}</p>
      <div class="actions" style="margin-top:18px">
        <button class="primary" id="login-gmail" type="button">${gsiLogoSvg()}<span>${escapeHtml(t("auth.loginButton"))}</span></button>
        <button class="ghost language-toggle" id="login-language" type="button">${currentLanguage === "zh" ? "EN" : "中文"}</button>
      </div>
    </main>
    <div id="outreach-modal-root"></div>
  `;
  document.getElementById("login-gmail").addEventListener("click", (e) => triggerGisPopup(e.currentTarget));
  document.getElementById("login-language").addEventListener("click", () => {
    currentLanguage = currentLanguage === "zh" ? "en" : "zh";
    localStorage.setItem(LANG_KEY, currentLanguage);
    renderLoginScreen();
  });
}

function updateCurrentUserBar() {
  const el = document.getElementById("current-user");
  const avatar = document.getElementById("user-avatar");
  const name = currentUser?.display_name || currentUser?.username || currentUser?.identity || currentUser?.email || "";
  const scope = currentUser?.department_name || currentUser?.role || "";
  if (el) el.textContent = name ? `${name}` : "";
  if (el && scope) el.title = `${name} · ${scope}`;
  if (avatar) {
    const firstChar = (name || "?").trim().charAt(0).toUpperCase();
    avatar.textContent = firstChar || "?";
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Minimal markdown renderer for AI assistant messages.
// Escapes HTML first, then applies safe inline patterns.
function renderMarkdown(text) {
  let s = escapeHtml(text);
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  s = s.replace(/^[-•]\s+(.+)$/gm, "· $1");
  s = s.replace(/\n/g, "<br>");
  return s;
}

function formatTime(value) {
  if (!value) return dash();
  const raw = String(value);
  const date = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleString(currentLanguage === "zh" ? "zh-CN" : "en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }
  return raw.replace("T", " ").slice(0, 19);
}

function formatRelativeTime(value) {
  if (!value) return dash();
  const raw = String(value);
  const date = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return raw.replace("T", " ").slice(0, 19);
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 10) return t("collection.justNow");
  if (seconds < 60) return t("collection.secondsShort", { n: seconds });
  if (seconds < 3600) return t("collection.minutesShort", { n: Math.floor(seconds / 60) });
  if (seconds < 86400) return t("collection.hoursShort", { n: Math.floor(seconds / 3600) });
  return t("collection.daysShort", { n: Math.floor(seconds / 86400) });
}

function heartbeatLabel(value) {
  if (!value) return dash();
  const relative = formatRelativeTime(value);
  const ago = relative === t("collection.justNow") ? relative : t("collection.heartbeatAgo", { time: relative });
  return `${ago} · ${formatTime(value)}`;
}

function compactWorkerId(value) {
  const raw = String(value || "").trim();
  if (!raw) return dash();
  if (raw.length <= 22) return raw;
  return `${raw.slice(0, 10)}...${raw.slice(-8)}`;
}

function pageTypeLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return dash();
  const zh = {
    search_results: "搜索结果",
    profile: "达人主页",
    video: "视频页",
    home: "首页",
  };
  const en = {
    search_results: "Search results",
    profile: "Profile",
    video: "Video",
    home: "Home",
  };
  const map = currentLanguage === "zh" ? zh : en;
  return map[raw] || raw.replace(/_/g, " ");
}

function pageStatusLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return dash();
  const zh = {
    on_tiktok: "TikTok 页面",
    off_tiktok: "非 TikTok 页面",
    not_tiktok: "非 TikTok 页面",
    blocked: "受限页面",
    unknown: "未知页面",
  };
  const en = {
    on_tiktok: "TikTok page",
    off_tiktok: "Not TikTok",
    not_tiktok: "Not TikTok",
    blocked: "Blocked page",
    unknown: "Unknown page",
  };
  const map = currentLanguage === "zh" ? zh : en;
  return map[raw] || raw.replace(/_/g, " ");
}

function formatUrlForPanel(value) {
  const raw = String(value || "").trim();
  if (!raw) return t("collection.noUrl");
  try {
    const url = new URL(raw);
    const keyword = url.searchParams.get("q");
    const path = url.pathname === "/" ? "" : url.pathname.replace(/\/$/, "");
    return keyword ? `${url.hostname}${path}?q=${keyword}` : `${url.hostname}${path || "/"}`;
  } catch {
    return shortText(raw, 76);
  }
}

/** Compact date — month/day for the current year, otherwise yyyy-mm-dd. */
function formatDate(value) {
  if (!value) return dash();
  const raw = String(value);
  const date = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return raw.slice(0, 10);
  const now = new Date();
  const sameYear = date.getFullYear() === now.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return sameYear ? `${m}-${d} ${hh}:${mm}` : `${date.getFullYear()}-${m}-${d}`;
}

/** Compact follower count: 1.2K / 12.3K / 1.4M. */
function formatFollowers(n) {
  const value = Number(n || 0);
  if (!value) return "0";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 100_000 ? 0 : 1)}K`;
  return String(value);
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

function showInstallExtensionGuide() {
  // Prevent duplicate overlays if user double-clicks.
  const existing = document.getElementById("ext-install-modal");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "ext-install-modal";
  overlay.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;" +
    "display:flex;align-items:center;justify-content:center;padding:20px;";

  const card = document.createElement("div");
  card.style.cssText =
    "background:#1c1f24;color:#e6e6e6;border:1px solid #333;border-radius:8px;" +
    "max-width:560px;width:100%;padding:20px 22px;line-height:1.6;" +
    "box-shadow:0 8px 32px rgba(0,0,0,0.6);font-size:14px;";

  const title = document.createElement("h3");
  title.textContent = t("extInstall.title");
  title.style.cssText = "margin:0 0 12px;font-size:16px;";

  const intro = document.createElement("p");
  intro.textContent = t("extInstall.intro");
  intro.style.cssText = "margin:0 0 12px;color:#bbb;";

  const steps = document.createElement("div");
  steps.style.cssText = "margin:0 0 16px;";
  ["step1", "step2", "step3", "step4"].forEach((k) => {
    const p = document.createElement("p");
    p.textContent = t(`extInstall.${k}`);
    p.style.cssText = "margin:6px 0;";
    steps.appendChild(p);
  });

  const btnRow = document.createElement("div");
  btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:8px;";

  const openBtn = document.createElement("button");
  openBtn.className = "ghost";
  openBtn.textContent = t("extInstall.openChrome");
  openBtn.addEventListener("click", () => {
    // Chrome blocks JS from opening chrome://* directly; fall back to clipboard.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText("chrome://extensions").catch(() => {});
    }
    toast("chrome://extensions");
  });

  const closeBtn = document.createElement("button");
  closeBtn.className = "primary";
  closeBtn.textContent = t("extInstall.close");
  closeBtn.addEventListener("click", () => overlay.remove());

  btnRow.appendChild(openBtn);
  btnRow.appendChild(closeBtn);
  card.appendChild(title);
  card.appendChild(intro);
  card.appendChild(steps);
  card.appendChild(btnRow);
  overlay.appendChild(card);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

function dot(status) {
  const cls = status === "good" ? "good" : status === "warn" ? "warn" : "bad";
  return `<span class="status-dot ${cls}"></span>`;
}

function pill(text, kind) {
  return `<span class="pill ${kind || ""}">${escapeHtml(text || dash())}</span>`;
}

function safeHref(value, { httpOnly = false } = {}) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const allowed = httpOnly ? /^https?:\/\//i : /^(https?:\/\/|mailto:|tel:)/i;
  return allowed.test(raw) ? escapeHtml(raw) : "";
}

function shortText(value, max = 58) {
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  return raw.length > max ? `${raw.slice(0, max - 1)}...` : raw;
}

function contactLabel(method) {
  const key = `contact.${method?.type || ""}`;
  return I18N[currentLanguage]?.[key] || I18N.en[key] || method?.label || method?.type || "Contact";
}

function renderCreatorCell(c) {
  const profileHref = safeHref(c.profile_url, { httpOnly: true });
  const profileLink = profileHref
    ? `<br /><a class="profile-link" href="${profileHref}" target="_blank" rel="noreferrer">${escapeHtml(t("recommendations.profileLink"))}</a>`
    : "";
  return `<strong>@${escapeHtml(c.handle)}</strong><br /><span class="subtle">${escapeHtml(c.display_name || "")}</span>${profileLink}`;
}

function renderAssignmentCell(c) {
  const store = shortText(c.store_assigned || "", 34);
  const owner = shortText(c.owner_bd || "", 34);
  if (!store && !owner) return `<span class="subtle">${dash()}</span>`;
  return `<div class="assignment-list">
    <div><span class="assignment-label">${escapeHtml(t("assignment.store"))}</span><span>${escapeHtml(store || dash())}</span></div>
    <div><span class="assignment-label">${escapeHtml(t("assignment.owner"))}</span><span>${escapeHtml(owner || dash())}</span></div>
  </div>`;
}

function operatorName() {
  return String(currentUser?.email || currentUser?.username || currentUser?.identity || currentOperatorName || "").trim();
}

function ensureOperatorName() {
  const current = operatorName();
  if (!current) toast(t("outreach.gmailNotReady"));
  return current;
}

function sameOwner(a, b) {
  return String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
}

function renderActionCell(c) {
  const id = escapeHtml(c.id);
  const owner = String(c.owner_bd || "").trim();
  const mine = owner && sameOwner(owner, operatorName());
  if (!owner) {
    return `<button class="row-action" data-claim="${id}">${t("assignment.claim")}</button>`;
  }
  if (mine) {
    return `<button class="row-action" data-release="${id}">${t("assignment.release")}</button>
      <button class="row-action primary" data-outreach="${id}">${t("outreach.button")}</button>`;
  }
  return `<button class="row-action" disabled title="${escapeHtml(owner)}">${t("assignment.taken")}</button>`;
}

function renderContactMethods(c) {
  const methods = Array.isArray(c.contact_methods) ? c.contact_methods : [];
  if (!methods.length) return `<span class="subtle">${dash()}</span>`;
  return `<div class="contact-list">${methods.slice(0, 5).map((method) => {
    const label = escapeHtml(contactLabel(method));
    const value = escapeHtml(shortText(method.value || ""));
    const href = safeHref(method.href);
    const body = `<span class="contact-kind">${label}</span>${value ? `<span class="contact-value">${value}</span>` : ""}`;
    if (href) {
      return `<a class="contact-chip" href="${href}" target="_blank" rel="noreferrer">${body}</a>`;
    }
    return `<span class="contact-chip">${body}</span>`;
  }).join("")}</div>`;
}

function recommendationCardInitial(c) {
  const seed = String(c.display_name || c.handle || "?").replace(/^@+/, "").trim();
  return escapeHtml((seed.charAt(0) || "?").toUpperCase());
}

function recommendationCardPriority(c) {
  const priority = c.outreach_priority || dash();
  const cls = priority ? `priority-${String(priority).toLowerCase()}` : "";
  return pill(priority, cls);
}

function renderRecommendationCard(c) {
  const profileHref = safeHref(c.profile_url, { httpOnly: true });
  const profileLink = profileHref
    ? `<a class="profile-link" href="${profileHref}" target="_blank" rel="noreferrer">${escapeHtml(t("recommendations.profileLink"))}</a>`
    : "";
  const reason = c.recommendation_reason || "";
  const bio = c.bio || "";
  const fitScore = c.primary_product_fit_score ? `(${c.primary_product_fit_score})` : "";
  return `
    <article class="rec-card" role="listitem">
      <div class="rec-card-head">
        <div class="rec-avatar">${recommendationCardInitial(c)}</div>
        <div class="rec-handle-block">
          <div class="rec-handle">@${escapeHtml(c.handle || c.id || dash())}</div>
          <div class="rec-display-name">${escapeHtml(c.display_name || "")}</div>
          ${profileLink}
        </div>
        ${recommendationCardPriority(c)}
      </div>

      <div class="rec-hero">
        <span class="rec-hero-value">${formatFollowers(c.followers_count)}</span>
        <span class="rec-hero-label">${escapeHtml(t("table.followers"))}</span>
      </div>

      <div class="rec-score-grid">
        <div class="rec-score-cell">
          <span class="rec-score-label">${escapeHtml(t("table.scoreShort"))}</span>
          <span class="rec-score-value">${escapeHtml(c.recommendation_score ?? 0)}</span>
          <span class="rec-score-sub">${escapeHtml(codeLabel("queue", c.queue_type))}</span>
        </div>
        <div class="rec-score-cell">
          <span class="rec-score-label">${escapeHtml(t("table.fit"))}</span>
          <span class="rec-score-value">${escapeHtml(c.fit_level || dash())}</span>
          <span class="rec-score-sub">${escapeHtml(fitScore)}</span>
        </div>
      </div>

      <div class="rec-tag-row">
        <span class="rec-status" data-creator-status="${escapeHtml(String(c.id || ""))}">${escapeHtml(codeLabel("current_status", c.current_status))}</span>
        ${pill(codeLabel("product", c.recommended_product_type), "queue")}
        ${pill(codeLabel("collab", c.recommended_collab_type), "queue")}
      </div>

      <div class="rec-reason reason-cell" data-full="${escapeHtml(reason)}">${escapeHtml(reason || dash())}</div>
      <div class="rec-reason bio-cell" data-full="${escapeHtml(bio)}">${escapeHtml(shortText(bio || dash(), 130))}</div>
      <div class="rec-contact-row">${renderContactMethods(c)}</div>

      <div class="rec-card-foot">
        <div>
          ${renderAssignmentCell(c)}
          <div class="rec-meta">
            <span>${escapeHtml(formatDate(c.collected_at || c.created_at || c.last_seen_at))}</span>
            <span>${escapeHtml(c.search_keyword || "")}</span>
          </div>
        </div>
        <div class="rec-card-foot-actions">${renderActionCell(c)}</div>
      </div>
    </article>`;
}

function renderOutreachCreatorStat(label, value, title) {
  const text = value === null || value === undefined || value === "" ? dash() : String(value);
  return `<div class="outreach-creator-stat">
    <span class="outreach-creator-stat-label">${escapeHtml(label)}</span>
    <span class="outreach-creator-stat-value" title="${escapeHtml(title || text)}">${escapeHtml(text)}</span>
  </div>`;
}

function renderOutreachCreatorSummary(c) {
  const profileHref = safeHref(c.profile_url, { httpOnly: true });
  const profileLink = profileHref
    ? `<a class="profile-link" href="${profileHref}" target="_blank" rel="noreferrer">${escapeHtml(t("recommendations.profileLink"))}</a>`
    : "";
  const productCollab = [
    codeLabel("product", c.recommended_product_type),
    codeLabel("collab", c.recommended_collab_type),
  ].filter((value) => value && value !== dash()).join(" / ") || dash();
  const fitValue = [
    c.fit_level || "",
    c.primary_product_fit_score ? `(${c.primary_product_fit_score})` : "",
  ].filter(Boolean).join(" ") || dash();
  const followerCount = Number(c.followers_count || 0);
  const exactFollowers = followerCount
    ? followerCount.toLocaleString(currentLanguage === "zh" ? "zh-CN" : "en-US")
    : dash();
  const collectedAt = formatDate(c.collected_at || c.created_at || c.last_seen_at);
  const subMeta = [
    profileLink,
    c.search_keyword ? `<span>${escapeHtml(t("filters.keyword"))}: ${escapeHtml(c.search_keyword)}</span>` : "",
    collectedAt && collectedAt !== dash()
      ? `<span>${escapeHtml(t("table.collectedAt"))}: ${escapeHtml(collectedAt)}</span>`
      : "",
  ].filter(Boolean).join("");
  const bio = shortText(c.bio || dash(), 180);
  const reason = shortText(c.recommendation_reason || dash(), 220);

  return `
    <section class="outreach-creator-panel" aria-label="${escapeHtml(t("table.creatorInfo"))}">
      <div class="outreach-creator-main">
        <div class="outreach-creator-avatar">${recommendationCardInitial(c)}</div>
        <div class="outreach-creator-identity">
          <div class="outreach-creator-handle">@${escapeHtml(c.handle || c.id || dash())}</div>
          <div class="outreach-creator-name">${escapeHtml(c.display_name || dash())}</div>
          <div class="outreach-creator-submeta">${subMeta}</div>
        </div>
      </div>
      <div class="outreach-creator-stats">
        ${renderOutreachCreatorStat(t("table.followers"), exactFollowers)}
        ${renderOutreachCreatorStat(t("contact.email"), c.email || dash())}
        ${renderOutreachCreatorStat(t("table.productCollab"), productCollab)}
        ${renderOutreachCreatorStat(t("table.priority"), c.outreach_priority || dash())}
        ${renderOutreachCreatorStat(t("table.fit"), fitValue)}
        ${renderOutreachCreatorStat(t("table.score"), c.recommendation_score ?? dash())}
        ${renderOutreachCreatorStat(t("table.status"), codeLabel("current_status", c.current_status))}
        ${renderOutreachCreatorStat(t("assignment.owner"), c.owner_bd || dash())}
      </div>
      <div class="outreach-creator-notes">
        <div class="outreach-creator-note">
          <span>${escapeHtml(t("table.profileBio"))}</span>
          <p title="${escapeHtml(c.bio || "")}">${escapeHtml(bio)}</p>
        </div>
        <div class="outreach-creator-note">
          <span>${escapeHtml(t("table.reason"))}</span>
          <p title="${escapeHtml(c.recommendation_reason || "")}">${escapeHtml(reason)}</p>
        </div>
        <div class="outreach-creator-note outreach-creator-contact">
          <span>${escapeHtml(t("table.contact"))}</span>
          ${renderContactMethods(c)}
        </div>
      </div>
    </section>`;
}

function loginLabel(status) {
  if (status === "logged_in") return t("state.loggedIn");
  if (status === "logged_out" || status === "not_logged_in") return t("state.loggedOut");
  if (status === "unknown") return t("state.unknown");
  return status || t("state.unknown");
}

// Helper: only update the element if the new value differs. Prevents
// React-like reflows and stops the eye-catching "blink" that happens when
// you reassign identical innerHTML every 5 seconds.
function setIfChanged(el, html, isText) {
  if (!el) return;
  if (isText) {
    if (el.textContent !== html) el.textContent = html;
  } else {
    if (el.innerHTML !== html) el.innerHTML = html;
  }
}

// Renders the structural "shell" of the extension session card. Time-varying
// fields (heartbeat label, login text, current page, current URL) are left as
// empty placeholders identified by data-field hooks, to be filled by
// patchExtensionSessionValues without touching the surrounding DOM (preserves
// the .status-dot.good ring-pulse CSS animation).
function renderExtensionSessionShell(session, ctx) {
  if (!session) {
    return `
      <div class="collector-session-card is-empty" data-field-shell="empty">
        <div class="collector-session-status">
          ${dot("bad")}
          <div class="collector-session-title">
            <strong>${escapeHtml(t("collection.notConnected"))}</strong>
            <span>${escapeHtml(t("dashboard.extensionHelp"))}</span>
          </div>
        </div>
      </div>
    `;
  }

  const { online, loginKind, workerId, chips } = ctx;

  return `
    <div class="collector-session-card ${online ? "is-online" : "is-offline"}" data-field-shell="filled">
      <div class="collector-session-main">
        <div class="collector-session-status">
          ${dot(online ? "good" : "warn")}
          <div class="collector-session-title">
            <strong>${escapeHtml(t(online ? "collection.onlineWorker" : "collection.offlineWorker"))}</strong>
            <span class="collector-worker" title="${escapeHtml(workerId)}">${escapeHtml(compactWorkerId(workerId))}</span>
          </div>
        </div>
        ${chips.length ? `<div class="collector-session-meta">${chips.map((item) => `<span class="collector-chip">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="collector-session-grid">
        <div class="collector-session-item">
          <span>${escapeHtml(t("collection.tiktokLogin"))}</span>
          <strong class="collector-status-line">${dot(loginKind)}<span data-field="login-text"></span></strong>
        </div>
        <div class="collector-session-item">
          <span>${escapeHtml(t("collection.currentPage"))}</span>
          <strong data-field="page" title=""></strong>
        </div>
        <div class="collector-session-item">
          <span>${escapeHtml(t("collection.lastHeartbeat"))}</span>
          <strong data-field="heartbeat"></strong>
        </div>
        <div class="collector-session-item">
          <span>${escapeHtml(t("collection.currentUrl"))}</span>
          <strong class="collector-url" data-field="url" title=""></strong>
        </div>
      </div>
    </div>
  `;
}

function patchExtensionSessionValues(root, session) {
  if (!root || !session) return;

  const hb = root.querySelector('[data-field="heartbeat"]');
  if (hb) {
    const text = heartbeatLabel(session.last_heartbeat_at);
    if (hb.textContent !== text) hb.textContent = text;
  }

  const loginEl = root.querySelector('[data-field="login-text"]');
  if (loginEl) {
    const text = loginLabel(session.tiktok_login_status);
    if (loginEl.textContent !== text) loginEl.textContent = text;
  }

  const pageEl = root.querySelector('[data-field="page"]');
  if (pageEl) {
    const pageParts = [pageTypeLabel(session.page_type), pageStatusLabel(session.tiktok_page_status)]
      .filter((item) => item && item !== dash());
    const pageText = pageParts.join(" · ") || dash();
    const rawPageText = [session.page_type, session.tiktok_page_status].filter(Boolean).join(" · ");
    if (pageEl.textContent !== pageText) pageEl.textContent = pageText;
    if (pageEl.getAttribute("title") !== rawPageText) pageEl.setAttribute("title", rawPageText);
  }

  const urlEl = root.querySelector('[data-field="url"]');
  if (urlEl) {
    const fullUrl = session.current_url || "";
    const display = formatUrlForPanel(fullUrl);
    if (urlEl.textContent !== display) urlEl.textContent = display;
    if (urlEl.getAttribute("title") !== fullUrl) urlEl.setAttribute("title", fullUrl);
  }
}

// Entry point: rebuild the shell only when shape changes; otherwise just patch
// time-varying values in place. Keeps .status-dot.good alive across polls so
// the CSS ring-pulse animation runs uninterrupted.
function renderExtensionSessionPanelInto(container, session) {
  if (!container) return;

  let ctx = null;
  let shapeKey;
  if (!session) {
    shapeKey = JSON.stringify(["empty", "", false, "bad", "", "", currentLanguage]);
  } else {
    const online = Boolean(session.online);
    const loginText = loginLabel(session.tiktok_login_status);
    const loginKind = loginText === t("state.loggedIn") ? "good" : loginText === t("state.unknown") ? "warn" : "bad";
    const workerId = session.worker_id || dash();
    const chips = [
      session.extension_version ? `${t("collection.version")} ${session.extension_version}` : "",
      session.department_code || "",
    ].filter(Boolean);
    ctx = { online, loginKind, workerId, chips };
    shapeKey = JSON.stringify([
      "filled",
      session.worker_id || "",
      online,
      loginKind,
      session.extension_version || "",
      session.department_code || "",
      currentLanguage,
    ]);
  }

  if (container.dataset.shapeKey !== shapeKey) {
    container.innerHTML = renderExtensionSessionShell(session, ctx || {
      online: false, loginKind: "bad", workerId: dash(), chips: [],
    });
    container.dataset.shapeKey = shapeKey;
  }

  if (session) patchExtensionSessionValues(container, session);
}

function formatCount(value) {
  return Number(value || 0).toLocaleString(currentLanguage === "zh" ? "zh-CN" : "en-US");
}

function formatGrowth(value) {
  if (value === null || value === undefined || value === "") return dash();
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function countRows(items, labelFn = (value) => value, limit = 8) {
  const rows = (items || []).filter((row) => Number(row.count || row.n || 0) > 0).slice(0, limit);
  return rows.map((row) => `
    <tr>
      <td>${escapeHtml(labelFn(row.name ?? row.cat ?? dash()))}</td>
      <td>${formatCount(row.count ?? row.n)}</td>
    </tr>
  `).join("") || `<tr><td colspan="2" class="subtle">${dash()}</td></tr>`;
}

function metricRows(items, nameKey = "name", countKey = "count") {
  const rows = items || [];
  const max = Math.max(1, ...rows.map((row) => Number(row[countKey] || 0)));
  return rows.map((row) => {
    const count = Number(row[countKey] || 0);
    const width = Math.max(3, Math.round(count / max * 100));
    return `
      <div class="metric-row">
        <span class="metric-name" title="${escapeHtml(row[nameKey] || dash())}">${escapeHtml(row[nameKey] || dash())}</span>
        <span class="metric-track"><span class="metric-fill" style="width:${width}%"></span></span>
        <span class="metric-value">${formatCount(count)}</span>
      </div>
    `;
  }).join("") || `<p class="subtle">${dash()}</p>`;
}

async function renderBusiness() {
  setMain("tpl-business");
  try {
    const data = await api("/admin/business-dashboard");
    const summary = data.summary || {};
    const scope = data.scope || {};
    $("#business-scope").textContent = scope.name ? `${scope.name} · 按部门数据分配` : "当前部门 · 按部门数据分配";
    $("#business-cards").innerHTML = [
      ["达人线索", summary.creator_count],
      ["推荐线索", summary.recommended],
      ["可联系", summary.contactable],
      ["待联系", summary.pending_contact],
      ["已推进", summary.contacted],
      ["待回复", summary.pending_reply],
      ["近 7 天新增", summary.recent_collections_7d],
      ["未分配推荐", summary.unassigned_recommended],
    ].map(([label, value]) => `<div class="card"><h3>${escapeHtml(label)}</h3><p>${formatCount(value)}</p></div>`).join("");
    $("#business-status").innerHTML = countRows(data.business_status);
    $("#business-products").innerHTML = countRows(data.products);
    $("#business-priorities").innerHTML = countRows(data.priorities);
    $("#business-owners").innerHTML = (data.owners || []).map((row) => `
      <tr>
        <td>${escapeHtml(row.owner || dash())}</td>
        <td>${formatCount(row.recommended)}</td>
        <td>${formatCount(row.pending_contact)}</td>
        <td>${formatCount((row.contacted || 0) + (row.pending_reply || 0) + (row.sample_sent || 0) + (row.video_published || 0))}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="subtle">${dash()}</td></tr>`;
  } catch (e) {
    $("#business-cards").innerHTML = `<div class="card"><h3>加载失败</h3><p>${escapeHtml(e.message)}</p></div>`;
  }
}

async function loadHotKw() {
  if (currentPage !== "hotkw") return;
  try {
    const data = await api("/shared/keywords/dashboard");
    const totals = data.totals || {};
    const lastRun = data.last_run || {};
    $("#hotkw-status").textContent = `共享模块 · 两个部门可见 · 已更新 ${new Date().toLocaleString("zh-CN", { hour12: false })}`;
    $("#hotkw-cards").innerHTML = [
      ["有效关键词", totals.active],
      ["近 60 分钟新鲜", totals.fresh],
      ["待分类", totals.uncategorized],
      ["最近状态", lastRun.status || data.warning || "-"],
    ].map(([label, value]) => `<div class="card"><h3>${escapeHtml(label)}</h3><p>${escapeHtml(formatCountOrText(value))}</p></div>`).join("");
    $("#hotkw-categories").innerHTML = metricRows((data.by_category || []).map((row) => ({ name: row.cat, count: row.n })));
    $("#hotkw-rising").innerHTML = hotKwTableRows(data.rising_top);
    $("#hotkw-volume").innerHTML = hotKwTableRows(data.volume_top);
    $("#hotkw-runs").innerHTML = (data.recent_runs || []).map((row) => `
      <tr>
        <td>${escapeHtml(formatTime(row.started_at))}</td>
        <td>${escapeHtml(row.source || dash())}</td>
        <td>${escapeHtml(row.status || dash())}</td>
        <td>${formatCount(row.n_added)} / ${formatCount(row.n_updated)} / ${formatCount(row.n_errors)}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="subtle">${dash()}</td></tr>`;
  } catch (e) {
    $("#hotkw-status").textContent = `加载失败：${e.message}`;
  }
}

function formatCountOrText(value) {
  const n = Number(value);
  return Number.isFinite(n) && value !== "" && value !== null ? formatCount(n) : (value || dash());
}

function hotKwTableRows(items) {
  return (items || []).map((row) => `
    <tr>
      <td>${escapeHtml(row.keyword || dash())}</td>
      <td>${escapeHtml(row.category_hint || "(待分类)")}</td>
      <td>${formatCount(row.search_volume)}</td>
      <td>${escapeHtml(formatGrowth(row.growth_rate))}</td>
    </tr>
  `).join("") || `<tr><td colspan="4" class="subtle">${dash()}</td></tr>`;
}

async function renderHotKw() {
  setMain("tpl-hotkw");
  await loadHotKw();
  clearInterval(hotKwTimer);
  hotKwTimer = setInterval(loadHotKw, 30000);
}

async function renderAssistant() {
  setMain("tpl-assistant");
  const status = $("#assistant-status");
  const input = $("#assistant-input");
  const send = $("#assistant-send");
  renderAssistantMessages();
  try {
    const info = await api("/shared/assistant/info");
    status.textContent = info.ready
      ? `就绪 · ${info.model || "默认模型"} · ${info.department_name || "当前部门"}`
      : "未配置 OPENAI_API_KEY，请联系超级管理员。";
    send.disabled = !info.ready;
  } catch (e) {
    status.textContent = `加载失败：${e.message}`;
    send.disabled = true;
  }
  send.addEventListener("click", sendAssistantMessage);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendAssistantMessage();
  });
}

function renderAssistantMessages() {
  const box = $("#assistant-messages");
  if (!box) return;
  if (!assistantHistory.length) {
    box.innerHTML = `<div class="assistant-msg assistant">你好，我可以帮你看业务看板、热搜机会、达人线索和建联下一步。</div>`;
    return;
  }
  box.innerHTML = assistantHistory.map((msg) => `
    <div class="assistant-msg ${msg.role === "user" ? "user" : "assistant"}">${
      msg.role === "user" ? escapeHtml(msg.content) : renderMarkdown(msg.content)
    }</div>
  `).join("");
  box.scrollTop = box.scrollHeight;
}

async function sendAssistantMessage() {
  const input = $("#assistant-input");
  const send = $("#assistant-send");
  const text = input.value.trim();
  if (!text || send.disabled) return;
  input.value = "";
  assistantHistory.push({ role: "user", content: text });
  assistantHistory.push({ role: "assistant", content: "思考中..." });
  renderAssistantMessages();
  send.disabled = true;
  try {
    const reply = await api("/shared/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: assistantHistory.slice(0, -1) }),
    });
    assistantHistory[assistantHistory.length - 1] = { role: "assistant", content: reply.message || "-" };
  } catch (e) {
    assistantHistory[assistantHistory.length - 1] = { role: "assistant", content: `出错了：${e.message}` };
  } finally {
    send.disabled = false;
    renderAssistantMessages();
  }
}

async function renderDashboard() {
  // Mount the template only when the dashboard view isn't already in the DOM.
  // The auto-refresh interval calls renderDashboard() too — without this
  // guard, every tick would re-clone the template and flash the whole panel.
  if (!document.getElementById("card-backend")) {
    setMain("tpl-dashboard");
  }
  await refreshDashboardData();
}

async function refreshDashboardData() {
  // If the user navigated away mid-tick, abort so we don't write into
  // the wrong page's DOM (the IDs may not exist or may belong to another view).
  if (currentPage !== "dashboard") return;
  if (!document.getElementById("card-backend")) return;

  try {
    const a = await api("/app/status");
    setIfChanged($("#versions"), t("dashboard.versionText", {
      system: a.system_version || "1.0",
      score: a.score_version,
      tag: a.tag_version,
      rec: a.rec_version,
    }), true);
  } catch {}

  let backendOk = false;
  try {
    const r = await fetch("/health");
    backendOk = r.ok;
  } catch {}
  setIfChanged($("#card-backend"),
    backendOk ? `${dot("good")}${t("state.running")}` : `${dot("bad")}${t("state.stopped")}`);

  try {
    const stats = await api("/db/stats");
    setIfChanged($("#card-db"), `${dot("good")}${t("state.connected")}`);
    setIfChanged($("#card-count-creators"), String(stats.today_creators ?? stats.creators_today ?? stats.creators), true);
    setIfChanged($("#card-count-obs"), String(stats.today_raw_observations ?? stats.raw_observations_today ?? stats.raw_observations), true);
    setIfChanged($("#card-count-review"), String(stats.review_tasks), true);

    const recs = await api("/creators/recommended?limit=1000");
    setIfChanged($("#card-count-rec"), String(recs.total || 0), true);
    const holds = await api("/creators?queue_type=low_confidence_hold&limit=1");
    setIfChanged($("#card-count-review"), String(holds.total || 0), true);
  } catch (e) {
    setIfChanged($("#card-db"), `${dot("bad")}${t("state.error")}`);
  }

  try {
    const e = await api("/extension/status");
    if (e.any_online) {
      setIfChanged($("#card-ext"), `${dot("good")}${t("state.online")}`);
      const top = e.sessions.find((s) => s.online) || e.sessions[0];
      const tt = loginLabel(top.tiktok_login_status);
      setIfChanged($("#card-tt"), `${dot(tt === t("state.loggedIn") ? "good" : "warn")}${tt}`);
      setIfChanged($("#ext-detail"), JSON.stringify(top, null, 2), true);
    } else if (e.sessions.length) {
      setIfChanged($("#card-ext"), `${dot("warn")}${t("state.offlineLastSeen")}`);
      setIfChanged($("#card-tt"), `${dot("bad")}${dash()}`);
      setIfChanged($("#ext-detail"), JSON.stringify(e.sessions[0], null, 2), true);
    } else {
      setIfChanged($("#card-ext"), `${dot("bad")}${t("state.notConnected")}`);
      setIfChanged($("#card-tt"), `${dot("bad")}${dash()}`);
      setIfChanged($("#ext-detail"), t("dashboard.extensionHelp"), true);
    }
  } catch {
    setIfChanged($("#card-ext"), `${dot("bad")}${t("state.error")}`);
  }
}

async function renderCollection() {
  setMain("tpl-collection");

  // Sticky session cache: hold the last known session for a few polls before
  // declaring the extension truly disconnected. Avoids the "一会无一会有"
  // flicker caused by intermittent empty responses or transient API errors.
  let lastGoodSession = null;
  let emptyStreak = 0;
  const EMPTY_TOLERANCE = 3; // ~4.5s of consecutive empties before clearing

  const drawProgress = async () => {
    let progress = null;
    let displaySession = null;
    let workerId = null;
    try {
      const ext = await api("/extension/status");
      const latestSession = ext.sessions?.find?.((s) => s.online) || ext.sessions?.[0] || null;
      if (latestSession) {
        lastGoodSession = latestSession;
        emptyStreak = 0;
        displaySession = latestSession;
      } else {
        emptyStreak += 1;
        if (emptyStreak < EMPTY_TOLERANCE && lastGoodSession) {
          displaySession = lastGoodSession; // sticky hold
        } else {
          lastGoodSession = null;
          displaySession = null;
        }
      }
      renderExtensionSessionPanelInto($("#collector-session-panel"), displaySession);
    } catch (err) {
      console.warn("[collection] /extension/status failed; preserving last panel view", err);
      // Do not overwrite the panel on transient API errors.
      displaySession = lastGoodSession;
    }
    workerId = displaySession?.worker_id || lastGoodSession?.worker_id || null;

    try {
      const rp = await api("/extension/run-progress" + (workerId ? `?worker_id=${encodeURIComponent(workerId)}` : ""));
      progress = workerId ? rp.progress : (rp.progress || rp.items?.[0] || null);
    } catch {}

    const cards = $("#run-progress-cards");
    if (!progress || !progress.running) {
      setIfChanged(cards, `<div class="card"><h3>${t("collection.autoRun")}</h3><p class="subtle">${t("collection.noProgress")}</p></div>`);
      return;
    }
    const target = (progress.profiles_visited || 0) + (progress.profiles_remaining || 0);
    const pct = target > 0 ? Math.round((progress.profiles_visited / target) * 100) : 0;
    const step = (progress.step || "idle").replace(/_/g, " ");
    const runningText = progress.running ? t("collection.running") : (progress.finished_at ? t("collection.finished") : t("collection.idle"));
    setIfChanged(cards, `
      <div class="card"><h3>${t("collection.step")}</h3><p>${escapeHtml(step)}</p>
        <p class="subtle" style="font-size:12px">${escapeHtml((progress.current_action || "").slice(0, 120))}</p></div>
      <div class="card"><h3>${t("collection.profiles")}</h3><p>${progress.profiles_visited} / ${target}</p>
        <p class="subtle" style="font-size:12px">${pct}% · ${escapeHtml(t("collection.keywordInline", { keyword: progress.keyword || dash() }))}</p></div>
      <div class="card"><h3>${t("collection.leads")}</h3><p>${progress.leads_saved}</p>
        <p class="subtle" style="font-size:12px">${escapeHtml(t("collection.skippedQueue", { skipped: progress.skipped, queue: progress.queue_size }))}</p></div>
      <div class="card"><h3>${t("collection.pace")}</h3><p>${escapeHtml(t("collection.paceText", { scrolls: progress.scrolls_done, rests: progress.rest_breaks }))}</p>
        <p class="subtle" style="font-size:12px">${runningText} · ${progress.elapsed_seconds || 0}s</p></div>
    `);
  };

  await drawProgress();

  if (window._x9_collection_timer) clearInterval(window._x9_collection_timer);
  window._x9_collection_timer = setInterval(() => {
    if (currentPage === "collection") drawProgress();
    else clearInterval(window._x9_collection_timer);
  }, 1500);
}

function setIfValue(params, key, value) {
  const trimmed = String(value ?? "").trim();
  if (trimmed) params.set(key, trimmed);
}

/** Parse a single number with optional K/M/B suffix.
 *  "1.2K" → 1200, "5M" → 5000000, "12,000" → 12000.
 *  Returns null if the string can't be parsed cleanly. */
function parseFollowerNumber(raw) {
  const s = String(raw || "").trim().toLowerCase().replaceAll(",", "");
  if (!s) return null;
  const m = s.match(/^([\d.]+)\s*([kmb])?$/);
  if (!m) return null;
  const n = parseFloat(m[1]);
  if (Number.isNaN(n)) return null;
  const mult = { k: 1000, m: 1_000_000, b: 1_000_000_000 }[m[2] || ""] || 1;
  return Math.round(n * mult);
}

/** Parse a follower-count filter expression.
 *
 * Supported forms:
 *   "1K"          → min=1000             (bare number = lower bound)
 *   "≥1K" / ">=1K" / ">1K" / "1K+"  → min=1000
 *   "≤10K" / "<=10K" / "<10K"        → max=10000
 *   "1K-100K" / "1K~100K" / "1K..100K" → min=1000, max=100000
 *   ""           → {min:null, max:null}  (no filter)
 *
 * Returns ``{min, max, ok}`` — ``ok=false`` if the user typed garbage so
 * the caller can highlight the input. */
function parseFollowersExpr(raw) {
  const s = String(raw || "").trim().replace(/\s+/g, "");
  if (!s) return { min: null, max: null, ok: true };

  // Range — split on -, ~, ..
  const rangeMatch = s.match(/^([^-~.]+)(?:[-~]|\.\.)(.+)$/);
  if (rangeMatch) {
    const lo = parseFollowerNumber(rangeMatch[1]);
    const hi = parseFollowerNumber(rangeMatch[2]);
    if (lo == null || hi == null) return { min: null, max: null, ok: false };
    return { min: Math.min(lo, hi), max: Math.max(lo, hi), ok: true };
  }

  // Lower-bound: ≥ / >= / > / trailing +
  const minPrefix = s.match(/^(?:>=|≥|>)(.+)$/);
  if (minPrefix) {
    const v = parseFollowerNumber(minPrefix[1]);
    return v == null ? { min: null, max: null, ok: false } : { min: v, max: null, ok: true };
  }
  const minSuffix = s.match(/^(.+)\+$/);
  if (minSuffix) {
    const v = parseFollowerNumber(minSuffix[1]);
    return v == null ? { min: null, max: null, ok: false } : { min: v, max: null, ok: true };
  }

  // Upper-bound: ≤ / <= / <
  const maxPrefix = s.match(/^(?:<=|≤|<)(.+)$/);
  if (maxPrefix) {
    const v = parseFollowerNumber(maxPrefix[1]);
    return v == null ? { min: null, max: null, ok: false } : { min: null, max: v, ok: true };
  }

  // Bare number → treat as lower bound
  const v = parseFollowerNumber(s);
  if (v == null) return { min: null, max: null, ok: false };
  return { min: v, max: null, ok: true };
}

async function renderRecommendations() {
  setMain("tpl-recommendations");
  let drawTimer = null;
  let requestSeq = 0;

  const draw = async () => {
    const seq = ++requestSeq;
    const status = $("#rec-filter-status");
    if (status) status.textContent = t("recommendations.filtering");
    const params = new URLSearchParams({ limit: 1000 });
    const timePreset = $("#f-time-preset").value;
    const collectedDate = $("#f-collected-date").value;

    setIfValue(params, "sort_by", $("#f-sort").value || "recommended");
    setIfValue(params, "handle_contains", $("#f-handle").value);
    setIfValue(params, "contact_contains", $("#f-contact").value);
    setIfValue(params, "contact_channel", $("#f-contact-channel").value);
    setIfValue(params, "bio_contains", $("#f-bio").value);

    // Followers expression — single input, parsed into min/max
    const followersInput = $("#f-followers");
    const parsed = parseFollowersExpr(followersInput?.value || "");
    if (followersInput) {
      followersInput.classList.toggle("invalid", !parsed.ok);
    }
    if (!parsed.ok) {
      if ($("#f-min-followers")) $("#f-min-followers").value = "";
      if ($("#f-max-followers")) $("#f-max-followers").value = "";
      if (status) status.textContent = t("filters.followersInvalid");
      return;
    }
    if (parsed.ok) {
      if (parsed.min != null) params.set("min_followers", String(parsed.min));
      if (parsed.max != null) params.set("max_followers", String(parsed.max));
      // Mirror to hidden inputs so the "clear filters" + other code paths
      // continue to work the same way.
      if ($("#f-min-followers")) $("#f-min-followers").value = parsed.min ?? "";
      if ($("#f-max-followers")) $("#f-max-followers").value = parsed.max ?? "";
    } else {
      if ($("#f-min-followers")) $("#f-min-followers").value = "";
      if ($("#f-max-followers")) $("#f-max-followers").value = "";
    }

    setIfValue(params, "outreach_priority", $("#f-priority").value);
    setIfValue(params, "queue_type", $("#f-queue").value);
    setIfValue(params, "recommended_product_type", $("#f-product").value);
    setIfValue(params, "recommended_collab_type", $("#f-collab").value);
    setIfValue(params, "min_score", $("#f-min-score").value);
    setIfValue(params, "min_fit_score", $("#f-min-fit").value);
    setIfValue(params, "current_status", $("#f-status").value);
    setIfValue(params, "reason_contains", $("#f-reason").value);
    setIfValue(params, "owner_bd_contains", $("#f-owner")?.value);

    if (timePreset === "date" && collectedDate) {
      params.set("collected_date", collectedDate);
    } else if (timePreset) {
      params.set("collected_range", timePreset);
    } else if (collectedDate) {
      params.set("collected_date", collectedDate);
    }

    let r;
    try {
      r = await api(`/creators?${params}`);
    } catch (e) {
      if (seq !== requestSeq) return;
      if (status) status.textContent = t("recommendations.filterFailed", { message: e.message });
      const grid = $("#rec-grid");
      const tbody = $("#rec-tbody");
      if (grid) {
        grid.innerHTML = `<div class="rec-empty">${escapeHtml(t("recommendations.filterFailed", { message: e.message }))}</div>`;
      } else if (tbody) {
        tbody.innerHTML = `<tr><td colspan="15" class="subtle">${escapeHtml(t("recommendations.filterFailed", { message: e.message }))}</td></tr>`;
      }
      return;
    }
    if (seq !== requestSeq) return;
    const items = r.items || [];
    window._x9_creators_index = Object.fromEntries(items.map((c) => [c.id, c]));
    const grid = $("#rec-grid");
    const tbody = $("#rec-tbody");
    if (grid) {
      grid.innerHTML = items.map(renderRecommendationCard).join("")
        || `<div class="rec-empty">${escapeHtml(t("recommendations.noMatch"))}</div>`;
    } else if (tbody) {
      tbody.innerHTML = items.map((c) => `
        <tr>
          <td class="creator-cell">${renderCreatorCell(c)}</td>
          <td>${pill(c.outreach_priority || dash(), (c.outreach_priority || "").toLowerCase())}</td>
          <td class="number-cell">${c.recommendation_score}</td>
          <td>${escapeHtml(c.fit_level || "")} ${c.primary_product_fit_score ? `(${c.primary_product_fit_score})` : ""}</td>
          <td class="number-cell">${formatFollowers(c.followers_count)}</td>
          <td>${escapeHtml(codeLabel("current_status", c.current_status))}</td>
          <td class="action-cell">${renderActionCell(c)}</td>
          <td class="contact-cell">${renderContactMethods(c)}</td>
          <td class="reason-cell subtle" data-full="${escapeHtml(c.recommendation_reason || "")}">${escapeHtml((c.recommendation_reason || "").slice(0, 240))}</td>
          <td>${escapeHtml(codeLabel("product", c.recommended_product_type))}</td>
          <td>${escapeHtml(codeLabel("collab", c.recommended_collab_type))}</td>
          <td>${pill(codeLabel("queue", c.queue_type), "queue")}</td>
          <td class="bio-cell" data-full="${escapeHtml(c.bio || "")}">${escapeHtml(c.bio || dash())}</td>
          <td class="time-cell subtle">${formatDate(c.collected_at || c.created_at || c.last_seen_at)}</td>
          <td class="assignment-cell">${renderAssignmentCell(c)}</td>
        </tr>`).join("") || `<tr><td colspan="15" class="subtle">${t("recommendations.noMatch")}</td></tr>`;
    }
    if (status) status.textContent = t("recommendations.resultCount", { count: r.total || 0 });
    bindOutreachButtons();
    bindAssignmentButtons(draw);
    bindBioReasonPopover();
  };

  const scheduleDraw = () => {
    if (drawTimer) clearTimeout(drawTimer);
    drawTimer = setTimeout(draw, 350);
  };

  const filterControls = () => Array.from(document.querySelectorAll("#rec-toolbar input, #rec-toolbar select"));
  const visibleFilterControls = () => filterControls().filter((el) => el.type !== "hidden" && !el.hidden);
  const advancedFilters = $("#rec-advanced-filters");
  const toggleAdvanced = $("#btn-toggle-advanced");
  const syncAdvancedFilters = () => {
    if (!advancedFilters || !toggleAdvanced) return;
    const open = !advancedFilters.hidden;
    toggleAdvanced.textContent = t(open ? "filters.advancedHide" : "filters.advancedToggle");
    toggleAdvanced.setAttribute("aria-expanded", String(open));
  };

  visibleFilterControls().forEach((el) => {
    el.addEventListener("input", scheduleDraw);
    el.addEventListener("change", draw);
  });

  // Time-popover: bind once.
  setupTimePopover(draw);
  if (toggleAdvanced && advancedFilters) {
    toggleAdvanced.addEventListener("click", () => {
      advancedFilters.hidden = !advancedFilters.hidden;
      syncAdvancedFilters();
    });
    syncAdvancedFilters();
  }

  $("#f-sort")?.addEventListener("change", draw);
  $("#btn-apply-rec-filters")?.addEventListener("click", () => {
    if (drawTimer) clearTimeout(drawTimer);
    draw();
  });
  $("#btn-clear-rec-filters")?.addEventListener("click", () => {
    if (drawTimer) clearTimeout(drawTimer);
    filterControls().forEach((el) => {
      el.value = "";
      el.classList.remove("invalid");
    });
    if ($("#f-sort")) $("#f-sort").value = "recommended";
    if ($("#f-time-preset")) $("#f-time-preset").value = "";
    if ($("#f-collected-date")) $("#f-collected-date").value = "";
    if (advancedFilters) advancedFilters.hidden = true;
    syncAdvancedFilters();
    refreshTimeTriggerLabel();
    draw();
  });
  await draw();
}

/* ---------- Custom date popover (calendar + preset chips) ----------- */

const TIME_PRESETS = [
  { value: "",    labelKey: "filters.timeAll" },
  { value: "1d",  labelKey: "filters.lastDay" },
  { value: "7d",  labelKey: "filters.lastWeek" },
  { value: "30d", labelKey: "filters.lastMonth" },
];

let _timePopoverState = {
  open: false,
  monthCursor: null, // a Date pointing at year/month being shown
  onChange: null,
};

function refreshTimeTriggerLabel() {
  const label = $("#f-time-label");
  if (!label) return;
  const preset = $("#f-time-preset")?.value || "";
  const date = $("#f-collected-date")?.value || "";
  if (date) {
    label.textContent = date;
    return;
  }
  const match = TIME_PRESETS.find((p) => p.value === preset);
  label.textContent = match ? t(match.labelKey) : t("filters.timeAll");
}

function setupTimePopover(onChange) {
  _timePopoverState.onChange = onChange;
  refreshTimeTriggerLabel();
  const trigger = $("#f-time-trigger");
  if (!trigger) return;
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (_timePopoverState.open) closeTimePopover();
    else openTimePopover(trigger);
  });
  document.addEventListener("click", (e) => {
    const root = document.getElementById("time-popover-root");
    if (!_timePopoverState.open) return;
    if (root && !root.contains(e.target) && !trigger.contains(e.target)) {
      closeTimePopover();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && _timePopoverState.open) closeTimePopover();
  });
}

function openTimePopover(trigger) {
  _timePopoverState.open = true;
  trigger.setAttribute("aria-expanded", "true");
  // Cursor starts on the picked date or today
  const picked = $("#f-collected-date")?.value;
  _timePopoverState.monthCursor = picked ? new Date(picked + "T00:00:00") : new Date();
  renderTimePopover(trigger);
}

function closeTimePopover() {
  _timePopoverState.open = false;
  const trigger = $("#f-time-trigger");
  if (trigger) trigger.setAttribute("aria-expanded", "false");
  const root = document.getElementById("time-popover-root");
  if (root) root.innerHTML = "";
}

function renderTimePopover(trigger) {
  const root = document.getElementById("time-popover-root");
  if (!root) return;
  const cursor = _timePopoverState.monthCursor;
  const year = cursor.getFullYear();
  const month = cursor.getMonth(); // 0-indexed
  const today = new Date();
  const todayKey = ymd(today);
  const pickedKey = $("#f-collected-date")?.value || "";

  // Build day grid — 6 rows × 7 cols, week starts Monday
  const firstOfMonth = new Date(year, month, 1);
  // 0=Sun..6=Sat → shift so Monday = 0
  let leadingBlanks = (firstOfMonth.getDay() + 6) % 7;
  const startDate = new Date(year, month, 1 - leadingBlanks);
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    cells.push(d);
  }

  const monthTitle = currentLanguage === "zh"
    ? `${year} 年 ${month + 1} 月`
    : `${cursor.toLocaleString("en-US", { month: "long" })} ${year}`;

  const weekdayLabels = currentLanguage === "zh"
    ? ["一", "二", "三", "四", "五", "六", "日"]
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const currentPreset = $("#f-time-preset")?.value || "";
  const usingChip = currentPreset && currentPreset !== "date";

  root.innerHTML = `
    <div class="time-popover" role="dialog" aria-label="选择搜集时间">
      <div class="time-cal-head">
        <button class="cal-nav" data-nav="prev" type="button">‹</button>
        <span class="cal-title">${escapeHtml(monthTitle)}</span>
        <button class="cal-nav" data-nav="next" type="button">›</button>
      </div>
      <div class="time-cal-weekdays">
        ${weekdayLabels.map((w) => `<span>${w}</span>`).join("")}
      </div>
      <div class="time-cal-days">
        ${cells.map((d) => {
          const key = ymd(d);
          const inMonth = d.getMonth() === month;
          const classes = ["cal-day"];
          if (!inMonth) classes.push("muted");
          if (key === todayKey) classes.push("today");
          if (key === pickedKey) classes.push("selected");
          return `<button class="${classes.join(" ")}" type="button" data-date="${key}">${d.getDate()}</button>`;
        }).join("")}
      </div>
      <div class="time-cal-presets">
        ${TIME_PRESETS.map((p) => `
          <button class="time-chip ${usingChip && p.value === currentPreset ? "active" : ""}${!usingChip && !pickedKey && p.value === "" ? " active" : ""}"
                  type="button" data-preset="${p.value}">${escapeHtml(t(p.labelKey))}</button>
        `).join("")}
      </div>
      <div class="time-cal-foot">
        <button type="button" data-action="clear">${currentLanguage === "zh" ? "清除" : "Clear"}</button>
        <button type="button" data-action="today">${currentLanguage === "zh" ? "今天" : "Today"}</button>
      </div>
    </div>
  `;

  // Position the popover under the trigger
  const pop = root.querySelector(".time-popover");
  const rect = trigger.getBoundingClientRect();
  const popWidth = 240;
  let left = rect.left;
  // keep within viewport
  if (left + popWidth + 12 > window.innerWidth) {
    left = Math.max(8, window.innerWidth - popWidth - 12);
  }
  pop.style.top = `${rect.bottom + 4}px`;
  pop.style.left = `${left}px`;

  // Wire interactions
  pop.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cur = _timePopoverState.monthCursor;
      const delta = btn.dataset.nav === "prev" ? -1 : 1;
      _timePopoverState.monthCursor = new Date(cur.getFullYear(), cur.getMonth() + delta, 1);
      renderTimePopover(trigger);
    });
  });
  pop.querySelectorAll("[data-date]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#f-collected-date").value = btn.dataset.date;
      $("#f-time-preset").value = "date";
      refreshTimeTriggerLabel();
      closeTimePopover();
      _timePopoverState.onChange?.();
    });
  });
  pop.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.preset || "";
      $("#f-time-preset").value = preset;
      $("#f-collected-date").value = "";
      refreshTimeTriggerLabel();
      closeTimePopover();
      _timePopoverState.onChange?.();
    });
  });
  pop.querySelector("[data-action='clear']").addEventListener("click", () => {
    $("#f-time-preset").value = "";
    $("#f-collected-date").value = "";
    refreshTimeTriggerLabel();
    closeTimePopover();
    _timePopoverState.onChange?.();
  });
  pop.querySelector("[data-action='today']").addEventListener("click", () => {
    const today = new Date();
    $("#f-collected-date").value = ymd(today);
    $("#f-time-preset").value = "date";
    refreshTimeTriggerLabel();
    closeTimePopover();
    _timePopoverState.onChange?.();
  });
}

function ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function renderReview() {
  setMain("tpl-review");
  const r = await api("/review-tasks?status=pending&limit=200");
  const rows = await Promise.all(r.items.map(async (task) => {
    let creator = null;
    try { creator = await api(`/creators/${task.creator_id}`); } catch {}
    const handle = creator?.handle || task.creator_id;
    return `
      <tr data-task="${escapeHtml(task.id)}">
        <td><strong>@${escapeHtml(handle)}</strong></td>
        <td class="subtle">${escapeHtml(task.reason || "")}</td>
        <td>${(task.risk_tags || []).map((x) => pill(x, "risk")).join("")}</td>
        <td>
          <button class="row-action good" data-action="approved">${t("review.approve")}</button>
          <button class="row-action bad"  data-action="rejected">${t("review.reject")}</button>
          <button class="row-action"      data-action="hold">${t("review.hold")}</button>
        </td>
      </tr>`;
  }));
  $("#review-tbody").innerHTML = rows.join("") || `<tr><td colspan="4" class="subtle">${t("review.noTasks")}</td></tr>`;
  $("#review-tbody").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const tr = btn.closest("tr");
    const id = tr.dataset.task;
    btn.disabled = true;
    try {
      await api(`/review-tasks/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: btn.dataset.action }),
      });
      tr.remove();
      toast(t("review.updated", { action: btn.textContent }));
    } catch (err) {
      toast(t("review.failed", { message: err.message }));
      btn.disabled = false;
    }
  });
}

async function renderExport() {
  setMain("tpl-export");
  const input = $("#creator-import-file");
  const button = $("#btn-import-creators");
  const status = $("#creator-import-status");
  button.addEventListener("click", async () => {
    const file = input.files?.[0];
    if (!file) {
      toast(t("import.pickFile"));
      return;
    }
    status.textContent = t("import.running");
    button.disabled = true;
    try {
      const params = new URLSearchParams({ filename: file.name });
      const response = await fetch(`${API}/import/creators/table?${params}`, {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `${response.status}`);
      const message = t("import.done", payload);
      status.textContent = message;
      toast(message);
    } catch (err) {
      const message = t("import.failed", { message: err.message });
      status.textContent = message;
      toast(message);
    } finally {
      button.disabled = false;
    }
  });
}

async function renderSettings() {
  setMain("tpl-settings");
  const a = await api("/app/status");
  const s = await api("/db/status");
  $("#settings-json").textContent = JSON.stringify({ app: a, db: s }, null, 2);

  // Build a structured, scannable display of the same data as labeled groups.
  const pretty = $("#settings-pretty");
  if (pretty) {
    pretty.innerHTML = "";
    pretty.appendChild(buildSettingsGroup(t("settings.groupApp") || "App", a, "app"));
    pretty.appendChild(buildSettingsGroup(t("settings.groupDb") || "Database", s, "db"));
  }

  if (["department_admin", "company_admin", "super_admin"].includes(currentUser?.role)) {
    await renderAdminUsers();
  }
}

function buildSettingsGroup(title, data, kind) {
  const card = document.createElement("div");
  card.className = "settings-group";
  const head = document.createElement("h3");
  head.className = "settings-group-head";
  // Tiny circle indicator: green if "ok=true", else neutral.
  const dot = document.createElement("span");
  dot.className = "status-dot " + (data && data.ok === false ? "bad" : "good");
  head.appendChild(dot);
  head.appendChild(document.createTextNode(" " + title));
  card.appendChild(head);

  const list = document.createElement("dl");
  list.className = "settings-kv";
  for (const [k, v] of Object.entries(data || {})) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = formatSettingValue(v);
    if (typeof v === "string" && v.length > 40) dd.classList.add("mono");
    if (v === true) dd.classList.add("v-true");
    if (v === false) dd.classList.add("v-false");
    list.appendChild(dt);
    list.appendChild(dd);
  }
  card.appendChild(list);
  return card;
}

function formatSettingValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

async function renderAdminUsers() {
  const panel = document.getElementById("admin-users-panel");
  if (!panel) return;
  panel.hidden = false;
  const status = document.getElementById("admin-users-status");
  const tbody = document.getElementById("admin-users-tbody");
  const draw = async () => {
    try {
      const r = await api("/auth/users");
      tbody.innerHTML = (r.items || []).map((u) => `
        <tr>
          <td>${escapeHtml(u.email)}</td>
          <td>${escapeHtml(u.role)}</td>
          <td>${escapeHtml(u.department_name || u.department_code || "-")}</td>
          <td>${escapeHtml(u.is_active ? t("auth.active") : t("auth.disabled"))}</td>
        </tr>
      `).join("") || `<tr><td colspan="4" class="subtle">-</td></tr>`;
    } catch (e) {
      status.textContent = t("auth.usersFailed", { message: e.message });
    }
  };
  document.getElementById("btn-add-user").addEventListener("click", async () => {
    const email = document.getElementById("admin-user-email").value.trim();
    const role = document.getElementById("admin-user-role").value;
    const department = document.getElementById("admin-user-department").value;
    if (!email) return;
    try {
      await api("/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          role,
          department_code: ["department_user", "department_admin"].includes(role) ? department : null,
          is_active: true,
        }),
      });
      status.textContent = t("auth.userSaved");
      document.getElementById("admin-user-email").value = "";
      await draw();
    } catch (e) {
      status.textContent = t("auth.usersFailed", { message: e.message });
    }
  });
  await draw();
}

function setMain(tplId) {
  const tpl = document.getElementById(tplId);
  $("#main").innerHTML = "";
  $("#main").appendChild(tpl.content.cloneNode(true));
  applyI18n($("#main"));
}

/* ----------------- Outreach (建联) modal ------------------- */

const OutreachState = {
  creator: null,
  draftId: null,
  templates: [],
  currentTemplateId: null,
  useAi: false,
  scriptKeywords: "",
  variants: [],
  selectedVariantIndex: 0,
  gmailStatus: null,
  // Multi-account fields
  accounts: [],
  currentAccountId: null, // which account to send from (null = use server default)
};

function bindOutreachButtons() {
  document.querySelectorAll("[data-outreach]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.outreach;
      const creator = window._x9_creators_index?.[id];
      if (creator) openOutreachModal(creator);
    });
  });
}

function bindAssignmentButtons(onDone) {
  document.querySelectorAll("[data-claim]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.claim;
      const creator = window._x9_creators_index?.[id];
      const owner = ensureOperatorName();
      if (!owner) return;
      btn.disabled = true;
      try {
        await api(`/creators/${encodeURIComponent(id)}/claim`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ owner_bd: owner }),
        });
        toast(t("assignment.claimed", { handle: creator?.handle || id }));
        await onDone?.();
      } catch (e) {
        toast(t("assignment.failed", { message: e.message }));
        btn.disabled = false;
      }
    });
  });

  document.querySelectorAll("[data-release]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.release;
      const creator = window._x9_creators_index?.[id];
      const owner = operatorName() || ensureOperatorName();
      if (!owner) return;
      btn.disabled = true;
      try {
        await api(`/creators/${encodeURIComponent(id)}/release`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ owner_bd: owner }),
        });
        toast(t("assignment.released", { handle: creator?.handle || id }));
        await onDone?.();
      } catch (e) {
        toast(t("assignment.failed", { message: e.message }));
        btn.disabled = false;
      }
    });
  });
}

/* -- bio-cell / reason-cell hover popover (full text, no row-growth) -- */

const _bioPopoverState = { showTimer: null, hideTimer: null, anchor: null, bound: false };

function bindBioReasonPopover() {
  const container = document.getElementById("rec-grid") || document.getElementById("rec-tbody");
  const root = document.getElementById("bio-popover-root");
  if (!container || !root) return;

  if (container.dataset.bioPopoverBound !== "1") {
    container.dataset.bioPopoverBound = "1";

    // Delegated mouseenter: triggers when cursor enters a bio/reason cell.
    // Using mouseover (not mouseenter) because mouseenter doesn't bubble.
    container.addEventListener("mouseover", (e) => {
      const cell = e.target.closest(".bio-cell, .reason-cell");
      if (!cell || cell === _bioPopoverState.anchor) return;
      clearTimeout(_bioPopoverState.hideTimer);
      clearTimeout(_bioPopoverState.showTimer);
      _bioPopoverState.showTimer = setTimeout(() => showBioPopover(cell), 250);
    });

    container.addEventListener("mouseout", (e) => {
      const cell = e.target.closest(".bio-cell, .reason-cell");
      if (!cell) return;
      clearTimeout(_bioPopoverState.showTimer);
      // If pointer moved into the popover itself, keep it open
      const into = e.relatedTarget;
      if (into && root.contains(into)) return;
      _bioPopoverState.hideTimer = setTimeout(hideBioPopover, 180);
    });
  }

  if (_bioPopoverState.bound) return;
  _bioPopoverState.bound = true;

  // Keep open when cursor is on the popover (so user can scroll / select)
  root.addEventListener("mouseenter", () => clearTimeout(_bioPopoverState.hideTimer));
  root.addEventListener("mouseleave", () => {
    _bioPopoverState.hideTimer = setTimeout(hideBioPopover, 120);
  });

  // Hide on scroll / click outside / Esc — popover would otherwise misalign
  document.addEventListener("scroll", hideBioPopover, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideBioPopover(); });
}

function showBioPopover(cell) {
  const root = document.getElementById("bio-popover-root");
  if (!root) return;
  const fullText = (cell.dataset.full || cell.textContent || "").trim();
  if (!fullText || fullText === "-") return;

  _bioPopoverState.anchor = cell;
  const isReason = cell.classList.contains("reason-cell");
  const headLabel = isReason ? t("table.reason") : t("table.profileBio");

  root.innerHTML = `
    <div class="bio-popover" role="tooltip">
      <div class="bio-popover-head">${escapeHtml(headLabel)}</div>
      <div class="bio-popover-body">${escapeHtml(fullText)}</div>
    </div>
  `;

  // Position: try right of cell first; if that overflows the viewport try
  // left; if that also overflows, place below.
  const pop = root.querySelector(".bio-popover");
  const rect = cell.getBoundingClientRect();
  const popWidth = 360;
  const popMaxHeight = 280;
  const margin = 8;

  let left = rect.right + margin;
  let top = rect.top;

  if (left + popWidth + margin > window.innerWidth) {
    left = rect.left - popWidth - margin;
  }
  if (left < margin) {
    // Neither right nor left fits — drop below the cell, viewport-clamped
    left = Math.max(margin, Math.min(rect.left, window.innerWidth - popWidth - margin));
    top = rect.bottom + margin;
  }
  if (top + popMaxHeight > window.innerHeight) {
    top = Math.max(margin, window.innerHeight - popMaxHeight - margin);
  }

  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

function hideBioPopover() {
  const root = document.getElementById("bio-popover-root");
  if (root) root.innerHTML = "";
  _bioPopoverState.anchor = null;
}

async function openOutreachModal(creator) {
  OutreachState.creator = creator;
  OutreachState.draftId = null;
  const creatorPanel = renderOutreachCreatorSummary(creator);
  const root = document.getElementById("outreach-modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="outreach-backdrop">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <h3>${escapeHtml(t("outreach.title", { handle: creator.handle || creator.id }))}</h3>
          <button class="modal-close" id="outreach-close" type="button">×</button>
        </div>
        <div class="modal-body">
          <div class="outreach-layout">
            <aside class="outreach-creator-sidebar">
              ${creatorPanel}
            </aside>
            <div class="outreach-compose">
              <div id="outreach-accounts" class="account-section"></div>
              <div id="outreach-banner" class="modal-banner" hidden></div>
              <div class="outreach-ai-panel">
                <label class="outreach-ai-field">
                  <span class="field-label">${t("outreach.scriptKeywords")}</span>
                  <input type="text" id="outreach-keywords" value="${escapeHtml(OutreachState.scriptKeywords)}" placeholder="${escapeHtml(t("outreach.scriptKeywordsPlaceholder"))}" />
                </label>
              </div>
              <label>
                <span class="field-label">${t("outreach.template")}</span>
                <select id="outreach-template"></select>
              </label>
              <label>
                <span class="field-label">${t("outreach.recipient")}</span>
                <input type="email" id="outreach-to" value="${escapeHtml(creator.email || "")}" />
              </label>
              <label>
                <span class="field-label">${t("outreach.subject")}</span>
                <input type="text" id="outreach-subject" />
              </label>
              <label>
                <span class="field-label">${t("outreach.body")}</span>
                <textarea id="outreach-body" rows="14"></textarea>
              </label>
              <div id="outreach-variants" class="outreach-variants" hidden></div>
              <div class="outreach-history" id="outreach-history"></div>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="ghost" id="outreach-regen" type="button">${t("outreach.regenerate")}</button>
          <span class="spacer"></span>
          <button class="ghost" id="outreach-cancel" type="button">${t("outreach.cancel")}</button>
          <button class="ghost" id="outreach-save" type="button">${t("outreach.saveDraft")}</button>
          <button class="primary" id="outreach-send" type="button">${t("outreach.send")}</button>
        </div>
      </div>
    </div>
  `;

  const close = () => {
    root.innerHTML = "";
    OutreachState.creator = null;
    OutreachState.draftId = null;
    OutreachState.variants = [];
    OutreachState.selectedVariantIndex = 0;
    OutreachState.scriptKeywords = "";
  };
  document.getElementById("outreach-close").addEventListener("click", close);
  document.getElementById("outreach-cancel").addEventListener("click", close);
  document.getElementById("outreach-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "outreach-backdrop") close();
  });

  // Load templates, gmail accounts, history, and an initial preview in parallel.
  await Promise.all([
    loadOutreachTemplates(),
    refreshAccountSection(),
    renderOutreachHistory(creator.id),
  ]);
  await refreshOutreachPreview(false);

  document.getElementById("outreach-template").addEventListener("change", () => {
    OutreachState.currentTemplateId = document.getElementById("outreach-template").value;
    syncOutreachLanguageToTemplate();
    refreshOutreachPreview();
  });
  document.getElementById("outreach-keywords").addEventListener("input", (e) => {
    OutreachState.scriptKeywords = e.currentTarget.value;
  });
  document.getElementById("outreach-keywords").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    OutreachState.scriptKeywords = e.currentTarget.value;
    refreshOutreachPreview();
  });
  document.getElementById("outreach-regen").addEventListener("click", () => refreshOutreachPreview());
  document.getElementById("outreach-save").addEventListener("click", saveOutreachDraft);
  document.getElementById("outreach-send").addEventListener("click", sendOutreachEmail);
}

/* ------------------ Gmail multi-account section ------------------ */

/** Open the Google Identity Services popup to authorize a *new* account
 *  (or re-authorize an existing one — picking the same Google account
 *  in the popup just refreshes its token). */
async function triggerGisPopup(triggerBtn) {
  startGmailRedirectAuth(triggerBtn);
  return;
  let info;
  try {
    info = await api("/outreach/gmail/client-info");
  } catch (err) {
    toast(t("outreach.gmailNotConfigured"));
    return;
  }
  if (!info.client_id) {
    toast(t("outreach.gmailNotConfigured"));
    return;
  }
  const originAction = ensureGmailOAuthOrigin(info);
  if (originAction === "redirect") {
    startGmailRedirectAuth(triggerBtn);
    return;
  }
  if (originAction) return;
  if (!window.google?.accounts?.oauth2) {
    startGmailRedirectAuth(triggerBtn);
    return;
  }

  if (triggerBtn) triggerBtn.disabled = true;
  const codeClient = google.accounts.oauth2.initCodeClient({
    client_id: info.client_id,
    scope: (info.scopes || []).join(" "),
    ux_mode: "popup",
    callback: async (response) => {
      if (triggerBtn) triggerBtn.disabled = false;
      if (response.error) { toast(`OAuth 失败: ${response.error}`); return; }
      if (!response.code) { toast("OAuth 没有返回 code"); return; }
      try {
        const r = await api("/outreach/gmail/exchange", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: response.code,
            redirect_uri: window.location.origin,
          }),
        });
        // Auto-select the freshly authorized account so the next send uses it
        if (r.account?.id) OutreachState.currentAccountId = r.account.id;
        if (!document.getElementById("outreach-accounts")) {
          window.location.reload();
          return;
        }
        await refreshAccountSection();
        toast(t("outreach.gmailReady", { email: r.account?.email || "Gmail" }));
      } catch (err) {
        toast(t("auth.notAllowed", { message: err.message }));
      }
    },
    error_callback: (err) => {
      if (triggerBtn) triggerBtn.disabled = false;
      const msg = err?.type || err?.message || JSON.stringify(err || {});
      toast(`OAuth 弹窗错误: ${msg}`);
    },
  });
  codeClient.requestCode();
}

function startGmailRedirectAuth(triggerBtn) {
  if (triggerBtn) triggerBtn.disabled = true;
  if (OutreachState.creator?.id) {
    localStorage.setItem(OUTREACH_PENDING_KEY, OutreachState.creator.id);
  }
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}` || "/";
  const url = `${API}/outreach/gmail/connect?return_to=${encodeURIComponent(returnTo)}&label=${encodeURIComponent("workspace")}`;
  toast(t("outreach.openOAuth"));
  window.location.href = url;
}

function ensureGmailOAuthOrigin(info) {
  const allowed = Array.isArray(info.javascript_origins) ? info.javascript_origins : [];
  if (!allowed.length || allowed.includes(window.location.origin)) return false;
  const candidates = [new URL(window.location.pathname + window.location.search + window.location.hash, "https://usx9.us")];
  const match = candidates.find((url) => allowed.includes(url.origin));
  if (!match) {
    return "redirect";
  }
  window.location.href = match.toString();
  return "switch-origin";
}

/** Pull the latest account list and re-render the picker section. */
async function refreshAccountSection() {
  let accounts = [];
  try {
    const r = await api("/outreach/gmail/accounts");
    accounts = r.items || [];
  } catch { /* ignore */ }
  OutreachState.accounts = accounts;

  // If currentAccountId is gone (deleted), fall back to the default
  if (!accounts.find((a) => a.id === OutreachState.currentAccountId)) {
    const def = accounts.find((a) => a.is_default) || accounts[0] || null;
    OutreachState.currentAccountId = def?.id || null;
  }
  renderAccountSection();
}

function renderAccountSection() {
  const root = document.getElementById("outreach-accounts");
  if (!root) return;
  const accounts = OutreachState.accounts || [];

  // 0 accounts → big "Sign in with Google" entry point
  if (!accounts.length) {
    root.innerHTML = `
      <div class="account-empty">
        <div class="account-empty-msg">${escapeHtml(t("outreach.gmailNotReady"))}</div>
        <button class="gsi-button gsi-connect" id="outreach-gmail-connect" type="button">
          ${gsiLogoSvg()}<span class="gsi-label">${t("outreach.connectGmail")}</span>
        </button>
      </div>
    `;
    document.getElementById("outreach-gmail-connect")
      .addEventListener("click", (e) => triggerGisPopup(e.currentTarget));
    return;
  }

  // 1+ accounts → picker
  const currentId = OutreachState.currentAccountId
    || accounts.find((a) => a.is_default)?.id
    || accounts[0]?.id;
  if (currentId !== OutreachState.currentAccountId) {
    OutreachState.currentAccountId = currentId;
  }

  root.innerHTML = `
    <div class="account-head">
      <span class="field-label">${escapeHtml(t("outreach.sender") || "发件人")}</span>
      <span class="account-count subtle">${accounts.length} ${t("outreach.accountUnit") || "个账号"}</span>
    </div>
    <div class="account-list">
      ${accounts.map((a) => `
        <div class="account-row ${a.id === currentId ? "selected" : ""}" data-id="${escapeHtml(a.id)}">
          <span class="account-radio">${a.id === currentId ? "●" : "○"}</span>
          <span class="account-email">${escapeHtml(a.email || "")}</span>
          ${a.is_default ? `<span class="account-badge">${t("outreach.defaultBadge") || "默认"}</span>` : ""}
          <span class="account-spacer"></span>
          ${!a.is_default ? `<button class="account-action" data-action="default" title="${escapeHtml(t("outreach.setDefault") || "设为默认")}">★</button>` : ""}
          <button class="account-action danger" data-action="remove" title="${escapeHtml(t("outreach.removeAccount") || "删除")}">×</button>
        </div>
      `).join("")}
    </div>
    <button class="account-add" id="outreach-gmail-add" type="button">
      <span class="account-add-icon">+</span>
      <span>${escapeHtml(t("outreach.addAccount") || "添加 Gmail 账号")}</span>
    </button>
  `;

  // Wire interactions
  root.querySelectorAll(".account-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      // Don't switch when clicking action buttons
      if (e.target.closest(".account-action")) return;
      OutreachState.currentAccountId = row.dataset.id;
      renderAccountSection();
    });
  });
  root.querySelectorAll('[data-action="default"]').forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const row = btn.closest(".account-row");
      const id = row?.dataset.id;
      if (!id) return;
      try {
        await api(`/outreach/gmail/accounts/${encodeURIComponent(id)}/default`, { method: "POST" });
        await refreshAccountSection();
      } catch (err) { toast(err.message); }
    });
  });
  root.querySelectorAll('[data-action="remove"]').forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const row = btn.closest(".account-row");
      const id = row?.dataset.id;
      const email = row?.querySelector(".account-email")?.textContent || "";
      if (!id) return;
      if (!confirm(`${t("outreach.removeAccountConfirm") || "确定删除这个 Gmail 账号？"}\n${email}`)) return;
      try {
        await api(`/outreach/gmail/accounts/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (OutreachState.currentAccountId === id) OutreachState.currentAccountId = null;
        await refreshAccountSection();
      } catch (err) { toast(err.message); }
    });
  });
  document.getElementById("outreach-gmail-add")
    .addEventListener("click", (e) => triggerGisPopup(e.currentTarget));
}

function gsiLogoSvg() {
  return `<svg class="gsi-logo" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.49h4.84c-.21 1.13-.84 2.09-1.78 2.73v2.27h2.88c1.69-1.55 2.7-3.84 2.7-6.65z"/>
    <path fill="#34A853" d="M9 18c2.43 0 4.47-.81 5.96-2.18l-2.88-2.27c-.8.54-1.83.86-3.08.86-2.36 0-4.36-1.6-5.07-3.74H.92v2.34A8.99 8.99 0 0 0 9 18z"/>
    <path fill="#FBBC05" d="M3.93 10.67A5.4 5.4 0 0 1 3.65 9c0-.58.1-1.14.28-1.67V4.99H.92A8.99 8.99 0 0 0 0 9c0 1.45.35 2.82.92 4.01l3.01-2.34z"/>
    <path fill="#EA4335" d="M9 3.58c1.32 0 2.51.46 3.45 1.35l2.59-2.59C13.46.89 11.43 0 9 0A8.99 8.99 0 0 0 .92 4.99l3.01 2.34C4.64 5.18 6.64 3.58 9 3.58z"/>
  </svg>`;
}

async function loadOutreachTemplates() {
  try {
    const r = await api("/outreach/templates");
    OutreachState.templates = r.items || [];
  } catch (e) {
    OutreachState.templates = [];
  }
  const sel = document.getElementById("outreach-template");
  if (!sel) return;
  const collab = OutreachState.creator?.recommended_collab_type || null;
  const targetLang = "en";
  const languageFiltered = targetLang
    ? OutreachState.templates.filter((tpl) => tpl.language === targetLang)
    : OutreachState.templates;
  const templatePool = languageFiltered.length ? languageFiltered : OutreachState.templates;
  // Stable sort: AI copy is English-first, then collab match, default flag, name.
  const sorted = [...templatePool].sort((a, b) => {
    const aLang = targetLang && a.language === targetLang ? 0 : 1;
    const bLang = targetLang && b.language === targetLang ? 0 : 1;
    if (aLang !== bLang) return aLang - bLang;
    const aMatch = collab && a.collab_type === collab ? 0 : 1;
    const bMatch = collab && b.collab_type === collab ? 0 : 1;
    if (aMatch !== bMatch) return aMatch - bMatch;
    if (a.is_default !== b.is_default) return a.is_default ? -1 : 1;
    return (a.name || "").localeCompare(b.name || "");
  });
  sel.innerHTML = sorted.map((tpl) => `
    <option value="${escapeHtml(tpl.id)}">${escapeHtml(outreachTemplateOptionLabel(tpl, targetLang))}</option>
  `).join("") || `<option value="">(no templates)</option>`;
  OutreachState.currentTemplateId = sorted[0]?.id || null;
  if (OutreachState.currentTemplateId) sel.value = OutreachState.currentTemplateId;
  syncOutreachLanguageToTemplate();
}

function codeLabelForLanguage(group, code, language) {
  if (!code) return dash();
  const lang = String(language || currentLanguage || "").toLowerCase().startsWith("en") ? "en" : "zh";
  const key = `${group}.${code}`;
  return I18N[lang]?.[key] || I18N[currentLanguage]?.[key] || I18N.zh[key] || I18N.en[key] || code;
}

function outreachTemplateOptionLabel(tpl, targetLang = null) {
  const name = String(tpl?.name || dash()).trim();
  const parts = [name];
  const collab = tpl?.collab_type ? codeLabelForLanguage("collab", tpl.collab_type, targetLang || tpl.language) : "";
  if (collab && collab !== dash() && !name.toLowerCase().includes(collab.toLowerCase())) {
    parts.push(collab);
  }
  if (!targetLang && tpl?.language && !name.toLowerCase().includes(String(tpl.language).toLowerCase())) {
    parts.push(String(tpl.language).toUpperCase());
  }
  return parts.join(" · ");
}

function selectedOutreachTemplate() {
  return (OutreachState.templates || []).find((tpl) => tpl.id === OutreachState.currentTemplateId) || null;
}

function syncOutreachLanguageToTemplate() {
  if (getOutreachUseAi()) return;
  const tpl = selectedOutreachTemplate();
  const langEl = document.getElementById("outreach-language");
  if (!tpl?.language || !langEl) return;
  if ([...langEl.options].some((option) => option.value === tpl.language)) {
    langEl.value = tpl.language;
  }
}

function getOutreachUseAi() {
  const el = document.getElementById("outreach-use-ai");
  return el ? Boolean(el.checked) : false;
}

function updateOutreachAiControls() {
  const useAi = getOutreachUseAi();
  OutreachState.useAi = useAi;
  const toneEl = document.getElementById("outreach-tone");
  const languageEl = document.getElementById("outreach-language");
  if (toneEl) toneEl.disabled = !useAi;
  if (languageEl) {
    languageEl.value = "en";
    languageEl.disabled = true;
  }
}

function setOutreachBanner(kind, message) {
  const banner = document.getElementById("outreach-banner");
  if (!banner) return;
  if (!message) {
    banner.hidden = true;
    banner.textContent = "";
    return;
  }
  banner.hidden = false;
  banner.className = `modal-banner ${kind || "good"}`;
  banner.textContent = message;
}

function outreachStatusMessage(status, requestedAi) {
  if (status === "keyword_reference") return t("outreach.generatedKeyword");
  if (!requestedAi) return t("outreach.generatedTemplate");
  if (status === "generated") return t("outreach.generatedAi");
  if (status === "not_configured") return t("outreach.aiNotConfigured");
  if (status === "unavailable") return t("outreach.aiUnavailable");
  if (status === "error") return t("outreach.aiError");
  return t("outreach.aiFallback");
}

function outreachStatusKind(status, hasEmail) {
  if (!hasEmail) return "warn";
  if (status === "generated" || status === "template" || status === "keyword_reference") return "good";
  if (status === "error") return "bad";
  return "warn";
}

function renderOutreachVariants(primary, variants) {
  const box = document.getElementById("outreach-variants");
  if (!box) return;
  const all = [primary, ...(variants || [])]
    .filter((item) => item && item.subject && item.body)
    .map((item) => ({ subject: String(item.subject), body: String(item.body) }));
  OutreachState.variants = all;
  OutreachState.selectedVariantIndex = 0;
  if (all.length <= 1) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = `
    <div class="outreach-variants-title">${escapeHtml(t("outreach.variants"))}</div>
    <div class="outreach-variant-list">
      ${all.map((item, index) => `
        <button class="outreach-variant ${index === 0 ? "active" : ""}" type="button" data-index="${index}">
          <span>${escapeHtml(t("outreach.variant", { index: index + 1 }))}</span>
          <small>${escapeHtml(shortText(item.subject, 54))}</small>
        </button>
      `).join("")}
    </div>
  `;
  box.querySelectorAll(".outreach-variant").forEach((btn) => {
    btn.addEventListener("click", () => selectOutreachVariant(Number(btn.dataset.index || 0)));
  });
}

function selectOutreachVariant(index) {
  const item = OutreachState.variants[index];
  if (!item) return;
  OutreachState.selectedVariantIndex = index;
  const subjectEl = document.getElementById("outreach-subject");
  const bodyEl = document.getElementById("outreach-body");
  if (subjectEl) subjectEl.value = item.subject;
  if (bodyEl) bodyEl.value = item.body;
  document.querySelectorAll(".outreach-variant").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.index || 0) === index);
  });
}

async function refreshOutreachPreview(useAi = null) {
  const creator = OutreachState.creator;
  if (!creator) return;
  const requestedAi = useAi === null ? getOutreachUseAi() : Boolean(useAi);
  const useAiEl = document.getElementById("outreach-use-ai");
  if (useAiEl) useAiEl.checked = requestedAi;
  updateOutreachAiControls();
  const keywordBrief = (document.getElementById("outreach-keywords")?.value || "").trim();
  OutreachState.scriptKeywords = keywordBrief;
  const body = {
    use_ai: requestedAi,
    n: requestedAi && !keywordBrief ? 3 : 1,
    language: "en",
  };
  if (keywordBrief) body.script_keywords = keywordBrief;
  if (OutreachState.currentTemplateId) body.template_id = OutreachState.currentTemplateId;
  if (requestedAi) {
    body.tone = document.getElementById("outreach-tone")?.value || "friendly";
    body.language = "en";
  }
  const regenBtn = document.getElementById("outreach-regen");
  if (regenBtn) regenBtn.disabled = true;
  setOutreachBanner("warn", requestedAi ? t("outreach.generatingAi") : t("outreach.generatingTemplate"));
  try {
    const r = await api(`/outreach/preview/${encodeURIComponent(creator.id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const subjectEl = document.getElementById("outreach-subject");
    const bodyEl = document.getElementById("outreach-body");
    const toEl = document.getElementById("outreach-to");
    if (subjectEl) subjectEl.value = r.subject || "";
    if (bodyEl) bodyEl.value = r.body || "";
    if (toEl && !toEl.value) toEl.value = r.to_email || "";
    const status = r.ai_status || (r.ai_used ? "generated" : (requestedAi ? "fallback" : "template"));
    let message = outreachStatusMessage(status, requestedAi);
    if (!r.has_email) message = `${message} ${t("outreach.noEmail")}`;
    setOutreachBanner(outreachStatusKind(status, r.has_email), message);
    renderOutreachVariants(
      { subject: r.subject || "", body: r.body || "" },
      requestedAi && r.ai_used ? (r.variants || []) : [],
    );
    toast(message);
  } catch (e) {
    renderOutreachVariants({ subject: "", body: "" }, []);
    setOutreachBanner("bad", t("outreach.regenerateFailed", { message: e.message }));
    toast(t("outreach.regenerateFailed", { message: e.message }));
  } finally {
    if (regenBtn) regenBtn.disabled = false;
  }
}


const OUTREACH_PENDING_KEY = "x9_outreach_pending_creator";

/** Called once at app boot. If we just came back from a Google OAuth
 *  redirect (`?gmail=ok` or `?gmail=error`), show a toast and re-open the
 *  outreach modal for the creator we were drafting for. */
async function handleGmailRedirect() {
  const params = new URLSearchParams(window.location.search);
  const flag = params.get("gmail");
  if (!flag) return;

  // Strip the query so a refresh doesn't re-fire this handler.
  const url = new URL(window.location.href);
  url.searchParams.delete("gmail");
  url.searchParams.delete("email");
  url.searchParams.delete("msg");
  window.history.replaceState({}, "", url.toString());

  if (flag === "ok") {
    const email = params.get("email") || "Gmail";
    toast(t("outreach.gmailReady", { email }));
  } else {
    const msg = params.get("msg") || "unknown error";
    toast(t("outreach.sendFailed", { message: msg }));
  }

  // Restore the building-up draft if we had one in flight.
  const pendingId = localStorage.getItem(OUTREACH_PENDING_KEY);
  localStorage.removeItem(OUTREACH_PENDING_KEY);
  if (!pendingId) return;
  try {
    const creator = await api(`/creators/${encodeURIComponent(pendingId)}`);
    // Recommendations page has its own renderer; jump there first so the
    // "建联" button + creator index are present, then open the modal.
    if (currentPage !== "recommendations") {
      go("recommendations");
      // wait for the table to draw before we open the modal
      setTimeout(() => openOutreachModal(creator), 600);
    } else {
      openOutreachModal(creator);
    }
  } catch (e) {
    /* creator gone — nothing to restore */
  }
}

async function saveOutreachDraft(options = {}) {
  const creator = OutreachState.creator;
  if (!creator) return;
  const silent = Boolean(options.silent);
  const payload = {
    creator_id: String(creator.id),
    template_id: OutreachState.currentTemplateId || null,
    to_email: document.getElementById("outreach-to").value.trim() || null,
    subject: document.getElementById("outreach-subject").value,
    body: document.getElementById("outreach-body").value,
    ai_versions: OutreachState.variants.length ? OutreachState.variants : null,
    ai_tone: getOutreachUseAi() ? (document.getElementById("outreach-tone")?.value || null) : null,
    ai_language: getOutreachUseAi() ? (document.getElementById("outreach-language")?.value || null) : null,
  };
  try {
    if (OutreachState.draftId) {
      await api(`/outreach/draft/${encodeURIComponent(OutreachState.draftId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_email: payload.to_email,
          subject: payload.subject,
          body: payload.body,
          ai_versions: payload.ai_versions,
          ai_tone: payload.ai_tone,
          ai_language: payload.ai_language,
        }),
      });
    } else {
      const r = await api("/outreach/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      OutreachState.draftId = r.id;
    }
    if (!silent) toast(t("outreach.draftSaved"));
    await renderOutreachHistory(creator.id);
    return true;
  } catch (e) {
    toast(t("outreach.sendFailed", { message: e.message }));
    return false;
  }
}

async function sendOutreachEmail() {
  const creator = OutreachState.creator;
  if (!creator) return;
  if (!confirm(t("outreach.confirmSend"))) return;
  // Always make sure we have a fresh draft on the server before sending.
  const saved = await saveOutreachDraft({ silent: true });
  if (!saved || !OutreachState.draftId) return;
  const sendBtn = document.getElementById("outreach-send");
  if (sendBtn) sendBtn.disabled = true;
  try {
    await api(`/outreach/send/${encodeURIComponent(OutreachState.draftId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confirm: true,
        update_creator_status: true,
        from_account_id: OutreachState.currentAccountId || null,
      }),
    });
    toast(t("outreach.sent"));
    applyOutreachSentStatus(creator);
    await renderOutreachHistory(creator.id);
  } catch (e) {
    toast(t("outreach.sendFailed", { message: e.message }));
    if (sendBtn) sendBtn.disabled = false;
    await refreshAccountSection();
  }
}

function applyOutreachSentStatus(creator) {
  if (!creator) return;
  creator.current_status = "已建联";
  const id = String(creator.id || "");
  if (id && window._x9_creators_index?.[id]) {
    window._x9_creators_index[id].current_status = "已建联";
  }
  const statusSelectorId = window.CSS?.escape ? CSS.escape(id) : id.replaceAll('"', '\\"');
  const statusNodes = document.querySelectorAll(`[data-creator-status="${statusSelectorId}"]`);
  statusNodes.forEach((node) => {
    node.textContent = codeLabel("current_status", "已建联");
  });
  if (currentPage === "recommendations") renderers.recommendations();
}

async function renderOutreachHistory(creatorId) {
  const box = document.getElementById("outreach-history");
  if (!box) return;
  let rows = [];
  try {
    const r = await api(`/outreach/history/${encodeURIComponent(creatorId)}`);
    rows = r.items || [];
  } catch (e) { /* ignore */ }
  if (!rows.length) {
    box.innerHTML = `<div class="subtle">${t("outreach.history")}: ${t("outreach.noHistory")}</div>`;
    return;
  }
  const statusLabel = (s) => {
    const key = `outreach.status${s.charAt(0).toUpperCase()}${s.slice(1)}`;
    return I18N[currentLanguage]?.[key] || s;
  };
  box.innerHTML = `<div class="subtle" style="margin-bottom:4px">${t("outreach.history")}</div>` +
    rows.slice(0, 6).map((row) => `
      <div class="outreach-history-item ${row.status}">
        <span>${formatTime(row.sent_at || row.created_at)}</span>
        <span>·</span>
        <span>${escapeHtml(statusLabel(row.status))}</span>
        <span>·</span>
        <span>${escapeHtml(shortText(row.subject || "(no subject)", 40))}</span>
      </div>
    `).join("");
}

const renderers = {
  dashboard: renderDashboard,
  business: renderBusiness,
  collection: renderCollection,
  recommendations: renderRecommendations,
  review: renderReview,
  export: renderExport,
  hotkw: renderHotKw,
  assistant: renderAssistant,
};

function go(page) {
  if (page !== "hotkw" && hotKwTimer) {
    clearInterval(hotKwTimer);
    hotKwTimer = null;
  }
  currentPage = page;
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.page === page));
  syncPageTitle(page);
  closeSidebarDrawer();
  renderers[page]?.();
}

// Mirror the active nav label into the page-topbar title.
function syncPageTitle(page) {
  const titleEl = document.getElementById("page-title");
  if (!titleEl) return;
  const key = `nav.${page}`;
  const localized = t(key);
  // Fall back to whatever the active tab is showing if i18n misses.
  if (localized && localized !== key) {
    titleEl.textContent = localized;
    titleEl.setAttribute("data-i18n", key);
  } else {
    const activeTab = document.querySelector(`.tab[data-page="${page}"] .nav-label`);
    if (activeTab) titleEl.textContent = activeTab.textContent;
  }
}

function openSidebarDrawer() {
  document.getElementById("sidebar")?.classList.add("open");
  const scrim = document.getElementById("sidebar-scrim");
  if (scrim) { scrim.hidden = false; requestAnimationFrame(() => scrim.classList.add("open")); }
}
function closeSidebarDrawer() {
  document.getElementById("sidebar")?.classList.remove("open");
  const scrim = document.getElementById("sidebar-scrim");
  if (scrim) {
    scrim.classList.remove("open");
    setTimeout(() => { scrim.hidden = true; }, 200);
  }
}

function setLanguage(nextLanguage) {
  currentLanguage = nextLanguage === "en" ? "en" : "zh";
  localStorage.setItem(LANG_KEY, currentLanguage);
  applyI18n(document);
  renderers[currentPage]();
}

async function initApp() {
  applyI18n(document);
  currentUser = await fetchCurrentUser();
  if (!currentUser) {
    renderLoginScreen();
    return;
  }
  if (["department_admin", "company_admin", "super_admin"].includes(currentUser.role) && currentUser.entry_scope === "admin") {
    window.location.href = "/admin/";
    return;
  }
  const workspaceMatch = window.location.pathname.match(/^\/workspace\/([^/]+)\//);
  if (workspaceMatch && currentUser.department_slug && workspaceMatch[1] !== currentUser.department_slug) {
    window.location.href = `/workspace/${currentUser.department_slug}/`;
    return;
  }
  updateCurrentUserBar();
  document.querySelector('.tab[data-page="settings"]')?.remove();

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => go(tab.dataset.page)));

  // Language toggle: flip + brief swap animation on the visible label.
  document.getElementById("btn-language")?.addEventListener("click", (e) => {
    const btn = e.currentTarget;
    btn.classList.add("swapping");
    setTimeout(() => {
      setLanguage(currentLanguage === "zh" ? "en" : "zh");
      btn.classList.remove("swapping");
    }, 120);
  });
  syncLanguageToggle();

  // Theme toggle — flip the effective theme and persist.
  // Effective theme = explicit data-theme if set, else the system preference.
  const themeBtn = document.getElementById("btn-theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const explicit = document.documentElement.getAttribute("data-theme");
      const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
      const effective = explicit || (systemDark ? "dark" : "light");
      const next = effective === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("x9-theme", next);
    });
  }

  // Live system-theme listener — only applies when the user hasn't picked one.
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
    if (!localStorage.getItem("x9-theme")) {
      // No-op: not having data-theme means the CSS @media query picks it up
      // automatically. We just want the page to re-render any JS-tied bits.
      document.documentElement.removeAttribute("data-theme");
    }
  });

  // Sidebar hamburger toggle (phone only) — drawer pattern.
  document.getElementById("btn-sidebar-toggle")?.addEventListener("click", () => {
    const sidebar = document.getElementById("sidebar");
    if (sidebar?.classList.contains("open")) closeSidebarDrawer();
    else openSidebarDrawer();
  });
  document.getElementById("sidebar-scrim")?.addEventListener("click", closeSidebarDrawer);

  // Initial page title sync to current tab.
  syncPageTitle(currentPage);

  document.getElementById("btn-logout").addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.href = "/login";
  });

  document.getElementById("btn-pipeline").addEventListener("click", async () => {
    try {
      const r = await api("/process/run-full-pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      toast(t("pipeline.done", { count: r.processed }));
      renderers[currentPage]();
    } catch (e) {
      toast(t("pipeline.failed", { message: e.message }));
    }
  });

  document.getElementById("btn-refresh").addEventListener("click", () => renderers[currentPage]());

  document.getElementById("btn-download-extension").addEventListener("click", async () => {
    try {
      // Trigger the actual file download via a hidden anchor so the browser
      // shows its native download UI (rather than fetch-then-blob, which can
      // miss the cookie/auth context the rest of the page uses).
      const a = document.createElement("a");
      a.href = "/api/local/extension/download";
      a.download = "x9-tk-creator-extension.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();

      // Show install instructions in a modal-style overlay.
      showInstallExtensionGuide();
    } catch (e) {
      toast(t("extInstall.downloadFailed", { message: e.message }));
    }
  });

  go("dashboard");
  setInterval(() => { if (currentPage === "dashboard") refreshDashboardData(); }, 5000);
  handleGmailRedirect();
}

initApp();
