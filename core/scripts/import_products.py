"""Import the product catalog into SQLite.

Sources merged into one row per SKU:
  1. Price table xlsx          -> sku_code, names, size, pcs/pack, prices
  2. Selling-points docx (4)   -> description, selling_points, scenarios, target audience
  3. 主推 SKU PDF              -> tier, positioning, pain points, creator persona
  4. 达人划分表 PDF            -> creator_match_levels for each main-push group
  5. TK_Content PRODUCT_LIBRARY -> tk_content_key, vocabulary, creative_angles, safe_scenes

Re-runnable: upserts on sku_code (does NOT delete rows that previously existed).
"""
from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

PRICE_XLSX = Path(r"C:\Users\Administrator\Desktop\x9产品\X9各平台销售价格表--（B2C平台售价一览）.xlsx")
INTERN_ROOT = Path(r"F:\实习生")
DOCX_FEMALE = INTERN_ROOT / "A社媒" / "女性系列产品卖点梳理.docx"
DOCX_PET = INTERN_ROOT / "A社媒" / "宠物系列产品卖点梳理.docx"
DOCX_ADULT = INTERN_ROOT / "A社媒" / "成人系列产品卖点梳理.docx"
DOCX_BABY = INTERN_ROOT / "A社媒" / "母婴系列产品卖点梳理.docx"

# ============================================================
# Categories
# ============================================================
CATEGORIES = [
    ("female_care", "女性护理", "Female Care"),
    ("adult_care",  "成人护理", "Adult Care"),
    ("pet",         "宠物用品", "Pet Care"),
    ("baby",        "母婴",     "Baby Care"),
    ("home_care",   "家居护理", "Home Care"),
    ("mask",        "口罩",     "Masks"),
]

# ============================================================
# SKU 元数据补全：分类 / 子类 / 系列 / TK_Content key / 主推等级
# 这里集中维护 — 后续新增 SKU 在此扩展
# ============================================================
# (sku_code) -> dict
SKU_META = {
    # ---- 女性护理 ----
    "BU02P155": dict(category="female_care", subcategory="护垫",
                     series="Cotton Cover Panty Liners", tk_key="cotton_cover_panty_liners",
                     tier="1号主推", positioning_zh="低价高转化，利润款，信任基石高复购",
                     match=["S","A","B"], main=1),
    "BU03P180": dict(category="female_care", subcategory="护垫",
                     series="Cotton Cover Panty Liners", tk_key="cotton_cover_panty_liners",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU01R240": dict(category="female_care", subcategory="卫生巾",
                     series="Cotton Cover Pads", tk_key="cotton_cover_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU01S280": dict(category="female_care", subcategory="卫生巾",
                     series="Cotton Cover Pads", tk_key="cotton_cover_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU01N320": dict(category="female_care", subcategory="卫生巾",
                     series="Cotton Cover Pads", tk_key="cotton_cover_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU04R245": dict(category="female_care", subcategory="卫生巾",
                     series="Ultra Thin Pads", tk_key="ultra_thin_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU04S290": dict(category="female_care", subcategory="卫生巾",
                     series="Ultra Thin Pads", tk_key="ultra_thin_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU04N330": dict(category="female_care", subcategory="卫生巾",
                     series="Ultra Thin Pads", tk_key="ultra_thin_pads",
                     tier="1号主推", positioning_zh="低价高转化",
                     match=["S","A","B"], main=1),
    "BU06PML1": dict(category="female_care", subcategory="经期裤",
                     series="Period Underwear", tk_key="period_underwear",
                     tier="常规", positioning_zh="夜用安心",
                     match=["A","B"], main=0),

    # ---- 成人护理 ----
    "CU01M001B1": dict(category="adult_care", subcategory="纸尿裤",
                       series="Adult Diaper with Tabs", tk_key="adult_tabs",
                       tier="常规", match=["A","B"], main=0),
    "CU01L002B1": dict(category="adult_care", subcategory="纸尿裤",
                       series="Adult Diaper with Tabs", tk_key="adult_tabs",
                       tier="常规", match=["A","B"], main=0),
    "CU01XL03B1": dict(category="adult_care", subcategory="纸尿裤",
                       series="Adult Diaper with Tabs", tk_key="adult_tabs",
                       tier="常规", match=["A","B"], main=0),
    "CU02M001B1": dict(category="adult_care", subcategory="拉拉裤",
                       series="Disposable Briefs", tk_key="disposable_briefs",
                       tier="常规", match=["A","B"], main=0),
    "CU02L002B1": dict(category="adult_care", subcategory="拉拉裤",
                       series="Disposable Briefs", tk_key="disposable_briefs",
                       tier="常规", match=["A","B"], main=0),
    "CU02XL03B1": dict(category="adult_care", subcategory="拉拉裤",
                       series="Disposable Briefs", tk_key="disposable_briefs",
                       tier="常规", match=["A","B"], main=0),
    "CU05W185": dict(category="adult_care", subcategory="失禁护垫",
                     series="Women Incontinence Pads", tk_key="women_pads",
                     tier="常规", match=["A","B"], main=0),
    "CU06W280": dict(category="adult_care", subcategory="失禁护垫",
                     series="Women Incontinence Pads", tk_key="women_pads",
                     tier="常规", match=["A","B"], main=0),
    "CU07M445": dict(category="adult_care", subcategory="产后护理垫",
                     series="Maxi Postpartum Pads", tk_key="postpartum_pads",
                     tier="常规", match=["A","B"], main=0),
    "CU08C380A1": dict(category="adult_care", subcategory="产后护理垫",
                      series="Calabash-Shaped Postpartum Pads",
                      tk_key="calabash_postpartum_pads",
                      tier="常规", match=["A","B"], main=0),

    # ---- 母婴 ----
    "DU03B115": dict(category="baby", subcategory="乳垫",
                     series="Disposable Nursing Pads", tk_key="nursing_pads",
                     tier="常规", match=["B","C"], main=0),
    "AU01NB01A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),
    "AU01S002A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),
    "AU01M003A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),
    "AU01L004A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),
    "AU01XL05A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),
    "AU01XXL6A1": dict(category="baby", subcategory="纸尿裤",
                       series="Ultra Thin Baby Diapers",
                       tk_key="ultra_thin_baby_diapers",
                       tier="常规", match=["A","B"], main=0),

    # ---- 宠物 ----
    "EU01P660": dict(category="pet", subcategory="宠物训练垫",
                     series="Training Pads", tk_key="training_pads",
                     tier="常规", match=["A","B"], main=0),
    "EU06FDXS": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (female)", tk_key="disposable_diapers",
                     tier="2号主推", positioning_zh="中高客单、高毛利",
                     match=["A","B"], main=1),
    "EU06FDDS": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (female)", tk_key="disposable_diapers",
                     tier="2号主推", match=["A","B"], main=1),
    "EU06FDDM": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (female)", tk_key="disposable_diapers",
                     tier="2号主推", match=["A","B"], main=1),
    "EU06FDDL": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (female)", tk_key="disposable_diapers",
                     tier="2号主推", match=["A","B"], main=1),
    "EU05DDXS": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (male wraps)",
                     tk_key="disposable_male_wraps",
                     tier="2号主推", match=["A","B"], main=1),
    "EU05MDDS": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (male wraps)",
                     tk_key="disposable_male_wraps",
                     tier="2号主推", match=["A","B"], main=1),
    "EU05MDDM": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (male wraps)",
                     tk_key="disposable_male_wraps",
                     tier="2号主推", match=["A","B"], main=1),
    "EU05MDDL": dict(category="pet", subcategory="宠物纸尿裤",
                     series="Pet Diapers (male wraps)",
                     tk_key="disposable_male_wraps",
                     tier="2号主推", match=["A","B"], main=1),

    # ---- 家居护理 (隔尿垫) ----
    "EU02P565A1": dict(category="home_care", subcategory="隔尿垫",
                      series="Regular Underpads", tk_key="regular_underpads",
                      tier="3号主推", positioning_zh="高客单、品牌调性",
                      match=["S","A"], main=1),
    "EU02UP790A1": dict(category="home_care", subcategory="隔尿垫",
                       series="Regular Underpads", tk_key="regular_underpads",
                       tier="3号主推", match=["S","A"], main=1),
    "EU02P786A1": dict(category="home_care", subcategory="隔尿垫",
                      series="Regular Underpads", tk_key="regular_underpads",
                      tier="3号主推", match=["S","A"], main=1),
    "EU04565A1":  dict(category="home_care", subcategory="隔尿垫",
                      series="Activated Charcoal Underpads",
                      tk_key="activated_charcoal_underpads",
                      tier="常规", match=["A","B"], main=0),
    "EU04P786A1": dict(category="home_care", subcategory="隔尿垫",
                      series="Activated Charcoal Underpads",
                      tk_key="activated_charcoal_underpads",
                      tier="常规", match=["A","B"], main=0),
    "EU03P565A1": dict(category="home_care", subcategory="隔尿垫",
                      series="Lavender Underpads", tk_key="lavender_underpads",
                      tier="常规", match=["A","B"], main=0),
    "EU03P786A1": dict(category="home_care", subcategory="隔尿垫",
                      series="Lavender Underpads", tk_key="lavender_underpads",
                      tier="常规", match=["A","B"], main=0),

    # ---- 口罩 ----
    "F02FM01": dict(category="mask", subcategory="平面口罩",
                    series="Disposable Flat Mask", tk_key=None,
                    tier="常规", match=["B","C","D"], main=0),
    "F01KN95": dict(category="mask", subcategory="KN95",
                    series="KN95", tk_key=None,
                    tier="常规", match=["B","C","D"], main=0),
}

# ============================================================
# 主推 SKU PDF 提炼出的痛点 / 达人画像 (按 series/category 共用)
# ============================================================
TIER_INFO = {
    "Cotton Cover Panty Liners": dict(
        pain_points=[
            "日常分泌物、内裤易脏易污染",
            "黄不干净，刺鼻熏人破坏私处弱酸环境",
            "护垫出门携带尴尬",
            "卫生护垫散装易污染细菌滋生",
        ],
        creator_persona_zh="海外垂类女性私密护理 / 经期护理博主 (Women Period Care / Feminine Hygiene KOL)；A 级 30-100 万中腰部、B 级 10-30 万潜力垂类；18-45 岁海外年轻女性、敏感肌、注重私处健康人群",
    ),
    "Cotton Cover Pads": dict(
        pain_points=[
            "经期侧漏社死",
            "厚重闷热不舒适",
            "反渗黏腻",
            "香精刺激敏感肌过敏",
        ],
        creator_persona_zh="海外垂类女性经期护理 KOL；A/B 级中腰部；敏感肌女生、注重私密护理 18-45 岁海外女性",
    ),
    "Ultra Thin Pads": dict(
        pain_points=[
            "经期侧漏社死",
            "厚重闷热反渗",
            "香精刺激过敏",
            "卫生巾闷痒不透气",
        ],
        creator_persona_zh="A 级 30-100 万中腰部、B 级 10-30 万潜力垂类；敏感肌、经期困扰女性",
    ),
    "Pet Diapers (female)": dict(
        pain_points=[
            "母犬发情期乱尿、血迹弄脏地板/沙发/车座",
            "老年犬、术后犬失禁漏尿难清理",
            "普通宠物尿裤厚重闷热不透气",
            "尺码不全，小型/大型犬找不到合适尺寸",
            "腰部弹力勒肚子，狗狗抗拒",
        ],
        creator_persona_zh="海外垂类宠物养狗博主 (Dog Mom / Dog Owner)；A 级 30-100 万中腰部、B 级 10-30 万潜力；母犬饲养者、老年犬/绝育术后铲屎官",
    ),
    "Pet Diapers (male wraps)": dict(
        pain_points=[
            "公犬标记行为弄脏家具",
            "老年犬、病犬术后失禁",
            "普通宠物尿裤厚重不透气",
            "尺码不全",
        ],
        creator_persona_zh="海外宠物养宠博主；A/B 级；公犬铲屎官、失禁漏尿狗狗家长",
    ),
    "Regular Underpads": dict(
        pain_points=[
            "宠物发情期老年犬失禁，弄脏床垫直接清洗困难",
            "普通隔尿垫太薄，尿液直接渗透到底层",
            "材质粗糙硬邦邦，宠物趴着睡觉不舒服",
            "尺寸太小，宠物一动就挪位",
        ],
        creator_persona_zh="S/A 级达人；母犬发情、老年犬失禁、术后康复、家居清洁场景；XS/S/M 全覆盖",
    ),
    "Activated Charcoal Underpads": dict(
        pain_points=["重度异味控制场景、长期使用、强效除臭"],
        creator_persona_zh="A/B 级；注重强效除臭的失禁老人、宠物主人",
    ),
    "Lavender Underpads": dict(
        pain_points=["夜间训练、轻度失禁、清新香味需求"],
        creator_persona_zh="A/B 级；夜间遗尿儿童家庭、轻度失禁老人",
    ),
}

# ============================================================
# 4 份卖点 docx 提炼 (series_key -> selling points / scenarios / target audience)
# series_key 与 SKU_META.series 一致
# ============================================================
SELLING_POINTS = {
    "Cotton Cover Panty Liners": dict(
        sp_en=[
            "Soothe skin with pure cotton, gentle for sensitive skin",
            "Breathable pure cotton, say goodbye to stuffiness and rashes",
            "Fragrance-free pure cotton, gently protect intimate health",
            "Soft pure cotton, fit comfortably without feeling",
            "Natural pure cotton, hypoallergenic and rash-free for peace of mind",
        ],
        sp_zh=["纯棉亲肤温和敏感肌","透气拒绝闷热红痒","无香无刺激保护私处","柔软无感舒适贴合","低敏不过敏放心使用"],
        scenarios_en=["daily commuting","light flow days","pre/post-menstrual","sensitive-skin care"],
        scenarios_zh=["日常通勤","量少日","经期前后","敏感肌护理"],
        ta_en="Women aged 18-45 who prioritize gentle skin feel and ingredient safety, especially suitable for users with sensitive skin, allergy-prone skin, and those seeking a comfortable menstrual experience.",
        ta_zh="18-45 岁注重温和肤感与成分安全的女性，敏感肌、易过敏、追求舒适经期体验",
        proof="Dermatologically tested",
    ),
    "Cotton Cover Pads": dict(
        sp_en=[
            "Pure cotton top sheet, gentle on sensitive skin",
            "100% leak-proof side guards for full protection",
            "Soft, breathable, fragrance-free",
            "Reliable absorbency for medium flow days",
            "Comfortable full coverage without bulk",
        ],
        sp_zh=["纯棉亲肤表层","100% 防漏侧翼","透气无香","中量日可靠吸收","全面覆盖不臃肿"],
        scenarios_en=["medium flow days","daily wear","work and travel"],
        scenarios_zh=["中量日","日常穿戴","工作出行"],
        ta_en="Women aged 18-45 needing reliable medium-flow protection with sensitive-skin friendly cotton.",
        ta_zh="18-45 岁需要中量日可靠防护、敏感肌友好的女性",
        proof="Dermatologically tested",
    ),
    "Ultra Thin Pads": dict(
        sp_en=[
            "Close-fitting, comfy without stuffiness",
            "Perforated mesh, instant absorption, no leakage for heavy flow",
            "Quick-dry, long-lasting dryness without stickiness",
            "Breathable, say goodbye to stuffiness and rashes",
            "Ultra-thin & odor-locking, all-day freshness",
        ],
        sp_zh=["贴身舒适不闷热","穿孔表层瞬吸不漏","快干长效不黏腻","透气拒绝闷热","超薄锁味全日清新"],
        scenarios_en=["daily commuting","sports & fitness","summer outings"],
        scenarios_zh=["日常通勤","运动健身","夏日出行"],
        ta_en="Women aged 18-45 seeking lightweight, all-day dryness, and ingredient safety; ideal for daily commuting, sports, and summer wear.",
        ta_zh="18-45 岁追求轻薄无感、全日干爽、成分安全；适合通勤、运动、夏日出行",
        proof="Dermatologically tested",
    ),
    "Period Underwear": dict(
        sp_en=[
            "Stretchy snug fit adapts to more body shapes",
            "3D leak protection for peaceful nights",
            "Moisture-locking comfort reduces sticky feeling",
            "Cost-effective for repeat overnight use",
            "Soft skin-friendly feel for better sleep",
        ],
        sp_zh=["弹力裤型适配更多身形","3D 防护夜间更安心","锁水干爽减少黏腻","日常夜用更具性价比","柔软亲肤更好睡"],
        scenarios_en=["overnight sleep","heavier-night use","travel stays","postpartum backup"],
        scenarios_zh=["夜间安睡","重流量夜用","旅行住宿","产后备用"],
        ta_en="Women needing dependable overnight backup, travel convenience, or postpartum-friendly peace of mind.",
        ta_zh="夜间量大女性、旅行用户、产后恢复备用",
        proof="FDA registered",
    ),
    "Micro Panty Liners": dict(
        sp_en=[
            "Fragrance-free & hypoallergenic, ultra comfy for sensitive skin",
            "Skin-friendly cotton top sheet, gentle and non-irritating",
            "Breathable for all-day fresh feeling",
            "Invisible & sensation-free for daily comfort",
            "Portable for safe daily backup",
        ],
        sp_zh=["无香低敏敏感肌友好","纯棉亲肤温和不刺激","透气全天清新","隐形无感日常舒适","便携安心日用"],
        scenarios_en=["daily discharge care","pre/post-menstrual","light protection"],
        scenarios_zh=["日常分泌物护理","经期前后","轻量防护"],
        ta_en="Women 18-45 seeking invisible daily care; sensitive-skin friendly.",
        ta_zh="18-45 岁注重日常隐形护理、敏感肌友好",
        proof="Dermatologically tested",
    ),
    # ---- 成人 ----
    "Adult Diaper with Tabs": dict(
        sp_en=[
            "Breathable back sheet for long-wear comfort",
            "Super absorbent core plus leak guards for day and night security",
            "Secure-fit tabs and larger hip coverage",
            "Odor control for discreet care",
        ],
        sp_zh=["透气面层适合长时穿戴","强吸收芯体配合腿围防护","搭扣调节大臀围覆盖","除味保持体面感"],
        scenarios_en=["overnight care","post-surgery recovery","limited-mobility support","extended day-to-night wear"],
        scenarios_zh=["夜间护理","术后恢复","行动不便护理","长时穿戴"],
        ta_en="Caregivers, adults with moderate-to-heavy incontinence, and post-surgery home-care families.",
        ta_zh="老人照护者、失禁用户本人、术后恢复家庭",
        proof="Dermatologically tested; FDA registered",
    ),
    "Disposable Briefs": dict(
        sp_en=[
            "Pull-up underwear styling for easier wear",
            "Maximum absorbency for longer-lasting dryness",
            "Odor control for fresher all-day feel",
            "Stretch waistband for comfort and movement",
            "Disposable hygiene & convenience",
        ],
        sp_zh=["内裤式穿脱更方便","高吸收芯体长效干爽","除味控制更体面","弹力腰围活动自在","一次性使用更卫生"],
        scenarios_en=["daily wear","self-managed routines","post-surgery recovery","overnight backup"],
        scenarios_zh=["白天日常穿戴","行动自理","术后恢复","夜间备用"],
        ta_en="Adults managing incontinence directly, seniors, and post-surgery home-care users.",
        ta_zh="失禁用户本人、长辈日常穿戴、术后恢复家庭",
        proof="Dermatologically tested; FDA registered",
    ),
    "Women Incontinence Pads": dict(
        sp_en=[
            "Skin-friendly & breathable for constant freshness",
            "Instant absorption & lock for long dryness",
            "Upgraded leak guard with side barriers",
            "Discreet shape inside regular underwear",
        ],
        sp_zh=["亲肤透气全天清新","瞬吸锁水长效干爽","升级侧翼防漏","内裤内隐形不显形"],
        scenarios_en=["postpartum care","light incontinence","daily protection"],
        scenarios_zh=["产后护理","轻度失禁","日常防护"],
        ta_en="Postpartum women, seniors, and mild incontinence users.",
        ta_zh="产后妈妈、长辈、轻度失禁女性",
        proof="Dermatologically tested",
    ),
    "Maxi Postpartum Pads": dict(
        sp_en=[
            "Gentle on sensitive skin",
            "Fragrance-free & dye-free recovery care",
            "Easy-tear release paper, secure stay-put fit",
            "Breathable fabric for all-day comfort",
        ],
        sp_zh=["敏感肌友好更温和","无香无染料更安心","易撕离型纸贴合不移位","透气面料长时间舒适"],
        scenarios_en=["postpartum recovery","hospital bag prep","nighttime support","post-surgery recovery"],
        scenarios_zh=["产后恢复","医院待产包","夜间护理","术后恢复"],
        ta_en="Postpartum moms, hospital-bag planners, and gentle post-op care users.",
        ta_zh="产后妈妈、待产包准备家庭、术后恢复用户",
        proof="Dermatologically tested; FDA registered",
    ),
    "Calabash-Shaped Postpartum Pads": dict(
        sp_en=[
            "Calabash shape secures fit during recovery",
            "Gentle care for sensitive postpartum skin",
            "Reliable overnight protection",
            "Breathable cotton-feel cover",
        ],
        sp_zh=["葫芦版型贴合恢复期","温和呵护敏感肌","可靠夜间防护","纯棉感透气面层"],
        scenarios_en=["postpartum overnight","recovery routines","hospital bag"],
        scenarios_zh=["产后夜用","恢复期日常","待产包"],
        ta_en="Postpartum women prioritizing shaped fit and gentle overnight care.",
        ta_zh="注重贴合度的产后女性、夜间护理用户",
        proof="Dermatologically tested",
    ),
    "Incontinence Pads for Men": dict(
        sp_en=[
            "Instant absorption keeps surface dry",
            "Odor control for confidence",
            "Breathable & skin-friendly long-wear comfort",
            "Adhesive backing keeps pad in place",
        ],
        sp_zh=["瞬吸锁水保持干爽","除味控制更有信心","透气亲肤长时间舒适","背胶固定不移位"],
        scenarios_en=["daily commuting","light protection","post-surgery recovery","extended seated wear"],
        scenarios_zh=["日常通勤","轻度防护","术后恢复","久坐场景"],
        ta_en="Senior men, mild incontinence users, and post-op recovery users.",
        ta_zh="轻度失禁男性、长辈男士、术后恢复",
        proof="Dermatologically tested; FDA registered",
    ),

    # ---- 母婴 ----
    "Ultra Thin Baby Diapers": dict(
        sp_en=[
            "Instant absorption with no backflow",
            "Breathable surface dissipates heat",
            "Soft & comfortable fit for active babies",
            "Trusted overnight dryness",
        ],
        sp_zh=["瞬吸锁水不反渗整夜安睡","透气面层速排闷热","柔软贴合活泼宝宝","值得信任的夜间干爽"],
        scenarios_en=["daytime wear","overnight sleep","active play"],
        scenarios_zh=["日间穿戴","夜间安睡","活泼玩耍"],
        ta_en="Parents seeking thin, breathable, all-day comfort diapers.",
        ta_zh="追求轻薄透气全天舒适纸尿裤的家长",
        proof="Dermatologically tested",
    ),
    "Disposable Nursing Pads": dict(
        sp_en=[
            "Strong absorbency keeps clothes stain-free",
            "Ultra-thin invisible design",
            "Skin-friendly cotton-feel cover",
            "Individually wrapped for on-the-go",
        ],
        sp_zh=["强吸不漏奶不湿衣","超薄隐形无感","亲肤纯棉感面层","独立包装便携"],
        scenarios_en=["breastfeeding moms","work and travel","postpartum routine"],
        scenarios_zh=["哺乳期妈妈","工作出行","产后日常"],
        ta_en="Breastfeeding moms wanting discreet daily protection.",
        ta_zh="哺乳期妈妈、追求隐形防护",
        proof="Dermatologically tested",
    ),

    # ---- 宠物 ----
    "Training Pads": dict(
        sp_en=[
            "Leak-proof backing keeps floors dry and clean",
            "Extra-long absorption locks in liquid with no rewet",
            "Skin-friendly guards for comfortable contact",
            "Improved backing doubles leak protection",
        ],
        sp_zh=["防漏底层地板干爽","超长吸收不反渗","亲肤护边温和接触","加强底层双重防漏"],
        scenarios_en=["potty training","indoor protection","temporary care"],
        scenarios_zh=["宠物如厕训练","室内防护","临时看护"],
        ta_en="Pet families, especially small/young dog owners.",
        ta_zh="养宠家庭，特别是小型犬/幼犬铲屎官",
        proof="",
    ),
    "Pet Diapers (female)": dict(
        sp_en=[
            "High-efficiency absorption locks in liquid",
            "Breathable structure reduces stuffiness",
            "Powerful odor lock keeps environment fresh",
            "Secure fit without restricting movement",
        ],
        sp_zh=["高效吸收锁水","透气结构减少闷热","强力锁臭","贴合不束缚活动"],
        scenarios_en=["heat cycle","incontinence care","travel","post-surgery"],
        scenarios_zh=["发情期管理","失禁护理","旅行使用","术后护理"],
        ta_en="Cat/dog families, esp. young, senior, or post-op pets.",
        ta_zh="养猫狗人群，尤其幼宠/老年宠/术后护理",
        proof="",
    ),
    "Pet Diapers (male wraps)": dict(
        sp_en=[
            "Quickly absorbs liquids, dry and comfortable",
            "Soft & gentle on the abdomen",
            "Wrap-around design prevents side leakage",
            "Lightweight & non-restrictive",
        ],
        sp_zh=["快速吸收干爽舒适","腹部柔软不摩擦","环绕设计防侧漏","轻薄不束缚"],
        scenarios_en=["indoor marking","post-surgery","travel"],
        scenarios_zh=["居家防尿","标记行为管理","术后护理","出行使用"],
        ta_en="Male-dog families focused on cleanliness and home hygiene.",
        ta_zh="养公犬家庭，关注清洁与居家卫生",
        proof="",
    ),

    # ---- 家居护理 ----
    "Regular Underpads": dict(
        sp_en=[
            "Leak-proof backing prevents leaks and protects surfaces",
            "Super long absorption delivers extended dryness",
            "Skin-friendly guards for gentle protection",
            "Dryness and odor control maintains fresh areas",
        ],
        sp_zh=["底层防漏保护表面","超长吸收延长干爽","亲肤护边温和保护","防潮锁臭保持清新"],
        scenarios_en=["bed protection","wheelchair","pet training","incontinence"],
        scenarios_zh=["床上防漏","椅子/轮椅垫","宠物训练","日常失禁管理"],
        ta_en="Senior incontinence users, pet trainers, and bed-bound users.",
        ta_zh="失禁老人、宠物训练、卧床人士、注重家居清洁的家庭",
        proof="",
    ),
    "Activated Charcoal Underpads": dict(
        sp_en=[
            "Activated charcoal layer absorbs and neutralizes odors",
            "Leak-proof backing protects surfaces",
            "Skin-friendly guards for gentle protection",
            "Strong dryness and odor control",
        ],
        sp_zh=["活性炭层中和异味","底层防漏保护表面","亲肤护边温和保护","强效防潮锁臭"],
        scenarios_en=["heavy odor control","long-term use","medical settings"],
        scenarios_zh=["重度异味控制","长期使用","医院/家庭护理"],
        ta_en="Caregivers handling heavy incontinence or odor-sensitive environments.",
        ta_zh="注重强效除臭的失禁老人、宠物主人、对异味敏感的护理家庭",
        proof="",
    ),
    "Lavender Underpads": dict(
        sp_en=[
            "Calming lavender scent neutralizes unpleasant odors",
            "Leak-proof backing & skin-friendly guards",
            "Ultra-absorbent core for extended dryness",
            "Soft, breathable top layer",
        ],
        sp_zh=["薰衣草香中和异味","防漏底层亲肤护边","超吸收芯体延长干爽","柔软透气表层"],
        scenarios_en=["nighttime training","light incontinence","pet training","travel"],
        scenarios_zh=["儿童夜间训练","老人轻度失禁","宠物训练","旅行外出"],
        ta_en="Families with bed-wetting kids, mild senior incontinence, lavender-scent lovers.",
        ta_zh="夜间遗尿儿童家庭、轻度失禁老人、清新香味偏好",
        proof="",
    ),
}

# ============================================================
# TK_Content workbench 词库 (用于 AI 文案 / 创意切入 / 安全镜头)
# 摘自 D:\\Backup\\Downloads\\TK_Content_Workbench_Delivery\\app\\index.html
# ============================================================
TK_CONTENT_EXTRA = {
    "cotton_cover_panty_liners": dict(
        vocabulary_en=["cotton cover","fragrance-free","invisible care","sensitive-skin friendly"],
        creative_angles_en=["gentle daily freshness","invisible all-day backup"],
        safe_scenes_en=["liner texture close-up","tucked into regular underwear"],
        focus_zh="主打纯棉无香、温和敏感肌、隐形日用",
    ),
    "cotton_cover_pads": dict(
        vocabulary_en=["100% leak-proof","cotton cover","medium flow protection"],
        creative_angles_en=["leak protection without bulk","gentle cotton feel"],
        safe_scenes_en=["pad cross-section","wing close-up"],
        focus_zh="主打防漏侧翼 + 纯棉亲肤",
    ),
    "ultra_thin_pads": dict(
        vocabulary_en=["instant absorption","ultra-thin","odor-locking","quick dry"],
        creative_angles_en=["barely-there feel","sports-day reliability"],
        safe_scenes_en=["thickness comparison","mesh top close-up"],
        focus_zh="超薄无感 + 瞬吸防漏",
    ),
    "period_underwear": dict(
        vocabulary_en=["overnight period pants","pull-on night protection","peaceful sleep","stretch fit"],
        creative_angles_en=["peaceful sleep without stress","pull-on convenience"],
        safe_scenes_en=["bedtime setup","waistband stretch","travel kit"],
        focus_zh="夜用安心 + 穿脱方便 + 性价比",
    ),
    "adult_tabs": dict(
        vocabulary_en=["discreet protection","secure-fit tabs","overnight confidence","caregiver-friendly"],
        creative_angles_en=["dignity-first caregiving","overnight peace of mind"],
        safe_scenes_en=["packaging close-up","tab adjustment","bedtime routine"],
        focus_zh="护理体面感 + 换护便利 + 夜间安心",
    ),
    "disposable_briefs": dict(
        vocabulary_en=["pull-up protection","underwear-style fit","easy self-wear","day-to-night absorbency"],
        creative_angles_en=["looks like regular underwear","easier self-managed care"],
        safe_scenes_en=["pull-up silhouette","waistband stretch close-up"],
        focus_zh="像内裤一样好穿脱，自理感和体面感",
    ),
    "women_pads": dict(
        vocabulary_en=["bladder control","light leakage","discreet protection"],
        creative_angles_en=["confidence in regular underwear"],
        safe_scenes_en=["pad inside folded underwear"],
        focus_zh="女性轻度失禁 + 隐形防护",
    ),
    "postpartum_pads": dict(
        vocabulary_en=["postpartum recovery","hospital-bag essential","gentle recovery comfort","fragrance-free care"],
        creative_angles_en=["softer recovery routines","hospital-bag readiness"],
        safe_scenes_en=["hospital bag flat lay","recovery basket bedside"],
        focus_zh="产后恢复语境，温和、安全、待产包准备感",
    ),
    "calabash_postpartum_pads": dict(
        vocabulary_en=["calabash shape","secure fit","gentle postpartum care"],
        creative_angles_en=["shape that hugs recovery","overnight peace"],
        safe_scenes_en=["pad shape close-up","bedside basket"],
        focus_zh="贴合恢复期 + 温和夜用",
    ),
    "men_pads": dict(
        vocabulary_en=["discreet daily backup","adhesive backing","stay-in-place protection"],
        creative_angles_en=["invisible confidence","stays put inside regular underwear"],
        safe_scenes_en=["pad profile close-up","placement inside folded underwear"],
        focus_zh="男士专用、贴身不移位、低存在感",
    ),
    "ultra_thin_baby_diapers": dict(
        vocabulary_en=["ultra-thin","instant absorption","breathable","peaceful sleep"],
        creative_angles_en=["all-day comfort","peaceful nights"],
        safe_scenes_en=["diaper texture close-up","baby movement"],
        focus_zh="轻薄透气 + 整夜干爽",
    ),
    "nursing_pads": dict(
        vocabulary_en=["nursing pads","invisible","stain-free","portable"],
        creative_angles_en=["confident breastfeeding"],
        safe_scenes_en=["pad inside bra","individual wrap close-up"],
        focus_zh="哺乳期隐形防护 + 独立包装便携",
    ),
    "training_pads": dict(
        vocabulary_en=["puppy pads","leak-proof","indoor potty training"],
        creative_angles_en=["clean floors during training"],
        safe_scenes_en=["pad layered on floor","puppy training scene"],
        focus_zh="室内训练 + 地板防护",
    ),
    "disposable_diapers": dict(
        vocabulary_en=["pet diapers","heat cycle","odor lock","secure fit"],
        creative_angles_en=["clean home during heat","worry-free travel"],
        safe_scenes_en=["dog wearing diaper","tail-hole close-up"],
        focus_zh="发情期/失禁护理 + 防漏锁臭",
    ),
    "disposable_male_wraps": dict(
        vocabulary_en=["male wrap","marking control","wrap-around design"],
        creative_angles_en=["clean home from marking","comfortable wrap"],
        safe_scenes_en=["wrap fit close-up","dog activity"],
        focus_zh="居家清洁 + 标记行为管理 + 腹部贴合",
    ),
    "regular_underpads": dict(
        vocabulary_en=["disposable underpads","leak-proof","surface protection","multiple sizes"],
        creative_angles_en=["protect every surface","multi-scenario versatility"],
        safe_scenes_en=["bed flat lay","wheelchair seat"],
        focus_zh="床椅表面防护 + 多场景使用",
    ),
    "activated_charcoal_underpads": dict(
        vocabulary_en=["activated charcoal","odor neutralizer","heavy-incontinence ready"],
        creative_angles_en=["strong odor control"],
        safe_scenes_en=["dark pad surface close-up","packaging shot"],
        focus_zh="活性炭除味 + 重度场景",
    ),
    "lavender_underpads": dict(
        vocabulary_en=["lavender scent","calming aroma","odor-neutralizing"],
        creative_angles_en=["gentle scent + strong protection"],
        safe_scenes_en=["pad with lavender props","bedside setup"],
        focus_zh="薰衣草香 + 防护与气味双体验",
    ),
}


# ============================================================
# Helpers
# ============================================================
def upsert_categories(con: sqlite3.Connection) -> dict[str, int]:
    cur = con.cursor()
    code_to_id = {}
    for sort_idx, (code, zh, en) in enumerate(CATEGORIES):
        cur.execute(
            "INSERT INTO category(code,name_zh,name_en,sort_order) VALUES(?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name_zh=excluded.name_zh, name_en=excluded.name_en",
            (code, zh, en, sort_idx),
        )
        cur.execute("SELECT id FROM category WHERE code=?", (code,))
        code_to_id[code] = cur.fetchone()[0]
    con.commit()
    return code_to_id


def parse_price_table() -> list[dict]:
    """Return one dict per SKU row from the price xlsx."""
    df = pd.read_excel(PRICE_XLSX, sheet_name=0, header=None)
    df = df.fillna("")
    out = []
    last_name_block = ""
    for i in range(1, len(df)):
        row = [str(x).strip() for x in df.iloc[i].tolist()]
        # cols: 序号,产品名称,货号,规格,片PCS/包BAG,包BAG/件,图片,Tiktok,Temu,eBay,eBay本土,独立站
        if not row[0] or row[0].lower() == "no.":
            continue
        sku_code = row[2]
        # SKU codes are uppercase alphanumeric (e.g. BU02P155); skip header echoes
        if not sku_code or not re.fullmatch(r"[A-Z0-9]{4,}", sku_code):
            continue
        # 序号 should be numeric
        try:
            seq = int(re.sub(r"\D", "", row[0]) or "0")
            if seq <= 0:
                continue
        except ValueError:
            continue
        name_block = row[1] if row[1] else last_name_block
        last_name_block = name_block
        # name_block: "Cotton cover Panty liners\nX9纯棉护垫155"
        parts = [p.strip() for p in re.split(r"[\r\n]+", name_block) if p.strip()]
        name_en = parts[0] if parts else ""
        name_zh = parts[1] if len(parts) >= 2 else ""

        def num(x: str) -> float | None:
            x = x.strip()
            if not x:
                return None
            try:
                return float(x)
            except ValueError:
                return None

        out.append(dict(
            sku_code=sku_code,
            name_en=name_en,
            name_zh=name_zh,
            size_label=row[3],
            pcs_per_pack=int(num(row[4])) if num(row[4]) else None,
            packs_per_case=int(num(row[5])) if num(row[5]) else None,
            price_tiktok=num(row[7]) if len(row) > 7 else None,
            price_temu=num(row[8]) if len(row) > 8 else None,
            price_ebay=num(row[9]) if len(row) > 9 else None,
            price_ebay_local=num(row[10]) if len(row) > 10 else None,
            price_independent=num(row[11]) if len(row) > 11 else None,
        ))
    return out


def upsert_product(con: sqlite3.Connection, row: dict, cat_id_map: dict[str, int]) -> int:
    sku = row["sku_code"]
    meta = SKU_META.get(sku, {})
    cat_code = meta.get("category", "female_care")
    series = meta.get("series", "")
    sp = SELLING_POINTS.get(series, {})
    tier_info = TIER_INFO.get(series, {})
    tk_extra = TK_CONTENT_EXTRA.get(meta.get("tk_key") or "", {})

    payload = dict(
        sku_code=sku,
        art_no=sku,
        name_en=row.get("name_en") or "",
        name_zh=row.get("name_zh") or "",
        category_id=cat_id_map.get(cat_code),
        subcategory=meta.get("subcategory"),
        series=series,
        size_label=row.get("size_label"),
        pcs_per_pack=row.get("pcs_per_pack"),
        packs_per_case=row.get("packs_per_case"),
        price_tiktok=row.get("price_tiktok"),
        price_temu=row.get("price_temu"),
        price_ebay=row.get("price_ebay"),
        price_ebay_local=row.get("price_ebay_local"),
        price_independent=row.get("price_independent"),
        currency="USD",
        positioning_zh=meta.get("positioning_zh"),
        tier=meta.get("tier"),
        description_en=sp.get("description_en"),
        description_zh=sp.get("description_zh"),
        selling_points_en=json.dumps(sp.get("sp_en", []), ensure_ascii=False),
        selling_points_zh=json.dumps(sp.get("sp_zh", []), ensure_ascii=False),
        pain_points_zh=json.dumps(tier_info.get("pain_points", []), ensure_ascii=False),
        scenarios_en=json.dumps(sp.get("scenarios_en", []), ensure_ascii=False),
        scenarios_zh=json.dumps(sp.get("scenarios_zh", []), ensure_ascii=False),
        target_audience_en=sp.get("ta_en"),
        target_audience_zh=sp.get("ta_zh"),
        proof=sp.get("proof"),
        vocabulary_en=json.dumps(tk_extra.get("vocabulary_en", []), ensure_ascii=False),
        creative_angles_en=json.dumps(tk_extra.get("creative_angles_en", []), ensure_ascii=False),
        safe_scenes_en=json.dumps(tk_extra.get("safe_scenes_en", []), ensure_ascii=False),
        focus_zh=tk_extra.get("focus_zh"),
        tk_content_key=meta.get("tk_key"),
        commission_rate_default=0.05,  # 默认 5%, 可在前台改
        creator_match_levels=json.dumps(meta.get("match", []), ensure_ascii=False),
        creator_persona_zh=tier_info.get("creator_persona_zh"),
        is_main_push=meta.get("main", 0),
        amazon_url=None,  # TODO: 等价格表/补料
        short_url=None,
    )
    cols = list(payload.keys())
    placeholders = ",".join(["?"] * len(cols))
    update_set = ",".join([f"{c}=excluded.{c}" for c in cols if c != "sku_code"])
    sql = (
        f"INSERT INTO product({','.join(cols)}) VALUES({placeholders}) "
        f"ON CONFLICT(sku_code) DO UPDATE SET {update_set}"
    )
    con.execute(sql, [payload[c] for c in cols])
    pid = con.execute("SELECT id FROM product WHERE sku_code=?", (sku,)).fetchone()[0]
    return pid


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    cat_id_map = upsert_categories(con)

    rows = parse_price_table()
    print(f"[import_products] parsed {len(rows)} SKUs from price table")

    inserted = 0
    for row in rows:
        upsert_product(con, row, cat_id_map)
        inserted += 1
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
    n_main = con.execute("SELECT COUNT(*) FROM product WHERE is_main_push=1").fetchone()[0]
    cats = con.execute(
        "SELECT c.code, COUNT(p.id) FROM category c "
        "LEFT JOIN product p ON p.category_id=c.id GROUP BY c.code ORDER BY c.sort_order"
    ).fetchall()
    print(f"[import_products] product rows total={n}  main_push={n_main}")
    for code, cnt in cats:
        print(f"   {code:14s} {cnt}")
    con.close()


if __name__ == "__main__":
    main()
