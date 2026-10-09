#!/usr/bin/env python3
"""
渠道比价记录工具。

用途：把检索到的各渠道价格统一归一化为"到手价"并输出比价表，避免手工
整理价格数据时算错、漏掉叠加优惠、混淆会员价，或忽略长期使用成本。

主要能力：
  - 国家补贴支持（subsidy_rate / subsidy_amount，区分"已含补贴"与"可叠加补贴"）
  - 国补额度**按品类封顶**（数码每件 ≤500 元、电脑每件 ≤1500 元），
    超封顶自动截断；单价越过品类门槛时给出"该品类通常不参与"的告警
  - 重复计算国补预警（商家标"补贴价"通常已含国补，不能再叠）
  - 四大平台渠道类型识别（京东/淘宝天猫/拼多多/官方商城）
  - 电商专供款标记（exclusive_model）
  - 券的时效标记（coupon_expiry）
  - 会员价区分（会员价与普通价分开呈现，避免拿会员价误导用户）
  - 历史价格标记（标记当前是否处于价格高位）
  - 单次使用成本计算（耗材类品类）
  - 可疑低价预警（明显低于均价时提示排查）
  - 运费险与退货成本提示（风格类商品）

用法：

   # 1. 添加一条价格记录（含国补；金额须是能核对的真实值）
   #    ⚠️ 必须带 --out，否则只把 JSON 打到屏幕、不落盘，示例 2 会报"找不到文件"
   python price_tracker.py add --item "XX 笔记本" --channel "京东自营" --list 6799 --coupon 200 --promo 100 --shipping 0 --note "已核实国补资格" --member-price 5690 --member-type "Plus" --out records.json

   # 2. 生成比价表（从 records.json 读取）
   python price_tracker.py report --input records.json

   # 3. 生成比价表（从 stdin 读取 JSON 数组）
   python price_tracker.py report < prices.json

输入 JSON 格式（records.json）：
[
  {
    "item": "XX 笔记本",
    "channel": "京东自营",
    "list_price": 6799,
    "coupon": 200,
    "promo": 100,
    "shipping": 0,
    "subsidy_rate": 0.15,
    "subsidy_included": true,
    "member_price": 5690,
    "member_type": "Plus",
    "note": "已核实国补资格",
    "date": "2026-09-22",
    "coupon_expiry": "2026-09-30",
    "is_historic_low": false,
    "exclusive_model": false,
    "consumable_cost": 0,
    "consumable_uses": 0,
    "return_shipping": 0,
    "refurb_risk": false
  }
]

字段说明：
  list_price        : 标价（元）
  coupon            : 可叠加优惠券金额（元，填正数）
  promo             : 其他立减/满减（元，填正数）
  shipping          : 运费（元）
  subsidy_amount    : 国补金额（元，填正数；不知道金额可填 0 并用 subsidy_rate）
                      **必须是可以核对出来的真实金额**，不要用「标价 ×15%」硬算——
                      政策有品类封顶（数码 ≤500/件、电脑 ≤1500/件），
                      超出的部分会被自动截断，硬算出来的数字是错的
  subsidy_included  : 该价格是否已含国补（**关键字段**，默认 false）
                      看到商家写「补贴价」就应置 true，否则会重复扣减
  subsidy_rate      : 国补比例（如 0.15；与 subsidy_amount **二选一**，同时填会报错）
  member_price      : 会员到手价（元，可选；**按实付填写，不与 coupon/promo 叠加**）
  member_type       : 会员类型（如 88VIP / Plus，可选）
  note              : 备注（赠品、限时、成色等）
  date              : 记录日期
  coupon_expiry     : 券的截止日期（可选，须为 YYYY-MM-DD 或 YYYY/MM/DD）
  is_historic_low   : 是否处于历史低位（可选，bool）
  exclusive_model   : 是否电商专供款（可选，bool）
  consumable_cost   : 单次耗材成本（元，可选，用于耗材类品类）
  consumable_uses   : 每消耗一次用多少（可选，与 cost 配合算单次成本）
  return_shipping   : 退货需自担运费（元，可选，风格类商品参考）
  refurb_risk       : 是否疑似翻新/水货/无保修（可选，bool）

到手价 = list_price - coupon - promo + shipping [- subsidy_amount（若未含补贴）]
"""

import argparse
import json
import os
import statistics
import sys
from datetime import date, datetime


def _f(v, default=0.0):
    """安全转 float。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# 2026 年国补品类参数（依据国家发展改革委、财政部 2026 年
# "大规模设备更新和消费品以旧换新" 政策）：
#   数码智能产品 = 手机 / 平板 / 智能手表（手环）/ 智能眼镜
#     → 单件售价 ≤ 6000 元才参与；按最终售价 15%；每件 ≤ 500 元
#   家电（含电脑）= 冰箱 / 洗衣机 / 电视 / 空调 / 电脑 / 热水器
#     → 须 1 级能效或水效；按最终售价 15%；每件 ≤ 1500 元
# 关键点：**"电脑"走家电通道，不走数码通道**。单价 6799 的笔记本
# 既不在数码通道（超 6000），也不满足家电通道（须 1 级能效且通常
# 有独立价格门槛），因此该价位报出国补本身就是可疑的。
SUBSIDY_CATEGORY = {
    # 关键词 -> (品类名, 单件售价上限 or None, 每件补贴上限, 通道)
    "手机":   ("手机",     6000,  500, "数码"),
    "平板":   ("平板",     6000,  500, "数码"),
    "手表":   ("智能手表", 6000,  500, "数码"),
    "手环":   ("智能手环", 6000,  500, "数码"),
    "眼镜":   ("智能眼镜", 6000,  500, "数码"),
    "笔记本": ("电脑",     None, 1500, "家电（须 1 级能效）"),
    "电脑":   ("电脑",     None, 1500, "家电（须 1 级能效）"),
    "台式":   ("电脑",     None, 1500, "家电（须 1 级能效）"),
    "显示器": ("电脑",     None, 1500, "家电（须 1 级能效）"),
    "冰箱":   ("冰箱",     None, 1500, "家电（须 1 级能效）"),
    "洗衣机": ("洗衣机",   None, 1500, "家电（须 1 级能效）"),
    "电视":   ("电视",     None, 1500, "家电（须 1 级能效）"),
    "空调":   ("空调",     None, 1500, "家电（须 1 级能效）"),
    "热水器": ("热水器",   None, 1500, "家电（须 1 级能效）"),
}
SUBSIDY_DEFAULT_CAP = 500.0

# 明确**不在** 2026 年国补目录内的高频品类。
# 这类商品如果被填了国补金额，几乎一定是算错了或被人误导了。
#
# ⚠️ 组合词（"手机壳"）必须显式列出：只有「耳机」「支架」这类词时，
# "手机壳" 会先命中品类表的 "手机" → 被算出 500 元国补，这是错的。
SUBSIDY_EXCLUDED = (
    # 数码外设与小配件
    "耳机", "键盘", "鼠标", "音箱", "音响", "充电", "数据线", "支架",
    "保护壳", "手机壳", "保护套", "内胆包", "贴膜", "钢化膜", "保护膜",
    "表带", "挂绳", "底座", "转接", "电源线", "延长线", "遥控器", "电池",
    "鼠标垫", "键盘膜", "散热器", "配件", "零件", "耗材", "维修", "延保", "换屏",
    # 家电的"同名周边物"（含家电品类词，但本身不是那件家电）
    "电视柜", "电视盒子", "机顶盒", "电视罩", "空调被", "空调罩",
    "冰箱贴", "洗衣机槽", "洗衣机罩", "热水器管", "电脑桌", "电脑包",
    # 完全不在补贴目录的品类
    "路由", "扫地机", "净化器", "加湿器", "风扇",
    "食品", "化妆品", "护肤", "保健品", "药", "服", "鞋", "包",
    "玩具", "家具", "床", "椅", "灯", "书", "猫粮", "狗粮",
)

# 配件类词尾。用于兜住带后缀修饰的写法（"手机壳 磨砂黑"、"平板保护套"）。
# 只匹配**词尾**，因此不会误伤 "27 寸带鱼屏显示器"（词尾是"器"）或
# "空调柜机"（词尾是"机"）这类真家电。
SUBSIDY_ACCESSORY_SUFFIX = (
    "壳", "套", "膜", "盒", "绳", "带", "贴", "罩", "垫", "架",
    "线", "头", "芯", "网", "剂", "包", "袋",
)


def _is_accessory(it: str) -> bool:
    """是否为"看起来像补贴品类、实际是配件"的商品名。

    三层判定，任一命中即视为配件：

    1. **已知配件词**（子串）——"手机壳""保护套""电视柜"
    2. **词尾是配件名词**——"数据线""滤芯"这类不带品类词的名字
    3. **品类词后面紧邻配件名词**——兜住"眼镜盒 便携""手机壳 磨砂黑"
       这类"配件名 + 修饰语"的写法

    第 3 层是关键：只靠第 2 层时，"眼镜盒 便携"因为词尾是"携"而漏网，
    会被当成"智能眼镜"算出 500 元国补。
    """
    if any(kw in it for kw in SUBSIDY_EXCLUDED):
        return True
    if it.endswith(SUBSIDY_ACCESSORY_SUFFIX):
        return True
    for kw in SUBSIDY_CATEGORY:
        idx = it.find(kw)
        while idx != -1:
            after = idx + len(kw)
            if after < len(it) and it[after] in SUBSIDY_ACCESSORY_SUFFIX:
                return True
            idx = it.find(kw, idx + 1)
    return False


def subsidy_rule(item: str):
    """按商品名推断适用哪个国补通道。

    返回 (品类, 售价上限 or None, 补贴上限, 通道名)。
    未识别时返回通道名 "未识别"，调用方据此提示"请自行核实品类"。

    优先级：**排除表 > 品类表**。耳机、充电头、手机壳这类配件虽然属于
    "数码"大类，但**不在** 2026 年国补目录内（目录只列了手机/平板/手表/
    眼镜四类数码 + 六类家电），所以必须先判排除，否则"蓝牙耳机"会被误判
    成有 500 元补贴，"手机壳"会被当成"手机"。
    """
    it = (item or "").strip()
    if _is_accessory(it):
        return ("未识别", None, SUBSIDY_DEFAULT_CAP, "未识别")
    for kw, rule in SUBSIDY_CATEGORY.items():
        if kw in it:
            return rule
    return ("未识别", None, SUBSIDY_DEFAULT_CAP, "未识别")


def compute_subsidy(rec: dict) -> float:
    """计算国补金额。支持直接给金额或用比例算。

    口径说明：
    - 国补按「商品成交价」计算，**不含运费**（运费不属于补贴范围）。
      因此这里刻意不减 shipping —— 与 compute_final_price 中
      "先加运费再减补贴" 的顺序配合，两者口径一致。
    - 如果同时填了 subsidy_amount 和 subsidy_rate，**报错**而不是
      静默取其一。两者并存几乎总是填错，静默取其一会让用户以为
      另一个也生效了（实测 rate=0.15 + amount=1 时只剩 1 元）。
    - 若比例算出的金额超过政策封顶，**按封顶截断**，而不是原样输出
      一个高于政策的数字（这是「不编造优惠信息」红线的直接要求）。
    """
    amt = _f(rec.get("subsidy_amount"))
    rate = _f(rec.get("subsidy_rate"))
    if amt > 0 and rate > 0:
        raise ValueError(
            "subsidy_amount 与 subsidy_rate 只能填一个，"
            "两者同时填写会无法判断以哪个为准（当前：金额 %.2f、比例 %s）"
            % (amt, rate)
        )
    _, _, cap, _ = subsidy_rule(rec.get("item"))
    if amt > 0:
        return round(min(amt, cap), 2)
    if rate > 0:
        base = _f(rec.get("list_price")) - _f(rec.get("coupon")) - _f(rec.get("promo"))
        return round(min(max(base, 0) * rate, cap), 2)
    return 0.0


def compute_final_price(rec: dict) -> float:
    """计算到手价。已含补贴的价不再二次扣减。"""
    total = (
        _f(rec.get("list_price"))
        - _f(rec.get("coupon"))
        - _f(rec.get("promo"))
        + _f(rec.get("shipping"))
    )
    if not rec.get("subsidy_included"):
        total -= compute_subsidy(rec)
    return round(max(total, 0.0), 2)


def compute_member_price(rec: dict):
    """计算会员到手价。未提供则返回 None。"""
    if rec.get("member_price") in (None, "", 0, "0"):
        return None
    return round(_f(rec.get("member_price")) + _f(rec.get("shipping")), 2)


def compute_unit_cost(rec: dict):
    """计算单次使用成本。不适用则返回 None。"""
    cost = _f(rec.get("consumable_cost"))
    uses = _f(rec.get("consumable_uses"))
    if cost <= 0 or uses <= 0:
        return None
    return round(cost / uses, 3)


def normalize_channel_type(channel: str) -> str:
    """按渠道名推断售后主体类型。

    判定纪律：**否定词优先于肯定词**。
    "官网 XX 第三方店" 这种名字里同时含"官网"和"第三方"，
    语义主体是"第三方店"（挂靠在官网上的第三方卖家或干脆是蹭名），
    绝不能因为出现"官网"二字就判成品牌官方——那会让告警反着来。
    因此先扫负面词（第三方/专营/专卖/个人/店），命中即判第三方，
    再扫正面词（自营 / 官方旗舰 / 品牌官网）。
    """
    c = channel or ""
    if not c.strip():
        return "第三方店铺"

    # 第一优先级：明确的负面信号 -> 第三方
    NEGATIVE = ("第三方", "专营", "专卖", "个人店", "小店", "代购", "全球购",
                "海外", "水货", "官换", "翻新", "二手", "黄牛")
    if any(w in c for w in NEGATIVE):
        return "第三方店铺"

    # 第二优先级：平台自营
    if "自营" in c:
        return "平台自营"

    # 第三优先级：品牌官方（官网/官方旗舰店，而非泛化的"商城"）
    if "官方旗舰" in c or "官旗" in c or "旗舰店" in c:
        return "品牌官方"
    if "官网" in c or "官方商城" in c or "官方店" in c or "官方网站" in c:
        return "品牌官方"

    if "百亿补贴" in c:
        return "平台补贴"

    return "第三方店铺"


def normalize_platform(channel: str) -> str:
    """按渠道名推断所属电商平台。"""
    c = channel or ""
    if "京东" in c:
        return "京东"
    if "天猫" in c or "淘宝" in c:
        return "淘宝/天猫"
    if "拼多多" in c or "多多" in c:
        return "拼多多"
    if "官网" in c or "官方商城" in c:
        return "官方商城"
    if "抖音" in c:
        return "抖音"
    if "唯品会" in c:
        return "唯品会"
    return "其他"

def build_records(args) -> list:
    """从命令行参数构建单条记录。"""
    return [{
        "item": args.item,
        "channel": args.channel,
        "list_price": args.list,
        "coupon": args.coupon,
        "promo": args.promo,
        "shipping": args.shipping,
        "subsidy_amount": args.subsidy_amount,
        "subsidy_rate": args.subsidy_rate,
        "subsidy_included": args.subsidy_included,
        "member_price": args.member_price,
        "member_type": args.member_type or "",
        "note": args.note or "",
        "date": args.date or date.today().isoformat(),
        "coupon_expiry": args.coupon_expiry or "",
        "is_historic_low": args.historic_low,
        "exclusive_model": args.exclusive_model,
        "consumable_cost": args.consumable_cost,
        "consumable_uses": args.consumable_uses,
        "return_shipping": args.return_shipping,
        "refurb_risk": args.refurb_risk,
    }]


def load_records(input_path: str) -> list:
    """从文件或 stdin 读取记录。出错时抛出 ValueError（由 main 转成友好提示）。"""
    if input_path:
        if os.path.isdir(input_path):
            raise ValueError("%s 是目录，不是文件" % input_path)
        if not os.path.exists(input_path):
            raise ValueError("找不到文件：%s" % input_path)
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise ValueError("读取 %s 失败：%s" % (input_path, e))
    else:
        raw = sys.stdin.read()

    raw = raw.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("JSON 解析失败（第 %d 行第 %d 列）：%s"
                         % (e.lineno, e.colno, e.msg))

    # 允许 {} / null 等非数组输入，统一转成空列表
    if data is None:
        return []
    if isinstance(data, dict):
        if not data:
            return []
        raise ValueError("顶层应是数组 [ {...}, {...} ]，收到的是对象")
    if not isinstance(data, list):
        raise ValueError("顶层应是数组，收到的是 %s" % type(data).__name__)

    # 逐条校验必需字段，报错时指明第几条
    # 字段名必须与 build_records() 写出的保持一致（list_price 不是 list）
    REQUIRED = ("item", "channel", "list_price")
    for i, rec in enumerate(data, 1):
        if not isinstance(rec, dict):
            raise ValueError("第 %d 条不是对象，而是 %s"
                             % (i, type(rec).__name__))
        missing = [k for k in REQUIRED if k not in rec]
        if missing:
            raise ValueError("第 %d 条缺少必需字段：%s"
                             % (i, "、".join(missing)))
    return data


def _coupon_expired(expiry: str):
    """判断券是否已过期。

    返回 True（已过期）/ False（未过期）/ None（**日期格式无法识别**）。
    不能把解析失败静默当成"未过期"——否则 9999-99-99 这种脏数据会被
    原样输出成"券截至 9999-99-99，下单前复核"，用户以为券还有效。
    """
    if not expiry:
        return False
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(expiry, fmt).date() < date.today()
        except ValueError:
            continue
    return None


def render_report(records: list, show_member: bool = True) -> str:
    """生成比价报告。"""
    if not records:
        return "无比价数据。"

    by_item = {}
    for rec in records:
        by_item.setdefault(rec.get("item", "未命名商品"), []).append(rec)

    lines = ["# 渠道比价表", "", f"生成时间：{date.today().isoformat()}", ""]

    for item, recs in by_item.items():
        enriched = []
        for rec in recs:
            enriched.append({
                **rec,
                "final_price": compute_final_price(rec),
                "subsidy": compute_subsidy(rec),
                "member_final": compute_member_price(rec),
                "unit_cost": compute_unit_cost(rec),
                "channel_type": normalize_channel_type(rec.get("channel", "")),
                "platform": normalize_platform(rec.get("channel", "")),
            })
        enriched.sort(key=lambda r: r["final_price"])

        lines.append(f"## {item}")
        lines.append("")

        has_member = show_member and any(r["member_final"] is not None for r in enriched)
        has_unit = any(r["unit_cost"] is not None for r in enriched)
        has_subsidy = any(r["subsidy"] > 0 for r in enriched)

        header = "| 渠道 | 平台 | 售后主体 | 标价 | 券 | 立减 | 运费"
        sep = "|---|---|---|---|---|---|---"
        if has_subsidy:
            header += " | 国补"
            sep += "|---"
        header += " | **到手价**"
        sep += "|---"
        if has_member:
            header += " | 会员价"
            sep += "|---"
        if has_unit:
            header += " | 单次成本"
            sep += "|---"
        header += " | 备注 |"
        sep += "|---|"
        lines.append(header)
        lines.append(sep)

        for r in enriched:
            row = (
                f"| {r.get('channel', '-')} "
                f"| {r['platform']} "
                f"| {r['channel_type']} "
                f"| ¥{_f(r.get('list_price')):.0f} "
                f"| -¥{_f(r.get('coupon')):.0f} "
                f"| -¥{_f(r.get('promo')):.0f} "
                f"| +¥{_f(r.get('shipping')):.0f}"
            )
            if has_subsidy:
                if r["subsidy"] > 0:
                    tag = "已含" if r.get("subsidy_included") else "可叠"
                    row += f" | ¥{r['subsidy']:.0f}（{tag}）"
                else:
                    row += " | -"
            row += f" | **¥{r['final_price']:.0f}**"
            if has_member:
                mp = r["member_final"]
                mt = r.get("member_type") or "会员"
                row += f" | {'' if mp is None else f'¥{mp:.0f}（{mt}）'}"
            if has_unit:
                uc = r["unit_cost"]
                row += f" | {'' if uc is None else f'¥{uc}'}"
            note = r.get("note") or "-"
            if r.get("refurb_risk"):
                note = f"⚠️ 疑似翻新/无保修；{note}"
            if r.get("exclusive_model"):
                note = f"⚠️ 电商专供款；{note}"
            row += f" | {note} |"
            lines.append(row)

        lines.append("")

        cheapest = enriched[0]
        priciest = enriched[-1]
        spread = round(priciest["final_price"] - cheapest["final_price"], 2)

        lines.append(f"- **最低到手价**：¥{cheapest['final_price']:.0f}（{cheapest.get('channel')}，{cheapest['channel_type']}）")
        if spread > 0:
            lines.append(f"- **价差**：¥{spread:.0f}（相对最高价 {priciest.get('channel')}）")

        # 标价陷阱
        by_list = sorted(enriched, key=lambda r: _f(r.get("list_price")))
        if by_list[0]["channel"] != cheapest["channel"]:
            lines.append(
                f"- ⚠️ **标价陷阱**：标价最低的是 {by_list[0].get('channel')}"
                f"（¥{_f(by_list[0].get('list_price')):.0f}），但到手价不是最低。比价必须看到手价。"
            )

        # 国补重复计算预警
        included = [r for r in enriched if r.get("subsidy_included") and r["subsidy"] > 0]
        if included:
            names = "、".join(r.get("channel", "-") for r in included)
            lines.append(
                f"- 🏛️ **国补已含**：{names} 标注的价格已包含国补，**不要在此之上再算 15%** "
                f"（这是最常见的算错方式）。"
            )

        # 国补政策合规检查 —— 这是「不编造优惠信息」红线的机械兜底。
        # 实测教训：曾用「6799 笔记本 + 975 元国补」当过示例，而 975 是
        # (6799-300)×15% 算出来的，远超数码类每件 500 元的法定封顶，
        # 且 6799 本身已越过数码通道 6000 元的售价门槛。写进技能的值
        # 必须能被政策核对，所以这里把两条硬约束做成显式告警。
        for r in enriched:
            cat, price_cap, cap, tunnel = subsidy_rule(r.get("item"))
            sub = r["subsidy"]
            if sub <= 0:
                continue
            base = _f(r.get("list_price"))
            if cat == "未识别":
                lines.append(
                    f"- ❓ **国补品类未识别**：`{r.get('item')}` 不在技能内置的"
                    f"国补品类表里。请自行核实它是否在目录内，再决定要不要写国补金额。"
                )
            elif price_cap is not None and base > price_cap:
                lines.append(
                    f"- 🚫 **国补品类存疑**：{cat}类国补要求**单件售价 ≤ {price_cap} 元**，"
                    f"而 {r.get('item')} 标价 ¥{base:.0f} 已超出，通常**不参与**该通道补贴。"
                    f"请核实这条补贴是否真实可拿。"
                )
            elif sub >= cap:
                lines.append(
                    f"- 🏛️ **国补已按封顶截断**：{cat}类（{tunnel}）每件上限 ¥{cap:.0f}，"
                    f"按比例算出的金额更高，已截断到上限。不要用「标价 ×15%」反推能减多少。"
                )
            elif tunnel.startswith("家电"):
                lines.append(
                    f"- 🏛️ **电脑/家电走「1 级能效家电」通道**（每件 ≤{cap:.0f} 元），"
                    f"不是数码通道。需确认该型号有 1 级能效标识，否则拿不到补贴。"
                )

        # 会员价差异提示
        # 只有在「会员价确实比该渠道自己的普通价更低」时才提，避免把
        # 「会员价 vs 自己的标价」当成渠道间对比 —— 那没有决策价值。
        # 口径提醒：member_price 按**实付**填写，不与 coupon/promo 叠加，
        # 所以这个价差和"券能省多少"不能相加，措辞里要说清楚。
        member_recs = [r for r in enriched
                       if r["member_final"] is not None
                       and r["member_final"] < r["final_price"]]
        if member_recs:
            best_member = min(member_recs, key=lambda r: r["member_final"])
            gap = round(best_member["final_price"] - best_member["member_final"], 2)
            hint = ""
            if _f(best_member.get("coupon")) > 0 or _f(best_member.get("promo")) > 0:
                hint = "（会员价按实付填写，已含渠道优惠，勿与券/立减再加一次）"
            lines.append(
                f"- 💳 **会员价更低**：{best_member.get('channel')} 会员价 ¥{best_member['member_final']:.0f}"
                f"（{best_member.get('member_type') or '会员'}），比该渠道普通价便宜 ¥{gap:.0f}{hint}。"
                f"注意区分「你能拿到的价」和「会员能拿到的价」。"
            )

        # 售后主体提示
        if cheapest["channel_type"] == "第三方店铺":
            lines.append(
                "- ⚠️ **售后提示**：最低价来自第三方店铺，售后责任主体非平台/品牌官方，"
                "价差不大的情况下建议优先自营或官旗。"
            )

        # 平台分布提示
        platforms = {r["platform"] for r in enriched}
        if len(platforms) >= 3:
            lines.append(
                f"- 🛒 **平台覆盖**：已比较 {len(platforms)} 个平台（{'、'.join(sorted(platforms))}）。"
            )
        elif len(platforms) == 2:
            missing = {"京东", "淘宝/天猫", "拼多多", "官方商城"} - platforms
            if missing:
                lines.append(
                    f"- 🛒 **建议补充**：还没查 {'、'.join(sorted(missing))}，价格可能更优或更差，值得一并核对。"
                )

        # 券时效提示
        expiring = [r for r in enriched if r.get("coupon_expiry")]
        for r in expiring:
            expired = _coupon_expired(r["coupon_expiry"])
            if expired is None:
                lines.append(
                    f"- ⚠️ **券期无法识别**：{r.get('channel')} 的券日期 `{r['coupon_expiry']}` "
                    f"不是 `YYYY-MM-DD` 或 `YYYY/MM/DD` 格式，未能判断是否过期，请人工复核。"
                )
            elif expired:
                lines.append(
                    f"- ⏰ **券已过期**：{r.get('channel')} 的券截止 {r['coupon_expiry']}，需重新核价。"
                )
            else:
                lines.append(
                    f"- ⏰ **券有效期**：{r.get('channel')} 的券截至 {r['coupon_expiry']}，下单前复核。"
                )

        # 历史价位提示
        for r in enriched:
            if r.get("is_historic_low"):
                lines.append(f"- 🟢 **{r.get('channel')} 处于历史低位**，是入手时机。")
                break

        # 可疑低价预警
        prices = [r["final_price"] for r in enriched if r["final_price"] > 0]
        if len(prices) >= 3:
            median = statistics.median(prices)
            if median > 0 and cheapest["final_price"] < median * 0.6:
                lines.append(
                    f"- 🚨 **可疑低价**：{cheapest.get('channel')} 的 ¥{cheapest['final_price']:.0f} "
                    f"显著低于中位数 ¥{median:.0f}（低于 60%）。请排查是否为翻新、水货、"
                    f"无保修、参数不符的山寨同款，或非全新商品。"
                )

        # 单次使用成本提示（耗材类）
        unit_recs = [r for r in enriched if r["unit_cost"] is not None]
        if len(unit_recs) >= 2:
            best_unit = min(unit_recs, key=lambda r: r["unit_cost"])
            lines.append(
                f"- 🧾 **单次使用成本最低**：{best_unit.get('channel')}（¥{best_unit['unit_cost']}/次）。"
                f"耗材类商品看长期成本，不看机身价格。"
            )

        # 退货成本提示（风格类）
        ret_recs = [r for r in enriched if _f(r.get("return_shipping")) > 0]
        if ret_recs:
            rs = ret_recs[0]
            lines.append(
                f"- 📦 **退货成本**：{rs.get('channel')} 退货需自担运费 ¥{_f(rs.get('return_shipping')):.0f}。"
                f"风格类商品退货概率高，这部分要计入实际成本。"
            )

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("提示：以上为检索时点价格，实际价格波动频繁，下单前请复核。")
    lines.append("国补注意：2026 年分数码（手机/平板/手表/眼镜，≤6000 元、每件≤500 元）")
    lines.append("与家电（含电脑，须 1 级能效、每件≤1500 元）两条通道，均按 15% 计，")
    lines.append("超 6000 元整单失去资格，封顶按件算——不要用「标价 ×15%」反推。")
    lines.append("商家标注的「补贴价」通常已含国补，不要重复计算。")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="price_tracker.py",
        description="渠道到手价比对：自动识别标价陷阱、会员价差异、可疑低价、单次使用成本、国补后价。",
        epilog="例：price_tracker.py report --input records.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="{add,report}")

    add_p = sub.add_parser("add", help="添加一条价格记录")
    add_p.add_argument("--item", required=True)
    add_p.add_argument("--channel", required=True)
    add_p.add_argument("--list", type=float, required=True)
    add_p.add_argument("--coupon", type=float, default=0)
    add_p.add_argument("--promo", type=float, default=0)
    add_p.add_argument("--shipping", type=float, default=0)
    add_p.add_argument("--subsidy-amount", type=float, default=0)
    add_p.add_argument("--subsidy-rate", type=float, default=0)
    add_p.add_argument("--subsidy-included", action="store_true",
                       help="该价格是否已含国补")
    add_p.add_argument("--member-price", type=float, default=0)
    add_p.add_argument("--member-type", default="")
    add_p.add_argument("--note", default="")
    add_p.add_argument("--date", default="")
    add_p.add_argument("--coupon-expiry", default="")
    add_p.add_argument("--historic-low", action="store_true")
    add_p.add_argument("--exclusive-model", action="store_true")
    add_p.add_argument("--consumable-cost", type=float, default=0)
    add_p.add_argument("--consumable-uses", type=float, default=0)
    add_p.add_argument("--return-shipping", type=float, default=0)
    add_p.add_argument("--refurb-risk", action="store_true")
    add_p.add_argument("--out", default="")

    rep_p = sub.add_parser("report", help="生成比价表")
    rep_p.add_argument("--input", default="")
    rep_p.add_argument("--no-member", action="store_true", help="不显示会员价列")

    args = parser.parse_args()

    # argparse 在「自定义 Action 抛 ArgumentError」等情况下会把异常继续
    # 向上冒泡，用户会看到英文 traceback。这里统一兜住，转成中文提示 +
    # 退出码 2（与参数错误一致），兑现文档里"不抛栈"的承诺。
    try:
        if args.command == "add":
            records = build_records(args)
        elif args.command == "report":
            records = load_records(args.input)
    except ValueError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2

    if args.command == "add":
        if args.out:
            if os.path.isdir(args.out):
                print("错误：--out 指向的是目录，请给出文件名（如 %s）"
                      % os.path.join(args.out, "records.json"), file=sys.stderr)
                return 2
            existing = []
            try:
                with open(args.out, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except FileNotFoundError:
                existing = []
            except json.JSONDecodeError:
                print("错误：%s 已存在但不是合法 JSON，为免覆盖已中止。"
                      "请先备份或删除该文件。" % args.out, file=sys.stderr)
                return 2
            except OSError as e:
                print("错误：读取 %s 失败：%s" % (args.out, e), file=sys.stderr)
                return 2
            if not isinstance(existing, list):
                print("错误：%s 的内容不是数组，为免写坏已中止。" % args.out,
                      file=sys.stderr)
                return 2
            existing.extend(records)
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
            except OSError as e:
                print("错误：写入 %s 失败：%s" % (args.out, e), file=sys.stderr)
                return 2
            print(f"已写入 {args.out}（现有 {len(existing)} 条记录）")
        else:
            print(json.dumps(records, ensure_ascii=False, indent=2))

    elif args.command == "report":
        try:
            print(render_report(records, show_member=not args.no_member))
        except ValueError as e:
            # compute_subsidy 在渲染期才被调用（amount/rate 冲突检测），
            # 必须在这里也兜一层，否则会漏出英文 traceback。
            print("错误：%s" % e, file=sys.stderr)
            return 2

    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
