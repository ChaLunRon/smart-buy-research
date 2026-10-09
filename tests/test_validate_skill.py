#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_skill.py 的单元测试。

重点覆盖 5.9 新增的两条检查（5.10 又扩了第 14 项的覆盖面）—— 它们是
「发布后审计发现的盲区」的防复发装置：

  13. `## 目录` 与正文二级标题**同集同序**
      原检查只验证「目录里的锚点能否解析」：目录里**多**一条会报错，
      而正文有、目录**少**收录的、以及**顺序**，它一概不管 ——
      README 漏了「引用」、CONTRIBUTING 漏了「License」，都是这么漏出去的。
  14. 自指链接指向「需在仓库设置中开启」的功能
      （Discussions / Wiki / Packages / Private vulnerability reporting）
      未开启就是死链，但只以 WARN 呈现、不影响退出码。
      5.10 起：匹配范围放宽到整段路径（才认得出 `/security/advisories`），
      且**已人工实测确认开启**的（`SELF_LINK_OPTIN_VERIFIED`）只列出、不报警告。

说明：夹具全部搭在**临时目录**里，不引用本仓库当前内容的行号或措辞 ——
否则改一次 README 就会连带弄红测试，那是夹具设计错了，不是内容错了。
"""

import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "validate_skill.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vs = _load("validate_skill_under_test", TOOL)


SKILL_MD = """---
name: {name}
description: 用于测试校验器的最小技能夹具，不涉及任何真实能力与外部依赖。
metadata:
  version: "1.0"
---

# 夹具技能

## 目录

- [第一节](#第一节)

## 第一节

正文。
"""


class Fixture(object):
    """在临时目录里搭一个最小技能仓库（目录名 = `name`，否则第 2 项必失败）。"""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="vsfix-")
        # 目录名不含保留字（`skill` / `claude` / `anthropic` / `agent-skills`）——
        # 它是校验器第 2 项要拦的东西，夹具自己不能先踩上。
        self.name = "demo-tool-1-0"
        self.root = os.path.join(self.tmp, self.name)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def build(self, doc=None):
        self.write("SKILL.md", SKILL_MD.format(name=self.name))
        if doc is not None:
            self.write("NOTES.md", doc)
        return self

    def run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vs.main([self.root])
        return rc, buf.getvalue()

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TocSyncTest(unittest.TestCase):
    """检查 13：`## 目录` ↔ 二级标题。"""

    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def test_目录与正文同集同序时通过(self):
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [第一节](#第一节)\n"
            "- [第二节](#第二节)\n\n"
            "## 第一节\n\n正文。\n\n"
            "## 第二节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("目录与二级标题同集同序", out)

    def test_漏收录一条二级标题判失败(self):
        # 正文有两节，目录只写了一条 —— 正是 README「引用」那类漏法。
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [第一节](#第一节)\n\n"
            "## 第一节\n\n正文。\n\n"
            "## 第二节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        self.assertIn("漏收录", out)

    def test_顺序与正文不一致判失败(self):
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [第二节](#第二节)\n"
            "- [第一节](#第一节)\n\n"
            "## 第一节\n\n正文。\n\n"
            "## 第二节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        self.assertIn("顺序", out)

    def test_目录里的分组小标题不算条目(self):
        # 目录里为可读性插入的分组标签不是目录项，不能当成「多收录」。
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "**使用者**\n\n"
            "- [第一节](#第一节)\n\n"
            "**维护者**\n\n"
            "- [第二节](#第二节)\n\n"
            "## 第一节\n\n正文。\n\n"
            "## 第二节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)

    def test_指向其它文件的目录项不参与比对(self):
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [第一节](#第一节)\n"
            "- [主文件](./SKILL.md)\n\n"
            "## 第一节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)

    def test_代码块里的标题不参与比对(self):
        # references/report-template.md 整篇正文在栅栏里，那些 ## 是模板内容。
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [概述](#概述)\n\n"
            "## 概述\n\n"
            "```markdown\n"
            "## 这是模板里的一节，不是本文档的章节\n"
            "```\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)

    def test_目录条目文字可加标点只要锚点对得上(self):
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [一、无头浏览器（首选）](#一无头浏览器实测首选)\n\n"
            "## 一、无头浏览器（实测，首选）\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)

    def test_目录里多出一条无法解析的锚点仍判失败(self):
        # 原有检查（第 7 项）覆盖的那一半必须保持不变。
        self.fx.build(
            "# 文档\n\n"
            "## 目录\n\n"
            "- [第一节](#第一节)\n"
            "- [不存在的节](#不存在的节)\n\n"
            "## 第一节\n\n正文。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        self.assertIn("无法解析", out)


class SelfLinkOptinTest(unittest.TestCase):
    """检查 14：指向「需在设置中开启」功能的链接。"""

    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def test_指向discussions报警但不影响退出码(self):
        self.fx.build("见 https://github.com/acme/acme/discussions 提问。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("Discussions", out)
        self.assertIn("需在仓库设置中开启", out)

    def test_指向wiki与packages同样报警(self):
        self.fx.build(
            "https://github.com/acme/acme/wiki\n"
            "https://github.com/acme/acme/packages\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("Wiki", out)
        self.assertIn("Packages", out)

    def test_指向security_advisories记为已核实而非警告(self):
        # 5.10 新增：两段式开关路径。已人工实测确认开启 ⇒ 列出但不报警告。
        self.fx.build(
            "报漏洞见 https://github.com/acme/acme/security/advisories/new 。\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("Private vulnerability reporting", out)
        self.assertIn("已核实", out)
        self.assertNotIn("WARN", out)

    def test_两段式路径更深的层级也能命中(self):
        self.fx.build(
            "https://github.com/acme/acme/security/advisories/123/edit\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("已核实", out)

    def test_单独的security路径不算命中(self):
        # 仓库的 Security 标签页本身**不需要**任何开关，不能把 `/security` 误判成 PVR。
        self.fx.build("https://github.com/acme/acme/security\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("未发现指向", out)
        self.assertNotIn("已核实", out)

    def test_常规仓库页面不报警(self):
        self.fx.build(
            "https://github.com/acme/acme/releases\n"
            "https://github.com/acme/acme/issues\n"
            "https://github.com/acme/acme/actions/workflows/validate.yml\n"
            "https://github.com/acme/acme/blob/main/docs/getting-started.md\n")
        rc, out = self.fx.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("未发现指向", out)


class AnchorHelperTest(unittest.TestCase):
    """检查 13 依赖的两个纯函数，单独钉住它们的行为。"""

    def test_github_anchor_去标点转小写(self):
        self.assertEqual(vs.github_anchor("Hello World"), "hello-world")
        self.assertEqual(vs.github_anchor("一、无头浏览器（实测，首选）"),
                         "一无头浏览器实测首选")

    def test_重复标题带序号后缀(self):
        anchors = [a for _, a, _ in vs.iter_headings("## 校验\n\n## 校验\n")]
        self.assertEqual(anchors, ["校验", "校验-1"])

    def test_目录解析只认指向本文件的条目(self):
        text = ("## 目录\n\n"
                "**分组**\n\n"
                "- [甲](#甲)\n"
                "- [乙](./OTHER.md)\n"
                "- 一个普通列表项\n\n"
                "## 甲\n")
        self.assertEqual(vs.toc_entry_anchors(text), ["甲"])


if __name__ == "__main__":
    unittest.main()
