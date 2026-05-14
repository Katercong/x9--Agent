# 字段说明

## product (产品主表)

| 字段 | 类型 | 含义 |
|---|---|---|
| id | INTEGER PK | 自增 |
| sku_code | TEXT UNIQUE | SKU 编码，如 `BU02P155` |
| art_no | TEXT | 货号（通常 = sku_code） |
| name_en / name_zh | TEXT | 英中文名 |
| category_id | FK | 类目 (female_care/adult_care/pet/baby/home_care/mask) |
| subcategory | TEXT | 子类（卫生巾/护垫/纸尿裤/隔尿垫…） |
| series | TEXT | 系列 (Cotton Cover Pads, Ultra Thin Pads…) |
| size_label | TEXT | 240mm / M / 56*56 |
| pcs_per_pack | INT | 单包片数 |
| packs_per_case | INT | 单件包数 |
| price_tiktok / price_temu / price_ebay / price_ebay_local / price_independent | REAL | 各平台 USD 售价 |
| positioning_zh | TEXT | 低价高转化 / 中高客单 / 高客单品牌调性 |
| tier | TEXT | 1号主推 / 2号主推 / 3号主推 / 常规 |
| description_en / _zh | TEXT | 长描述 |
| selling_points_en / _zh | JSON 数组 | 卖点 |
| pain_points_zh | JSON 数组 | 用户痛点 |
| scenarios_en / _zh | JSON 数组 | 使用场景 |
| target_audience_en / _zh | TEXT | 目标人群 |
| proof | TEXT | 认证 (FDA / Dermatologically tested) |
| vocabulary_en | JSON 数组 | AI 文案词库 |
| creative_angles_en | JSON 数组 | 创意切入点 |
| safe_scenes_en | JSON 数组 | AI 生图安全镜头 |
| focus_zh | TEXT | 卖点重心提示 |
| amazon_url / short_url | TEXT | 站外链接 |
| tk_content_key | TEXT | 桥接到 TK_Content workbench PRODUCT_LIBRARY 的 key |
| commission_rate_default | REAL | 默认达人佣金率 (0.05 = 5%) |
| creator_match_levels | JSON 数组 | `["S","A","B"]` 推荐合作的达人等级 |
| creator_persona_zh | TEXT | 达人画像描述 |
| is_main_push | BOOL | 是否主推款 (1/0) |
| status | TEXT | active / draft / inactive |

## creator (达人主表)

| 字段 | 类型 | 含义 |
|---|---|---|
| id | INTEGER PK | 自增 |
| handle | TEXT | TikTok / IG handle (不带 @) |
| platform | TEXT | tiktok / instagram / youtube |
| profile_url | TEXT | 主页 URL |
| display_name | TEXT | 显示名 |
| country / language | TEXT | 国家 / 语言 |
| category_tags | JSON 数组 | 内容标签 ["女性护理","母婴"] |
| followers | INT | 粉丝数 |
| followers_raw | TEXT | 原始字符串 "53.9K" |
| tier | TEXT | S / A / B / C / D — 自动按粉丝数划分 |
| avg_views | INT | 平均播放量 |
| gmv_30d_usd | REAL | 30 天带货 GMV |
| pps | REAL | 内容表现分 |
| sample_score | REAL | 样品评分 (0-100) |
| post_rate_est | REAL | 预估发布率 0~1 |
| email / whatsapp / instagram_handle / youtube_handle | TEXT | 跨平台联系方式 |
| current_status | TEXT | 见下方状态机 |
| store_assigned | TEXT | 店铺归属 (X9x9 Shop, Shores Bluff Mist 等) |
| owner_bd | TEXT | 国内对接人 |
| first_contact_date / last_contact_date | TEXT | ISO date |
| notes | TEXT | 自由备注 |
| source | TEXT | weekly_import / cm_import / scraper / manual |
| quality_score | REAL | (后续 AI 评分模型输出) |

### 状态机 current_status

```
prospect (候选)
   ↓ 发起联系
contacted (已建联)
   ↓ 达人确认合作
confirmed (已确认)
   ↓ 寄样
sample_shipped (已寄样)
   ↓ 物流签收
sample_delivered (样品签收)
   ↓ 达人发布视频
video_published (视频已发布)
   ↓ 达人提供 Spark Ads code
ad_authorized (已授权)
   ↓ 投放广告
ad_running (广告投放中)

任意阶段 → dropped (放弃 / 不合作)
```

## outreach (建联事件流水)

一条 = 一次 BD 操作（建联 / 寄样 / 视频发布 / 授权 / 跑广告）。

| 字段 | 含义 |
|---|---|
| creator_id | FK |
| event_date | 事件日期 |
| store_name / bd_owner | 那次操作的归属店铺、对接人 |
| action | contact / confirm / ship / deliver / post / authorize / run_ad / drop |
| status | 事件后的达人新状态 (冗余便于审计) |
| channel | dm / email / whatsapp / cm |
| message | 邀约话术原文 |
| sample_qty | 寄样数量 |
| commission_rate | 这次约定的佣金率 |
| video_url | 达人发布的视频链接 |
| ad_auth_code | Spark Ads 授权码 |
| remark | 备注 |

## outreach_sku (一次寄样涉及多个 SKU)
`(outreach_id, product_id, qty)` 联表。

## creator_product (达人 × 产品 兴趣矩阵)
`(creator_id, product_id, relation)` — relation: interest / sampled / posted / authorized。
后续 AI 推荐 "这个达人最适合推哪些 SKU" 会读这里。

## product_image
- `rel_path = "assets/reference-images/xxx.png"` → 直接落地资源
- `rel_path = "intern://女性产品图/外包装展示/xxx.png"` → 由 FastAPI 透传到 `F:\实习生\A社媒\` 原图
- `kind`: main / package / content / scene / reference

## audit_log
所有 INSERT / UPDATE / DELETE 写入，便于回溯。
