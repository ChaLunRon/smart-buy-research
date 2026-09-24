#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
price_tracker.py 的单元测试与 CLI 集成测试。

运行：
    python -m unittest discover -s tests -v
或：
    python tests/test_price_tracker.py

重点覆盖三类曾经的**真实缺陷**，防止回归：
  1. 国补越界（用「标价 ×15%」硬算，超出政策按件封顶）
  2. 渠道类型判反（`官网 XX 第三方店` 被判成品牌官方）
  3. 异常路径漏出英文 traceback（参数错误、文件不存在、JSON 畸形）
"""

import io
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "price_tracker.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pt = _load("price_tracker_under_test", SCRIPT)


def _run(args, stdin=None):
    """以子进程方式跑 CLI，返回 (returncode, stdout, stderr)。"""
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args,
        input=stdin, capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


class TestSubsidyRule(unittest.TestCase):
    """国补品类识别：必须是「排除表优先于品类表」。"""

    def test_digital_category(self):
        for item, cat in (("iPhone 16 手机", "手机"),
                          ("iPad 平板电脑", "平板"),
                          ("智能手表 A", "智能手表"),
                          ("智能手环 B", "智能手环"),
                          ("智能眼镜 C", "智能眼镜")):
            cat_name, threshold, cap, tunnel = pt.subsidy_rule(item)
            self.assertEqual(cat_name, cat, item)
            self.assertEqual(threshold, 6000, item)
            self.assertEqual(cap, 500, item)
            self.assertEqual(tunnel, "数码", item)

    def test_appliance_category(self):
        for item, cat in (("联想笔记本", "电脑"),
                          ("台式机主机", "电脑"),
                          ("27 寸显示器", "电脑"),
                          ("双门冰箱", "冰箱"),
                          ("滚筒洗衣机", "洗衣机"),
                          ("55 寸电视", "电视"),
                          ("变频空调", "空调"),
                          ("燃气热水器", "热水器")):
            cat_name, threshold, cap, tunnel = pt.subsidy_rule(item)
            self.assertEqual(cat_name, cat, item)
            self.assertIsNone(threshold, item)
            self.assertEqual(cap, 1500, item)
            self.assertIn("家电", tunnel, item)

    def test_laptop_goes_through_appliance_tunnel(self):
        """笔记本必须走家电通道（1500 封顶），不能走数码通道（500）。"""
        _, _, cap, tunnel = pt.subsidy_rule("ThinkBook 14+ 笔记本")
        self.assertEqual(cap, 1500)
        self.assertIn("家电", tunnel)

    def test_excluded_beats_category(self):
        """配件不得因含品类词而被判成可补贴。

        「手机壳」必须靠排除表拦下 —— 否则它会先命中品类表的「手机」，
        被算出一笔 500 元的国补。这是本测试存在的主要理由。
        """
        for item in ("蓝牙耳机", "机械键盘", "无线鼠标", "蓝牙音箱",
                     "手机壳", "平板保护套", "钢化贴膜", "路由器",
                     "扫地机器人", "猫粮 5kg", "运动鞋", "双肩包", "台灯",
                     "保健品", "电视柜", "冰箱贴", "空调被", "电脑桌"):
            cat_name, _, _, tunnel = pt.subsidy_rule(item)
            self.assertEqual(cat_name, "未识别", item)
            self.assertEqual(tunnel, "未识别", item)

    def test_accessory_suffix_with_trailing_text(self):
        """配件后跟修饰语时，仍要靠词尾规则拦下。"""
        for item in ("手机壳 磨砂黑", "平板保护套 磁吸款", "笔记本电脑内胆包",
                     "热水器滤芯", "洗衣机槽清洁剂", "眼镜盒 便携"):
            cat_name, _, _, _ = pt.subsidy_rule(item)
            self.assertEqual(cat_name, "未识别", item)

    def test_accessory_rule_does_not_break_real_products(self):
        """词尾规则不能误伤真家电：词尾是「器」「机」等多品类结尾。"""
        for item, cat in (("27 寸带鱼屏显示器", "电脑"),
                          ("立式空调柜机", "空调"),
                          ("滚筒洗衣机 10kg", "洗衣机"),
                          ("智能手表 血氧版", "智能手表")):
            cat_name, _, _, _ = pt.subsidy_rule(item)
            self.assertEqual(cat_name, cat, item)

    def test_unknown_item(self):
        cat_name, _, _, tunnel = pt.subsidy_rule("某种没见过的商品")
        self.assertEqual(cat_name, "未识别")
        self.assertEqual(tunnel, "未识别")

    def test_empty_item_does_not_crash(self):
        for item in (None, "", "   "):
            cat_name, _, cap, tunnel = pt.subsidy_rule(item)
            self.assertEqual(cat_name, "未识别")
            self.assertEqual(cap, pt.SUBSIDY_DEFAULT_CAP)


class TestComputeSubsidy(unittest.TestCase):
    def test_appliance_cap_is_1500(self):
        """家电通道封顶 1500：12000×15%=1800，必须截断到 1500。"""
        rec = {"item": "XX 笔记本", "list_price": 12000, "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_subsidy(rec), 1500.0)

    def test_laptop_under_cap_is_prorated_and_flagged(self):
        """6799 的笔记本：974.85 未超 1500 封顶 → 不截断，但报告要提示
        「走 1 级能效家电通道」而非数码通道（数码通道门槛 6000，它已越过）。"""
        rec = {"item": "XX 笔记本", "channel": "京东自营",
               "list_price": 6799, "coupon": 300, "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_subsidy(rec), 974.85)
        out = pt.render_report([rec])
        self.assertIn("1 级能效", out)
        self.assertIn("1500", out)

    def test_digital_cap_is_500(self):
        rec = {"item": "旗舰手机", "list_price": 5999, "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_subsidy(rec), 500.0)

    def test_below_cap_is_prorated(self):
        rec = {"item": "平板电脑", "list_price": 2000, "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_subsidy(rec), 300.0)

    def test_amount_is_also_capped(self):
        rec = {"item": "平板电脑", "list_price": 2000, "subsidy_amount": 900}
        self.assertEqual(pt.compute_subsidy(rec), 500.0)

    def test_amount_and_rate_conflict_raises(self):
        rec = {"item": "平板电脑", "list_price": 2000,
               "subsidy_amount": 1, "subsidy_rate": 0.15}
        with self.assertRaises(ValueError):
            pt.compute_subsidy(rec)

    def test_no_subsidy(self):
        self.assertEqual(pt.compute_subsidy({"item": "平板电脑", "list_price": 2000}), 0.0)

    def test_negative_base_does_not_produce_negative_subsidy(self):
        rec = {"item": "平板电脑", "list_price": 100, "coupon": 500,
               "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_subsidy(rec), 0.0)


class TestComputeFinalPrice(unittest.TestCase):
    def test_coupon_and_promo_are_subtracted(self):
        rec = {"item": "平板电脑", "list_price": 3000, "coupon": 200,
               "promo": 100, "shipping": 0, "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_final_price(rec), 3000 - 200 - 100 - 405)

    def test_shipping_is_added_but_not_subsidised(self):
        """运费要加进到手价，但不参与国补计算基数。"""
        rec = {"item": "平板电脑", "list_price": 3000, "shipping": 20,
               "subsidy_rate": 0.15}
        # 补贴基数是 3000（不含运费）→ 450，到手 3000 + 20 - 450
        self.assertEqual(pt.compute_final_price(rec), 2570.0)

    def test_subsidy_included_is_not_deducted_twice(self):
        rec = {"item": "平板电脑", "list_price": 2550, "subsidy_included": True,
               "subsidy_rate": 0.15}
        self.assertEqual(pt.compute_final_price(rec), 2550.0)

    def test_never_returns_negative(self):
        rec = {"item": "平板电脑", "list_price": 100, "coupon": 999}
        self.assertEqual(pt.compute_final_price(rec), 0.0)


class TestMemberAndUnitCost(unittest.TestCase):
    def test_member_price_none_when_absent(self):
        for v in (None, "", 0, "0"):
            self.assertIsNone(pt.compute_member_price({"member_price": v}))

    def test_member_price_adds_shipping(self):
        self.assertEqual(
            pt.compute_member_price({"member_price": 5690, "shipping": 10}), 5700.0)

    def test_unit_cost(self):
        self.assertAlmostEqual(
            pt.compute_unit_cost({"consumable_cost": 199, "consumable_uses": 100}), 1.99)

    def test_unit_cost_none_when_inapplicable(self):
        self.assertIsNone(pt.compute_unit_cost({"consumable_cost": 0, "consumable_uses": 100}))
        self.assertIsNone(pt.compute_unit_cost({"consumable_cost": 199, "consumable_uses": 0}))


class TestChannelType(unittest.TestCase):
    """否定词必须优先于肯定词，否则售后主体的判断会反着来。"""

    def test_third_party_negative_wins(self):
        for ch in ("官网 XX 第三方店", "淘宝商城第三方", "拼多多商城店",
                   "XX 专营店", "XX 专卖店", "个人店", "海外代购",
                   "全球购", "二手翻新", "官换机"):
            self.assertEqual(pt.normalize_channel_type(ch), "第三方店铺", ch)

    def test_official_website_is_official(self):
        for ch in ("官方网站", "品牌官网", "官方商城", "小米官方旗舰店", "官旗",
                   "Apple 旗舰店"):
            self.assertEqual(pt.normalize_channel_type(ch), "品牌官方", ch)

    def test_platform_self_operated(self):
        self.assertEqual(pt.normalize_channel_type("京东自营"), "平台自营")

    def test_blank_is_third_party(self):
        for ch in (None, "", "   "):
            self.assertEqual(pt.normalize_channel_type(ch), "第三方店铺")

    def test_platform_subsidy(self):
        self.assertEqual(pt.normalize_channel_type("百亿补贴"), "平台补贴")

    def test_platform_detection(self):
        self.assertEqual(pt.normalize_platform("京东自营"), "京东")
        self.assertEqual(pt.normalize_platform("天猫超市"), "淘宝/天猫")
        self.assertEqual(pt.normalize_platform("拼多多百亿补贴"), "拼多多")
        self.assertEqual(pt.normalize_platform("某小店"), "其他")


class TestCouponExpiry(unittest.TestCase):
    def test_expired_and_valid(self):
        self.assertTrue(pt._coupon_expired("2000-01-01"))
        self.assertFalse(pt._coupon_expired("2999-12-31"))

    def test_unparseable_returns_none_not_false(self):
        """脏数据不能被静默当成「未过期」。"""
        for bad in ("9999-99-99", "not-a-date", "2026年9月"):
            self.assertIsNone(pt._coupon_expired(bad), bad)

    def test_empty_is_not_expired(self):
        self.assertFalse(pt._coupon_expired(""))

    def test_slash_format_supported(self):
        self.assertTrue(pt._coupon_expired("2000/01/01"))


class TestRenderReport(unittest.TestCase):
    def test_empty_records(self):
        self.assertEqual(pt.render_report([]), "无比价数据。")

    def test_single_record_has_no_meaningless_spread(self):
        """单条记录不该输出「价差 ¥0」。"""
        out = pt.render_report([{"item": "平板电脑", "channel": "京东自营",
                                 "list_price": 2000}])
        self.assertIn("平板电脑", out)
        self.assertNotIn("价差 ¥0", out)

    def test_over_threshold_warning_for_digital(self):
        out = pt.render_report([{"item": "手机", "channel": "京东自营",
                                 "list_price": 7000, "subsidy_rate": 0.15}])
        self.assertIn("6000", out)

    def test_unknown_category_warning(self):
        out = pt.render_report([{"item": "某个未识别商品", "channel": "京东自营",
                                 "list_price": 2000, "subsidy_amount": 300}])
        self.assertIn("未识别", out)

    def test_amount_rate_conflict_propagates_as_valueerror(self):
        out = None
        try:
            out = pt.render_report([{"item": "平板电脑", "channel": "京东自营",
                                     "list_price": 2000,
                                     "subsidy_amount": 1, "subsidy_rate": 0.15}])
        except ValueError:
            return
        self.fail("amount/rate 冲突应抛 ValueError，实际返回：%r" % (out,))


class TestLoadRecords(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(ValueError):
            pt.load_records(os.path.join(ROOT, "no_such_file_abc.json"))

    def test_directory_rejected(self):
        with self.assertRaises(ValueError):
            pt.load_records(ROOT)

    def test_bad_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("{ not json ")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                pt.load_records(path)
        finally:
            os.unlink(path)

    def test_top_level_must_be_list(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write('{"item": "x"}')
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                pt.load_records(path)
        finally:
            os.unlink(path)

    def test_missing_required_field_names_the_row(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump([{"item": "a", "channel": "b", "list_price": 1},
                       {"item": "c"}], fh)
            path = fh.name
        try:
            with self.assertRaises(ValueError) as ctx:
                pt.load_records(path)
            self.assertIn("第 2 条", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_valid_records_roundtrip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump([{"item": "a", "channel": "b", "list_price": 1}], fh)
            path = fh.name
        try:
            self.assertEqual(len(pt.load_records(path)), 1)
        finally:
            os.unlink(path)

    def test_null_top_level_is_empty(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("null")
            path = fh.name
        try:
            self.assertEqual(pt.load_records(path), [])
        finally:
            os.unlink(path)


class TestCliContract(unittest.TestCase):
    """CLI 层的硬承诺：参数错误给中文提示 + rc=2 + 不打印 traceback。"""

    def assert_clean_failure(self, rc, out, err):
        self.assertEqual(rc, 2, "应返回退出码 2，实际 %s\n%s" % (rc, err))
        self.assertNotIn("Traceback", err, err)
        self.assertNotIn("Traceback", out, out)
        self.assertTrue(err.strip(), "应有中文错误提示")

    def test_help_exits_zero(self):
        rc, out, _ = _run(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("price_tracker", out)

    def test_no_subcommand_prints_help(self):
        rc, out, _ = _run([])
        self.assertEqual(rc, 1)
        self.assertIn("add", out)

    def test_add_missing_required_args(self):
        rc, out, err = _run(["add"])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", err)

    def test_report_missing_file(self):
        rc, out, err = _run(["report", "--input", "no_such_file_abc.json"])
        self.assert_clean_failure(rc, out, err)
        self.assertIn("找不到文件", err)

    def test_report_malformed_json(self):
        rc, out, err = _run(["report"], stdin="{ not json ")
        self.assert_clean_failure(rc, out, err)
        self.assertIn("JSON", err)

    def test_report_missing_field(self):
        rc, out, err = _run(["report"], stdin='[{"item":"a"}]')
        self.assert_clean_failure(rc, out, err)
        self.assertIn("缺少必需字段", err)

    def test_report_amount_rate_conflict_is_caught(self):
        payload = json.dumps([{"item": "平板电脑", "channel": "京东自营",
                               "list_price": 2000, "subsidy_amount": 1,
                               "subsidy_rate": 0.15}], ensure_ascii=False)
        rc, out, err = _run(["report"], stdin=payload)
        self.assert_clean_failure(rc, out, err)
        self.assertIn("只能填一个", err)

    def test_add_then_report_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = os.path.join(tmp, "records.json")
            rc, out, err = _run(["add", "--item", "平板电脑", "--channel", "京东自营",
                                 "--list", "3000", "--subsidy-rate", "0.15",
                                 "--out", rec])
            self.assertEqual(rc, 0, err)
            self.assertTrue(os.path.exists(rec))
            rc, out, err = _run(["report", "--input", rec])
            self.assertEqual(rc, 0, err)
            self.assertIn("平板电脑", out)
            # 3000 - 450 = 2550
            self.assertIn("2550", out)

    def test_add_refuses_to_overwrite_non_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = os.path.join(tmp, "records.json")
            with open(rec, "w", encoding="utf-8") as fh:
                fh.write("not json at all")
            rc, out, err = _run(["add", "--item", "a", "--channel", "b",
                                 "--list", "1", "--out", rec])
            self.assertEqual(rc, 2, err)
            self.assertNotIn("Traceback", err)
            with open(rec, "r", encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "not json at all")

    def test_add_out_pointing_to_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = _run(["add", "--item", "a", "--channel", "b",
                                 "--list", "1", "--out", tmp])
            self.assertEqual(rc, 2, err)
            self.assertIn("目录", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
