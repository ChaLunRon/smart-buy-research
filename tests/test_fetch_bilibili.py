#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_bilibili.py 的单元测试与 CLI 集成测试。

重点覆盖：
  1. WBI 签名实现（`mixin_key` / `sign`）—— 这是评论接口能否走通的唯一关键，
     一旦混淆表写错，签名会静默失效并表现为 -352 报错，很难定位
  2. 参数校验的中文报错与退出码（`--pages` 的边界）
  3. 网络失败必须转成 FetchError 文案，而不是裸抛 traceback

说明：所有涉及网络的用例都通过「离线替换」验证，不在测试里发真实请求，
避免 CI 因网络或平台风控而随机失败。
"""

import importlib.util
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fetch_bilibili.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bb = _load("fetch_bilibili_under_test", SCRIPT)


def _run(args):
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


class TestMixinKey(unittest.TestCase):
    IMG = "7ffe41e2b3c5d6a89c0f1a2b3c4d5e6f"
    SUB = "e1f2a3b4c5d6e7f8091a2b3c4d5e6f70"

    def test_table_is_a_permutation_of_0_to_63(self):
        """混淆表必须正好是 0..63 的一个排列，否则签名结果不可复现。"""
        tab = bb.MIXIN_KEY_ENC_TAB
        self.assertEqual(len(tab), 64)
        self.assertEqual(sorted(tab), list(range(64)))

    def test_real_key_length_is_32_each(self):
        """真实密钥各 32 位，拼起来正好覆盖混淆表的下标范围。"""
        self.assertEqual(len(self.IMG), 32)
        self.assertEqual(len(self.SUB), 32)
        self.assertEqual(max(bb.MIXIN_KEY_ENC_TAB) + 1, len(self.IMG) + len(self.SUB))

    def test_mixin_key_is_32_chars(self):
        self.assertEqual(len(bb.mixin_key(self.IMG, self.SUB)), 32)

    def test_mixin_key_is_deterministic(self):
        self.assertEqual(bb.mixin_key(self.IMG, self.SUB),
                         bb.mixin_key(self.IMG, self.SUB))

    def test_mixin_key_selects_from_source(self):
        """结果的每个字符都必须来自 img_key+sub_key，不能凭空生成。"""
        mk = bb.mixin_key(self.IMG, self.SUB)
        self.assertTrue(all(c in self.IMG + self.SUB for c in mk))

    def test_mixin_key_changes_with_input(self):
        # 注意：混淆表只取前 32 个下标，所以改末尾几位**未必**影响结果。
        # 这里整段换掉 sub_key，确保覆盖到被使用的下标。
        self.assertNotEqual(bb.mixin_key(self.IMG, self.SUB),
                            bb.mixin_key(self.IMG, "0" * 32))
        self.assertNotEqual(bb.mixin_key(self.IMG, self.SUB),
                            bb.mixin_key("0" * 32, self.SUB))

    def test_short_keys_raise_fetcherror_not_indexerror(self):
        """短密钥必须给出中文的 FetchError，而不是英文的 IndexError。"""
        for img, sub in (("abc", "def"), ("", ""), (None, None),
                         (self.IMG[:16], self.SUB[:16])):
            with self.assertRaises(bb.FetchError):
                bb.mixin_key(img, sub)


class TestSign(unittest.TestCase):
    IMG = "7ffe41e2b3c5d6a89c0f1a2b3c4d5e6f"
    SUB = "e1f2a3b4c5d6e7f8091a2b3c4d5e6f70"

    def test_sign_adds_wts_and_w_rid(self):
        out = bb.sign({"foo": 114}, self.IMG, self.SUB)
        self.assertIn("wts", out)
        self.assertIn("w_rid", out)
        self.assertEqual(len(out["w_rid"]), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in out["w_rid"]))

    def test_sign_filters_special_characters(self):
        """B站的 WBI 规则要求剔除 !'()*  这几个字符。"""
        out = bb.sign({"keyword": "a!b'c(d)e*f"}, self.IMG, self.SUB)
        self.assertEqual(out["keyword"], "abcdef")

    def test_sign_does_not_mutate_input(self):
        src = {"foo": 1}
        bb.sign(src, self.IMG, self.SUB)
        self.assertEqual(src, {"foo": 1})

    def test_sign_is_key_order_independent(self):
        """参数字典的插入顺序不应影响签名结果。"""
        a = {"b": 2, "a": 1, "c": 3}
        b = {"c": 3, "a": 1, "b": 2}
        ra = bb.sign(a, self.IMG, self.SUB)
        rb = bb.sign(b, self.IMG, self.SUB)
        ra.pop("wts")
        rb.pop("wts")
        self.assertEqual(ra, rb)

    def test_sign_converts_values_to_string(self):
        out = bb.sign({"pn": 2, "ps": 20}, self.IMG, self.SUB)
        self.assertEqual(out["pn"], "2")
        self.assertEqual(out["ps"], "20")


class TestFetchErrorSurface(unittest.TestCase):
    """网络层失败必须变成 FetchError，不能漏出 URLError / HTTPError。"""

    def test_unreachable_host_raises_fetcherror(self):
        """网络不可达 -> FetchError，且提示里带中文可操作信息。

        **必须用桩替换 `urlopen`，不能真去连 127.0.0.1:9。** 实测踩过：
        如果环境里配了 HTTP 代理，代理会替我们回一个 502（而不是「连接被拒」），
        于是代码走的是 HTTPError 分支而非 URLError 分支 —— 断言结果就取决于环境了，
        同一个仓库在本地绿、在 CI 红。测试不该依赖环境。
        """
        original = bb.urllib.request.urlopen
        bb.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
            bb.urllib.error.URLError("connection refused"))
        try:
            with self.assertRaises(bb.FetchError) as ctx:
                bb._get("http://127.0.0.1:9/definitely-not-listening")
            msg = str(ctx.exception)
            self.assertIn("失败", msg)
            self.assertNotIn("URLError", msg)        # 底层异常名不该漏给用户
            self.assertNotIn("Traceback", msg)
        finally:
            bb.urllib.request.urlopen = original

    def test_non_json_response_raises_fetcherror(self):
        original = bb.urllib.request.urlopen

        class _Resp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return b"<html>not json</html>"

        bb.urllib.request.urlopen = lambda *a, **k: _Resp()
        try:
            with self.assertRaises(bb.FetchError) as ctx:
                bb._get("https://api.bilibili.com/x/test")
            self.assertIn("不是 JSON", str(ctx.exception))
        finally:
            bb.urllib.request.urlopen = original

    def test_http_412_message_distinguishes_signature(self):
        """412 的提示必须点明「不是签名问题」，否则会把人引向错误排查方向。"""
        original = bb.urllib.request.urlopen
        err = bb.urllib.error.HTTPError(
            "https://api.bilibili.com/x/test", 412, "Precondition Failed", {}, None)
        bb.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(err)
        try:
            with self.assertRaises(bb.FetchError) as ctx:
                bb._get("https://api.bilibili.com/x/test")
            msg = str(ctx.exception)
            self.assertIn("412", msg)
            self.assertIn("非签名问题", msg)
        finally:
            bb.urllib.request.urlopen = original


class TestCliContract(unittest.TestCase):
    def test_help_exits_zero(self):
        rc, out, _ = _run(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("fetch_bilibili", out)

    def test_no_subcommand_prints_help(self):
        rc, out, _ = _run([])
        self.assertEqual(rc, 1)
        self.assertIn("comments", out)

    def test_pages_zero_is_rejected_cleanly(self):
        rc, out, err = _run(["comments", "BV1GJ411x7h7", "--pages", "0"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertTrue(err.strip())

    def test_pages_non_integer_is_rejected_cleanly(self):
        rc, out, err = _run(["comments", "BV1GJ411x7h7", "--pages", "abc"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)

    def test_pages_over_limit_is_rejected_cleanly(self):
        rc, out, err = _run(["comments", "BV1GJ411x7h7", "--pages", "99"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("20", err)

    def test_pages_missing_value_is_rejected_cleanly(self):
        rc, out, err = _run(["comments", "BV1GJ411x7h7", "--pages"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)

    def test_invalid_mode_is_rejected(self):
        rc, out, err = _run(["comments", "BV1GJ411x7h7", "--mode", "5"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)

    def test_info_requires_bvid(self):
        rc, out, err = _run(["info"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)

    def test_search_prints_offline_fallback(self):
        """搜索走不了接口，必须给出可用的浏览器路径而不是报错退出。"""
        rc, out, err = _run(["search", "某型号 笔记本 掉线"])
        self.assertEqual(rc, 0, err)
        self.assertIn("bilibili", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
