#!/usr/bin/env python3
"""
渠道比价记录工具 v2。

用途：把检索到的各渠道价格统一归一化为"到手价"并输出比价表，避免手工
整理价格数据时算错、漏掉叠加优惠、混淆会员价，或忽略长期使用成本。

v2 相比 v1 新增：
  - 会员价区分（会员价与普通价分开呈现，避免拿会员价误导用户）
  - 历史价格标记（标记当前是否处于价格高位）
  - 单次使用成本计算（耗材类品类）
  - 可疑低价预警（明显低于均价时提示排查）
  - 运费险与退货成本提示（风格类商品）

用法：

  # 1. 添加一条价格记录
  python price_tracker.py add \\
      --item "XX 耳机" --channel "京东自营" --list 999 --coupon 100 \\
      --promo 50 --shipping 0 --note "plus会员券" \\
      --member-price 849 --member-type "Plus"

  # 2. 生成比价表（从 records.json 读取）
  python price_tracker.py report --input records.json

  # 3. 生成比价表（从 stdin 读取 JSON 数组）
  cat prices.json | python price_tracker.py report

输入 JSON 格式（records.json）：
[
  {
    "item": "XX 耳机",
    "channel": "京东自营",
    "list_price": 999,
    "coupon": 100,
    "promo": 50,
    "shipping": 0,
    "member_price": 849,
    "member_type": "Plus",
    "note": "plus会员券",
    "date": "2026-09-22",
    "is_historic_low": false,
    "consumable_cost": 0,
    "consumable_uses": 0,
    "return_shipping": 0,
    "refurb_risk": false
  }
]

字段说明：
  list_price       : 标价（元）
  coupon           : 可叠加优惠券金额（元，填正数）
  promo            : 其他立减/满减（元，填正数）
  shipping         : 运费（元）
  member_price     : 会员到手价（元，可选；若不填则会员价不单独展示）
  member_type      : 会员类型（如 88VIP / Plus，可选）
  note             : 备注（赠品、限时、成色等）
  date             : 记录日期
  is_historic_low  : 是否处于历史低位（可选，bool）
  consumable_cost  : 单次耗材成本（元，可选，用于耗材类品类）
  consumable_uses  : 每消耗一次用多少（可选，与 cost 配合算单次成本）
  return_shipping  : 退货需自担运费（元，可选，风格类商品参考）
  refurb_risk      : 是否疑似翻新/水货/无保修（可选，bool）

到手价 = list_price - coupon - promo + shipping
"""

import argparse
import json
import statistics
import sys
from datetime import date


def _f(v, default=0.0):
    """安全转 float。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_final_price(rec: dict) -> float:
    """计算到手价。"""
    return round(
        _f(rec.get("list_price"))
        - _f(rec.get("coupon"))
        - _f(rec.get("promo"))
        + _f(rec.get("shipping")),
        2,
    )


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
    """按渠道名推断售后主体类型。"""
    c = channel or ""
    if "自营" in c:
        return "平台自营"
    if "官旗" in c or "官方旗舰" in c:
        return "品牌官方"
    if "百亿补贴" in c:
        return "平台补贴"
    if "专营" in c or "专卖" in c:
        return "第三方授权"
    return "第三方店铺"


def build_records(args) -> list:
    """从命令行参数构建单条记录。"""
    return [{
        "item": args.item,
        "channel": args.channel,
        "list_price": args.list,
        "coupon": args.coupon,
        "promo": args.promo,
        "shipping": args.shipping,
        "member_price": args.member_price,
        "member_type": args.member_type or "",
        "note": args.note or "",
        "date": args.date or date.today().isoformat(),
        "is_historic_low": args.historic_low,
        "consumable_cost": args.consumable_cost,
        "consumable_uses": args.consumable_uses,
        "return_shipping": args.return_shipping,
        "refurb_risk": args.refurb_risk,
    }]


def load_records(input_path: str) -> list:
    """从文件或 stdin 读取记录。"""
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)
    data = sys.stdin.read().strip()
    return json.loads(data) if data else []


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
                "member_final": compute_member_price(rec),
                "unit_cost": compute_unit_cost(rec),
                "channel_type": normalize_channel_type(rec.get("channel", "")),
            })
        enriched.sort(key=lambda r: r["final_price"])

        lines.append(f"## {item}")
        lines.append("")

        has_member = show_member and any(r["member_final"] is not None for r in enriched)
        has_unit = any(r["unit_cost"] is not None for r in enriched)

        header = "| 渠道 | 渠道类型 | 标价 | 券 | 立减 | 运费 | **到手价**"
        sep = "|---|---|---|---|---|---|---"
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
                f"| {r['channel_type']} "
                f"| ¥{_f(r.get('list_price')):.0f} "
                f"| -¥{_f(r.get('coupon')):.0f} "
                f"| -¥{_f(r.get('promo')):.0f} "
                f"| +¥{_f(r.get('shipping')):.0f} "
                f"| **¥{r['final_price']:.0f}**"
            )
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
            row += f" | {note} |"
            lines.append(row)

        lines.append("")

        cheapest = enriched[0]
        priciest = enriched[-1]
        spread = round(priciest["final_price"] - cheapest["final_price"], 2)

        lines.append(f"- **最低到手价**：¥{cheapest['final_price']:.0f}（{cheapest.get('channel')}，{cheapest['channel_type']}）")
        lines.append(f"- **价差**：¥{spread:.0f}（相对最高价 {priciest.get('channel')}）")

        # 标价陷阱
        by_list = sorted(enriched, key=lambda r: _f(r.get("list_price")))
        if by_list[0]["channel"] != cheapest["channel"]:
            lines.append(
                f"- ⚠️ **标价陷阱**：标价最低的是 {by_list[0].get('channel')}"
                f"（¥{_f(by_list[0].get('list_price')):.0f}），但到手价不是最低。比价必须看到手价。"
            )

        # 会员价差异提示
        member_recs = [r for r in enriched if r["member_final"] is not None]
        if member_recs:
            best_member = min(member_recs, key=lambda r: r["member_final"])
            gap = round(cheapest["final_price"] - best_member["member_final"], 2)
            if gap > 0:
                lines.append(
                    f"- 💳 **会员价更低**：{best_member.get('channel')} 会员价 ¥{best_member['member_final']:.0f}"
                    f"（{best_member.get('member_type') or '会员'}），比普通最低价便宜 ¥{gap:.0f}。"
                    f"注意区分「你能拿到的价」和「会员能拿到的价」。"
                )

        # 售后主体提示
        if cheapest["channel_type"] == "第三方店铺":
            lines.append(
                "- ⚠️ **售后提示**：最低价来自第三方店铺，售后责任主体非平台/品牌官方，"
                "价差不大的情况下建议优先自营或官旗。"
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
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="渠道比价记录工具 v2")
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="添加一条价格记录")
    add_p.add_argument("--item", required=True)
    add_p.add_argument("--channel", required=True)
    add_p.add_argument("--list", type=float, required=True)
    add_p.add_argument("--coupon", type=float, default=0)
    add_p.add_argument("--promo", type=float, default=0)
    add_p.add_argument("--shipping", type=float, default=0)
    add_p.add_argument("--member-price", type=float, default=0)
    add_p.add_argument("--member-type", default="")
    add_p.add_argument("--note", default="")
    add_p.add_argument("--date", default="")
    add_p.add_argument("--historic-low", action="store_true")
    add_p.add_argument("--consumable-cost", type=float, default=0)
    add_p.add_argument("--consumable-uses", type=float, default=0)
    add_p.add_argument("--return-shipping", type=float, default=0)
    add_p.add_argument("--refurb-risk", action="store_true")
    add_p.add_argument("--out", default="")

    rep_p = sub.add_parser("report", help="生成比价表")
    rep_p.add_argument("--input", default="")
    rep_p.add_argument("--no-member", action="store_true", help="不显示会员价列")

    args = parser.parse_args()

    if args.command == "add":
        records = build_records(args)
        if args.out:
            existing = []
            try:
                with open(args.out, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                existing = []
            existing.extend(records)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"已写入 {args.out}（现有 {len(existing)} 条记录）")
        else:
            print(json.dumps(records, ensure_ascii=False, indent=2))

    elif args.command == "report":
        print(render_report(load_records(args.input), show_member=not args.no_member))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
