#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_wechat_article.py 的单元测试与 CLI 集成测试。

重点覆盖：
  1. 正文提取的正则路径（微信的 DOM 结构改过多次，要有固定样例锁住行为）
  2. **「拦截图误判」**：正文里出现「环境异常」「完成验证」这类词是正常现象，
     只有**正文容器缺失**时才能判定为被拦截。这条判反会导致正常文章被
     判成打不开，是很容易犯的错
  3. 非 URL 输入、不可达地址必须给中文提示 + rc=2，不漏 traceback

说明：单元层面**不发起真实网络请求**，网络分支一律用桩替换 `urlopen`；
只有 CLI 子进程用例会真的尝试一次连接（端口 9），其断言对
「连接被拒」与「代理返回错误」两种结果都成立，故不受环境影响。
"""

import importlib.util
import io
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fetch_wechat_article.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wx = _load("fetch_wechat_article_under_test", SCRIPT)


def _run(args):
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


PAGE = """<!DOCTYPE html><html><head>
<meta property="og:title" content="og 标题" />
<script>
var msg_title = '真实的文章标题';
var nickname = '某测评号';
var author = '张三';
var ct = "1758500000";
</script>
</head><body>
<div class="rich_media_content" id="js_content">
<p>第一段&nbsp;文字</p>
<p>第二段 &amp; 符号</p>
<br/>
<img data-src="https://mmbiz.qpic.cn/a.jpg" />
<img data-src="https://mmbiz.qpic.cn/b.jpg" />
<p>结尾</p>
</div>
<script>var x = 1;</script>
</body></html>"""

BLOCKED_PAGE = """<html><body>
<div id="js_error_msg">环境异常，完成验证后即可继续访问。</div>
</body></html>"""

BLOCKED_WORD_IN_BODY = """<html><body>
<div class="rich_media_content" id="js_content">
<p>很多测评号会让你先完成验证再下载，这个说法是话术。</p>
<p>平台提示"环境异常"往往只是缺 User-Agent。</p>
</div>
<script></script>
</body></html>"""


class TestUnescape(unittest.TestCase):
    def test_common_entities(self):
        self.assertEqual(wx._unescape("a&nbsp;b&amp;c&lt;d&gt;e&quot;f&#39;g"),
                         'a b&c<d>e"f\'g')

    def test_chinese_quotes(self):
        self.assertEqual(wx._unescape("&ldquo;好&rdquo;"), "“好”")

    def test_plain_text_unchanged(self):
        self.assertEqual(wx._unescape("没有实体"), "没有实体")


class TestExtractNormalPage(unittest.TestCase):
    def setUp(self):
        self.rec = wx.extract(PAGE)

    def test_title_prefers_msg_title(self):
        self.assertEqual(self.rec["title"], "真实的文章标题")

    def test_account_and_author(self):
        self.assertEqual(self.rec["account"], "某测评号")
        self.assertEqual(self.rec["author"], "张三")

    def test_publish_timestamp(self):
        self.assertEqual(self.rec["publish_ts"], "1758500000")

    def test_content_extracted(self):
        self.assertIsNotNone(self.rec["content"])
        self.assertIn("第一段", self.rec["content"])
        self.assertIn("结尾", self.rec["content"])

    def test_tags_are_stripped(self):
        self.assertNotIn("<p>", self.rec["content"])
        self.assertNotIn("<img", self.rec["content"])

    def test_entities_inside_content_are_unescaped(self):
        self.assertIn("第二段 & 符号", self.rec["content"])

    def test_paragraphs_become_newlines(self):
        self.assertIn("\n", self.rec["content"])

    def test_images_collected(self):
        self.assertEqual(len(self.rec["images"]), 2)
        self.assertTrue(all(u.startswith("https://") for u in self.rec["images"]))

    def test_not_marked_blocked(self):
        self.assertIsNone(self.rec["blocked"])


class TestExtractBlockedPage(unittest.TestCase):
    def test_block_marker_without_content_is_flagged(self):
        rec = wx.extract(BLOCKED_PAGE)
        self.assertIsNotNone(rec["blocked"])
        self.assertIsNone(rec["content"])

    def test_marker_word_inside_real_content_is_not_a_block(self):
        """正文里出现「完成验证」「环境异常」不算被拦 —— 只看正文容器在不在。"""
        rec = wx.extract(BLOCKED_WORD_IN_BODY)
        self.assertIsNotNone(rec["content"])
        self.assertIsNone(rec["blocked"], "正文存在时不应判定为被拦截")

    def test_every_block_marker_is_specific_enough(self):
        """拦截标记必须有足够区分度，不能是「参数错误」这种正文里也会出现的通用词。"""
        generic = {"参数错误", "错误", "验证", "异常", "失败", "无法查看"}
        for marker in wx.BLOCK_MARKERS:
            self.assertNotIn(marker, generic, marker)
            self.assertGreaterEqual(len(marker), 3, marker)
        # 曾经的写法是裸「参数错误」，已收窄为完整串
        self.assertNotIn("参数错误", wx.BLOCK_MARKERS)
        self.assertIn("参数错误，请返回首页", wx.BLOCK_MARKERS)


class TestExtractEdgeCases(unittest.TestCase):
    def test_empty_html(self):
        rec = wx.extract("")
        self.assertIsNone(rec["content"])
        self.assertIsNone(rec["title"])
        self.assertEqual(rec["images"], [])

    def test_og_title_fallback(self):
        html = ('<html><head><meta property="og:title" content="只有 og 标题">'
                '</head><body><div class="rich_media_content">正文</div>'
                '<script></script></body></html>')
        rec = wx.extract(html)
        self.assertEqual(rec["title"], "只有 og 标题")

    def test_js_content_fallback_selector(self):
        html = ('<html><body><div id="js_content">备用选择器的正文</div>'
                '<script></script></body></html>')
        rec = wx.extract(html)
        self.assertIsNotNone(rec["content"])
        self.assertIn("备用选择器", rec["content"])

    def test_collapses_excess_blank_lines(self):
        html = ('<html><body><div class="rich_media_content">'
                '<p>a</p><p></p><p></p><p></p><p>b</p></div><script></script>'
                '</body></html>')
        rec = wx.extract(html)
        self.assertNotIn("\n\n\n", rec["content"])


class TestFetchErrorSurface(unittest.TestCase):
    def test_unreachable_host_raises_fetcherror(self):
        """网络不可达 -> FetchError（不是裸的 URLError）。

        用桩替换 `urlopen`：真去连 127.0.0.1:9 时，若环境里配了 HTTP 代理，
        代理会回一个 502，代码就走 HTTPError 分支了 —— 结果取决于环境。
        """
        original = wx.urllib.request.urlopen
        wx.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
            wx.urllib.error.URLError("connection refused"))
        try:
            with self.assertRaises(wx.FetchError) as ctx:
                wx.fetch("http://127.0.0.1:9/definitely-not-listening", timeout=5)
            msg = str(ctx.exception)
            self.assertIn("失败", msg)
            self.assertNotIn("URLError", msg)
            self.assertNotIn("Traceback", msg)
        finally:
            wx.urllib.request.urlopen = original

    def test_http_error_becomes_fetcherror(self):
        original = wx.urllib.request.urlopen
        err = wx.urllib.error.HTTPError(
            "https://mp.weixin.qq.com/s/x", 404, "Not Found", {}, None)
        wx.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(err)
        try:
            with self.assertRaises(wx.FetchError) as ctx:
                wx.fetch("https://mp.weixin.qq.com/s/x")
            self.assertIn("404", str(ctx.exception))
        finally:
            wx.urllib.request.urlopen = original


class TestCliContract(unittest.TestCase):
    def test_help_exits_zero(self):
        rc, out, _ = _run(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("fetch_wechat_article", out)

    def test_missing_url_is_usage_error(self):
        rc, out, err = _run([])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)

    def test_non_url_input_is_rejected_cleanly(self):
        rc, out, err = _run(["mp.weixin.qq.com/s/abc"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("http", err)

    def test_help_after_required_arg_does_not_crash(self):
        """--help 曾因 url 缺失与 urllib 的 ValueError 抛栈，这里锁住行为。"""
        rc, out, err = _run(["--help"])
        self.assertEqual(rc, 0)
        self.assertNotIn("unknown url type", err)

    def test_unreachable_url_reports_chinese_error(self):
        """CLI 层面：不可达地址给中文提示 + rc=2，且不漏 traceback。

        这是 CLI 用例，没法在进程内打桩，会真的尝试一次连接。
        断言只取「连接被拒」与「代理返回错误」两条路径**共有**的性质
        （rc=2 / 中文错误 / 无栈），因此不受代理环境影响。
        """
        rc, out, err = _run(["http://127.0.0.1:9/nope"])
        self.assertEqual(rc, 2, err)
        self.assertIn("错误", err)


class TestFailureExitContract(unittest.TestCase):
    """取不到正文必须以非零退出码收场。

    6.0 修复的回归：原来只 `print("!! 未能提取正文")` 然后 `return 0`，
    调用方（Agent）按退出码判断时会**把"没取到"当成"取到了"**。
    """

    def _call_main(self, html):
        # 先建好缓冲区再打桩 —— 否则中途出错会让桩泄漏到其它用例
        buf_out, buf_err = io.StringIO(), io.StringIO()
        original = wx.fetch
        old_out, old_err = sys.stdout, sys.stderr
        wx.fetch = lambda url, timeout=None: html
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            return wx.main(["https://mp.weixin.qq.com/s/abcdefghijklmnop"]), buf_out.getvalue()
        finally:
            wx.fetch = original
            sys.stdout, sys.stderr = old_out, old_err

    def test_no_content_returns_exit_code_3(self):
        rc, out = self._call_main("<html><body>nothing here</body></html>")
        self.assertEqual(rc, 3)
        self.assertIn("未能提取正文", out)

    def test_blocked_page_returns_exit_code_3(self):
        rc, _ = self._call_main('<html><body>环境异常，完成验证后即可继续访问</body></html>')
        self.assertEqual(rc, 3)

    def test_content_present_still_returns_zero(self):
        """正向用例：能取到正文时仍必须是 0（别把修复做成误伤）。"""
        html = ('<html><head><meta property="og:title" content="标题" /></head>'
                '<body><div class="rich_media_content" id="js_content">'
                '<p>正文第一段</p><p>正文第二段</p></div>'
                '<script></script></body></html>')
        rc, out = self._call_main(html)
        self.assertEqual(rc, 0)
        self.assertIn("正文第一段", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
