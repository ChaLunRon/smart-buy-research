#!/usr/bin/env python3
"""
渠道比价记录工具。

用途：把检索到的各渠道价格统一归一化为"到手价"并输出比价表，
避免手工整理价格数据时算错或漏掉叠加优惠。

用法：

  # 1. 添加一条价格记录
  python price_tracker.py add \
      --item "XX 耳机" --channel "京东自营" --list 999 --coupon 100 \
      --promo 50 --shipping 0 --note "plus会员券"

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
    "note": "plus会员券",
    "date": "2026-09-22"
  }
]

字段说明：
  list_price : 标价（元）
  coupon     : 可叠加优惠券金额（元，填正数）
  promo      : 其他立减/满减（元，填正数）
  shipping   : 运费（元）
  note       : 备注（会员条件、赠品、限时等）

到手价 = list_price - coupon - promo + shipping
"""

import argparse
import json
import sys
from datetime import date


def compute_final_price(rec: dict) -> float:
    """计算到手价。"""
    list_price = float(rec.get("list_price") or 0)
    coupon = float(rec.get("coupon") or 0)
    promo = float(rec.get("promo") or 0)
    shipping = float(rec.get("shipping") or 0)
    return round(list_price - coupon - promo + shipping, 2)


def normalize_channel_type(channel: str) -> str:
    """按渠道名推断售后主体类型，用于提示风险。"""
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
        "note": args.note or "",
        "date": args.date or date.today().isoformat(),
    }]


def load_records(input_path: str) -> list:
    """从文件或 stdin 读取记录。"""
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)
    data = sys.stdin.read().strip()
    if not data:
        return []
    return json.loads(data)


def render_report(records: list) -> str:
    """生成比价报告。"""
    if not records:
        return "无比价数据。"

    # 按商品分组
    by_item = {}
    for rec in records:
        by_item.setdefault(rec.get("item", "未命名商品"), []).append(rec)

    lines = []
    lines.append("# 渠道比价表")
    lines.append("")
    lines.append(f"生成时间：{date.today().isoformat()}")
    lines.append("")

    for item, recs in by_item.items():
        # 计算到手价
        enriched = []
        for rec in recs:
            final = compute_final_price(rec)
            enriched.append({
                **rec,
                "final_price": final,
                "channel_type": normalize_channel_type(rec.get("channel", "")),
            })

        enriched.sort(key=lambda r: r["final_price"])

        lines.append(f"## {item}")
        lines.append("")
        lines.append("| 渠道 | 渠道类型 | 标价 | 券 | 立减 | 运费 | **到手价** | 备注 |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for r in enriched:
            lines.append(
                f"| {r.get('channel', '-')} "
                f"| {r['channel_type']} "
                f"| ¥{r.get('list_price', 0)} "
                f"| -¥{r.get('coupon', 0)} "
                f"| -¥{r.get('promo', 0)} "
                f"| +¥{r.get('shipping', 0)} "
                f"| **¥{r['final_price']}** "
                f"| {r.get('note', '') or '-'} |"
            )

        lines.append("")

        # 分析
        cheapest = enriched[0]
        most_expensive = enriched[-1]
        spread = round(most_expensive["final_price"] - cheapest["final_price"], 2)

        lines.append(f"- **最低到手价**：¥{cheapest['final_price']}（{cheapest.get('channel')}，{cheapest['channel_type']}）")
        lines.append(f"- **价差**：¥{spread}（相对最高价 {most_expensive.get('channel')}）")

        # 标价最低但到手价不是最低的情况，特别提示
        by_list = sorted(enriched, key=lambda r: float(r.get("list_price") or 0))
        if by_list[0]["channel"] != cheapest["channel"]:
            lines.append(
                f"- ⚠️ **标价陷阱**：标价最低的是 {by_list[0].get('channel')}（¥{by_list[0].get('list_price')}），"
                f"但到手价不是最低。比价必须看到手价。"
            )

        # 售后主体提示
        types = {r["channel_type"] for r in enriched}
        if "第三方店铺" in types and cheapest["channel_type"] == "第三方店铺":
            lines.append(
                f"- ⚠️ **售后提示**：最低价来自第三方店铺，售后责任主体非平台/品牌官方，"
                f"价差不大的情况下建议优先自营或官旗。"
            )

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("提示：以上为检索时点价格，实际价格波动频繁，下单前请复核。")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="渠道比价记录工具")
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="添加一条价格记录")
    add_p.add_argument("--item", required=True, help="商品名称/型号")
    add_p.add_argument("--channel", required=True, help="渠道名称")
    add_p.add_argument("--list", type=float, required=True, help="标价")
    add_p.add_argument("--coupon", type=float, default=0, help="优惠券金额")
    add_p.add_argument("--promo", type=float, default=0, help="其他立减金额")
    add_p.add_argument("--shipping", type=float, default=0, help="运费")
    add_p.add_argument("--note", default="", help="备注")
    add_p.add_argument("--date", default="", help="日期 YYYY-MM-DD")
    add_p.add_argument("--out", default="", help="追加写入的文件路径")

    rep_p = sub.add_parser("report", help="生成比价表")
    rep_p.add_argument("--input", default="", help="记录 JSON 文件，省略则从 stdin 读取")

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
        records = load_records(args.input)
        print(render_report(records))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
