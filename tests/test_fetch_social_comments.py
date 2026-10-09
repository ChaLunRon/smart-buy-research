#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_social_comments.py 的单元测试与 CLI 集成测试。

重点覆盖（都是"错了会静默出错"的地方）：
  1. 平台域名判断 —— 尤其**不能**把 `bilibili.com.evil.com` 判成 bilibili
  2. 正文的嵌套套法 —— B站把正文放在 `content.message`，「同一层找不到正文」
     是 6.0 开发时真实踩过的坑（接口命中了却一条评论都抽不出来）
  3. 评论抽取的**宁缺毋滥** —— 配置块、HTML 块不能被当成评论；
     嵌套的 content 子对象也不能被重复计成第二条评论
  4. 去重与排序 —— 同一人同一句取赞数高的那条
  5. 参数校验与退出码契约

说明：全部离线。不联网、不要求安装 agent-browser —— CI 上必须能稳定跑过。
"""

import importlib.util
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fetch_social_comments.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fsc = _load("fetch_social_comments_under_test", SCRIPT)


def _run(args):
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


class TestPlatformTable(unittest.TestCase):
    def test_every_platform_has_hosts_and_pattern(self):
        self.assertTrue(fsc.PLATFORMS)
        for key, cfg in fsc.PLATFORMS.items():
            with self.subTest(platform=key):
                self.assertTrue(cfg.get("hosts"), "%s 缺少 hosts" % key)
                self.assertTrue(cfg.get("pattern"), "%s 缺少 pattern" % key)

    def test_every_pattern_compiles(self):
        import re
        for key, cfg in fsc.PLATFORMS.items():
            with self.subTest(platform=key):
                re.compile(cfg["pattern"])  # 编译不过就是脚本级错误


class TestGuessPlatform(unittest.TestCase):
    def test_common_hosts(self):
        cases = [
            ("https://www.bilibili.com/video/BV1pa4y1X7kv/", "bilibili"),
            ("https://space.bilibili.com/3053296", "bilibili"),
            ("https://m.weibo.cn/detail/123", "weibo"),
            ("https://s.weibo.com/weibo?q=x", "weibo"),
            ("https://www.zhihu.com/question/123", "zhihu"),
            ("https://tieba.baidu.com/p/123", "tieba"),
            ("https://www.xiaohongshu.com/explore/abc", "xiaohongshu"),
            ("https://www.douyin.com/video/123", "douyin"),
            ("https://bbs.nga.cn/read.php?tid=123", "nga"),
            ("https://post.smzdm.com/p/abc/", "smzdm"),
        ]
        for url, want in cases:
            with self.subTest(url=url):
                self.assertEqual(fsc.guess_platform(url), want)

    def test_lookalike_domain_is_not_matched(self):
        """`bilibili.com.evil.com` 不是 B站 —— 后缀匹配必须落在域名边界上。"""
        for url in ("https://bilibili.com.evil.com/x",
                    "https://notbilibili.com/x",
                    "https://evil-zhihu.com/x"):
            with self.subTest(url=url):
                self.assertIsNone(fsc.guess_platform(url))

    def test_unknown_and_invalid(self):
        self.assertIsNone(fsc.guess_platform("https://example.org/x"))
        self.assertIsNone(fsc.guess_platform("not-a-url"))


class TestFindText(unittest.TestCase):
    def test_direct_text_field(self):
        self.assertEqual(fsc._find_text({"message": " 你好 "}), "你好")

    def test_nested_content_message(self):
        """B站形状：正文在 content.message，同一层只有 like / member。

        这是 6.0 开发时真实踩过的坑 —— 接口命中了却抽不出任何评论。
        """
        reply = {"like": 51, "content": {"message": "约好几个up造势"}, "member": {}}
        self.assertEqual(fsc._find_text(reply), "约好几个up造势")

    def test_no_text_returns_none(self):
        self.assertIsNone(fsc._find_text({"cursor": {"is_end": True}}))

    def test_blank_text_is_none(self):
        self.assertIsNone(fsc._find_text({"message": "   "}))


class TestExtractComments(unittest.TestCase):
    def _bili_payload(self):
        return {
            "code": 0,
            "data": {
                "cursor": {"is_end": True, "all_count": 230},
                "replies": [
                    {"rpid": 1, "like": 51,
                     "content": {"message": "预售都还没消息呢，就已经开始约好几个up造势了"},
                     "member": {"uname": "白给の少年"}, "ctime": 1700000000},
                    {"rpid": 2, "like": 1,
                     "content": {"message": "轴体感觉好拉垮"},
                     "member": {"uname": "東條雪蓮Official"}},
                ],
            },
        }

    def test_extracts_replies_with_author_and_like(self):
        rows = fsc.extract_comments(self._bili_payload())
        self.assertEqual(len(rows), 2)
        by_text = {r["text"]: r for r in rows}
        top = by_text["预售都还没消息呢，就已经开始约好几个up造势了"]
        self.assertEqual(top["author"], "白给の少年")
        self.assertEqual(top["like"], 51)
        self.assertEqual(top["id"], 1)
        self.assertEqual(top["time"], 1700000000)

    def test_nested_content_is_not_double_counted(self):
        """content 子对象里也有 message，但它没有作者/赞数，不能算第二条评论。"""
        rows = fsc.extract_comments(self._bili_payload())
        self.assertEqual(len(rows), 2)

    def test_config_blob_is_skipped(self):
        payload = {"data": {"config": {"content": "some config text"},
                            "control": {"text": "no author here"}}}
        self.assertEqual(fsc.extract_comments(payload), [])

    def test_html_blob_is_skipped(self):
        payload = {"data": {"item": {"content": "<!DOCTYPE html><html>...",
                                     "user": {"name": "x"}}}}
        self.assertEqual(fsc.extract_comments(payload), [])

    def test_overlong_text_is_skipped(self):
        payload = {"a": {"message": "长" * (fsc.MAX_TEXT_LEN + 1),
                         "author": "x"}}
        self.assertEqual(fsc.extract_comments(payload), [])

    def test_cursor_object_is_not_a_comment(self):
        payload = {"data": {"cursor": {"is_end": True, "all_count": 230}}}
        self.assertEqual(fsc.extract_comments(payload), [])


class TestDedup(unittest.TestCase):
    def test_keeps_higher_like_for_same_author_and_text(self):
        rows = [{"text": "一样的话", "author": "甲", "like": 3},
                {"text": "一样的话", "author": "甲", "like": 99}]
        out = fsc.dedup(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["like"], 99)

    def test_same_text_different_author_is_kept(self):
        rows = [{"text": "一样的", "author": "甲", "like": 1},
                {"text": "一样的", "author": "乙", "like": 2}]
        self.assertEqual(len(fsc.dedup(rows)), 2)

    def test_sorted_by_like_desc_with_none_last(self):
        rows = [{"text": "c", "author": "", "like": None},
                {"text": "a", "author": "", "like": 5},
                {"text": "b", "author": "", "like": 50}]
        out = fsc.dedup(rows)
        self.assertEqual([r["text"] for r in out], ["b", "a", "c"])


class TestRunHelper(unittest.TestCase):
    def test_missing_binary_raises_skill_error_not_traceback(self):
        """可执行文件不存在时必须转成 SkillError（友好中文），不能裸抛。"""
        with self.assertRaises(fsc.SkillError):
            fsc.run(["definitely-not-a-real-binary-xyz-12345"], timeout=5)


class TestCliContract(unittest.TestCase):
    def test_help_exits_zero(self):
        rc, out, _ = _run(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("fetch_social_comments", out)

    def test_doctor_exit_code_is_documented_set(self):
        """--doctor 只允许 0（齐备）或 1（不齐备）—— 不许崩。"""
        rc, out, _ = _run(["--doctor"])
        self.assertIn(rc, (0, 1))
        self.assertIn("agent-browser", out)

    def test_missing_url_exits_two(self):
        rc, _, err = _run([])
        self.assertEqual(rc, 2)

    def test_negative_max_scrolls_exits_two(self):
        rc, _, _ = _run(["https://example.org/x", "--max-scrolls", "-1"])
        self.assertEqual(rc, 2)

    def test_unknown_platform_exits_two(self):
        rc, _, _ = _run(["https://example.org/x", "--platform", "bogus"])
        self.assertEqual(rc, 2)

    def test_source_mentions_all_documented_exit_codes(self):
        """退出码契约必须写在 docstring 里（0/1/2/3），否则调用方无从判读。"""
        with open(SCRIPT, encoding="utf-8") as f:
            text = f.read()
        for code in ("    0  ", "    1  ", "    2  ", "    3  "):
            self.assertIn(code, text)


if __name__ == "__main__":
    unittest.main()
