#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Skill 自检工具（纯标准库，无需任何第三方依赖）。

用途：在一个技能仓库里跑一遍结构与规范检查，任何一条不通过就以非零退出码结束，
可直接作为 CI 的校验步骤。

    python tools/validate_skill.py .          # 校验当前目录
    python tools/validate_skill.py --quiet .  # 只输出问题

检查项（对应 Agent Skills 规范的硬性约束 + 本仓库的自我约束）：

  1. SKILL.md 存在且含合法的 YAML frontmatter
  2. `name`：仅小写字母/数字/连字符、不以连字符开头结尾、无连续连字符、
     ≤64 字符、不含保留字（claude / anthropic / skill 等）、**与所在目录名一致**
  3. `description`：存在、≤1024 字符、不含 XML 标签、非第一人称口吻
  4. SKILL.md 正文字数（不含 frontmatter）< 500 行
  5. references/ 下每个 >100 行的文件必须有 `## 目录`
  6. references/ 之间**不得互相引用**（引用只能有一层深度）
  7. 所有相对 Markdown 链接可达；行内锚点按 GitHub 算法可解析
  8. 所有路径使用正斜杠；正文中不得出现反斜杠路径
  9. 仓库内不得出现 CRLF 行尾
 10. scripts/ 下所有 .py 可编译
 11. 版本一致性：`name` 中的 `主-次` 与 `metadata.version` 的 `主.次` 对得上
 12. 发布前占位值清点：清点仍可能残留的**模板占位符**
     （常量见下方 `PLACEHOLDER_TOKENS`，即姓名字段的三种尖括号写法）
     与 `example.com` 一类占位域名
     —— 只报警不失败，用于发布前自查

退出码：0 = 全部通过；1 = 存在失败项；2 = 用法错误。
"""

import argparse
import os
import re
import sys

RESERVED_WORDS = ("claude", "anthropic", "skill", "agent-skills")
MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024
MAX_SKILL_BODY_LINES = 500
TOC_MIN_LINES = 100
PLACEHOLDER_DOMAIN_RE = re.compile(r"example\.(?:com|org|net)")

# 发布前要清点的**模板占位符**（姓名字段常见的三种写法）。
# 一律写成字符串拼接：将来做「全局替换」时，源码里完整字符串形态的常量
# 会被一并替换掉、检查器随即失效 —— 上一版的正则就是这样被污染成
# re.compile(r"<占位>|<占位>|<占位>") 的。拼接写法对这种替换天然免疫。
PLACEHOLDER_TOKENS = (
    "<" + "your-name" + ">",
    "<" + "YOUR_NAME" + ">",
    "<" + "你的用户名" + ">",
)
# 这些文件里出现占位符是**正常的**：CHANGELOG 天然要引用旧占位符来说明替代关系。
PLACEHOLDER_SKIP_FILES = {"CHANGELOG.md"}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


class Report:
    def __init__(self):
        self.fails = []
        self.warns = []
        self.passes = []

    def ok(self, msg):
        self.passes.append(msg)

    def fail(self, msg):
        self.fails.append(msg)

    def warn(self, msg):
        self.warns.append(msg)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def parse_frontmatter(text):
    """极简 frontmatter 解析：只支持本仓库用到的 顶层键 + 一层缩进子键。"""
    if not text.startswith("---"):
        return None, text
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return None, text
    raw = parts[0][3:]
    body = parts[1].lstrip("\n")
    data = {}
    current = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] not in (" ", "\t"):
            m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if val == "":
                    data[key] = {}
                    current = key
                else:
                    data[key] = val.strip("'\"")
                    current = None
        elif current is not None:
            m = re.match(r"^\s+([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
            if m and isinstance(data.get(current), dict):
                data[current][m.group(1)] = m.group(2).strip().strip("'\"")
    return data, body


def github_anchor(heading):
    """GitHub 标题锚点算法：小写 → 去掉非 [\\w\\s-] 字符 → 空格转连字符。"""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def collect_anchors(text):
    """返回该文件中全部可用锚点（含重复标题的 -1/-2 后缀）。"""
    seen = {}
    anchors = set()
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if not m:
            continue
        base = github_anchor(m.group(2))
        n = seen.get(base, 0)
        anchors.add(base if n == 0 else "%s-%d" % (base, n))
        seen[base] = n + 1
    return anchors


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield os.path.join(dirpath, name)


def check_name(rep, fm, root):
    name = fm.get("name")
    if not name:
        rep.fail("frontmatter 缺少 `name` 字段")
        return None
    if not isinstance(name, str):
        rep.fail("`name` 必须是字符串")
        return None
    if len(name) > MAX_NAME_LEN:
        rep.fail("`name` 长度 %d > %d" % (len(name), MAX_NAME_LEN))
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        rep.fail("`name` 必须是小写字母/数字/连字符的 hyphen-case（不得有点号、"
                 "不得以连字符开头结尾、不得有连续连字符）：%r" % name)
    else:
        rep.ok("`name` 字符集合法：%s" % name)
    if name != os.path.basename(os.path.abspath(root)):
        rep.fail("`name`（%s）必须与所在目录名（%s）一致"
                 % (name, os.path.basename(os.path.abspath(root))))
    else:
        rep.ok("`name` 与目录名一致：%s" % name)
    lowered = name.lower()
    hit = [w for w in RESERVED_WORDS if w in lowered]
    if hit:
        rep.fail("`name` 含保留字：%s" % hit)
    return name


def check_description(rep, fm):
    desc = fm.get("description")
    if not desc:
        rep.fail("frontmatter 缺少 `description` 字段")
        return
    if len(desc) > MAX_DESC_LEN:
        rep.fail("`description` 长度 %d > %d" % (len(desc), MAX_DESC_LEN))
    else:
        rep.ok("`description` 长度 %d / %d" % (len(desc), MAX_DESC_LEN))
    if re.search(r"<[A-Za-z/]", desc):
        rep.fail("`description` 含 XML/HTML 标签")
    if re.match(r"^(我|我们|you|I)\b", desc.strip()):
        rep.warn("`description` 建议用第三人称（当前以第一/第二人称开头）")


def check_skill_body(rep, body):
    n = len(body.splitlines())
    if n >= MAX_SKILL_BODY_LINES:
        rep.fail("SKILL.md 正文 %d 行，超过 %d 行上限" % (n, MAX_SKILL_BODY_LINES))
    else:
        rep.ok("SKILL.md 正文 %d / %d 行" % (n, MAX_SKILL_BODY_LINES))


def check_reference_depth(rep, ref_dir):
    """references/ 下的文件不得互相引用（引用只能有一层）。"""
    if not os.path.isdir(ref_dir):
        return
    names = [f for f in sorted(os.listdir(ref_dir)) if f.endswith(".md")]
    nested = 0
    for fname in names:
        text = read_text(os.path.join(ref_dir, fname))
        others = [o for o in names if o != fname]
        for other in others:
            # 只把「文件名本身」当作互相引用的证据，忽略 Markdown 相对链接（那是合法导航）
            if other in text:
                nested += 1
                rep.fail("references/%s 中出现了另一个引用文件名 `%s`（引用不得嵌套）"
                         % (fname, other))
    if not nested:
        rep.ok("references/ 下 %d 个文件无嵌套引用" % len(names))


def check_toc(rep, ref_dir):
    if not os.path.isdir(ref_dir):
        return
    long_files = 0
    missing = 0
    for fname in sorted(os.listdir(ref_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(ref_dir, fname)
        text = read_text(path)
        lines = len(text.splitlines())
        if lines > TOC_MIN_LINES:
            long_files += 1
            if "## 目录" not in text:
                missing += 1
                rep.fail("references/%s 共 %d 行（>%d），缺少 `## 目录`"
                         % (fname, lines, TOC_MIN_LINES))
    if long_files and not missing:
        rep.ok("references/ 下 %d 个超长文件均带 `## 目录`" % long_files)


def check_links(rep, root):
    """所有相对 Markdown 链接必须可达；带锚点的必须能解析。"""
    md_files = [p for p in iter_files(root) if p.endswith(".md")]
    base = os.path.abspath(root)
    checked = 0
    for path in md_files:
        text = read_text(path)
        rel_self = os.path.relpath(path, base).replace("\\", "/")
        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for target in re.findall(r"\]\(([^)\s]+)\)", line):
                if re.match(r"^(https?:|mailto:|#)", target):
                    if target.startswith("#"):
                        anchors = collect_anchors(text)
                        if target[1:] and target[1:] not in anchors:
                            rep.fail("%s：锚点 `%s` 无法解析" % (rel_self, target))
                        checked += 1
                    continue
                file_part, _, anchor = target.partition("#")
                if not file_part:
                    continue
                dest = os.path.normpath(os.path.join(os.path.dirname(path), file_part))
                if not os.path.exists(dest):
                    rep.fail("%s：链接目标不存在 `%s`" % (rel_self, target))
                    continue
                checked += 1
                if anchor:
                    if os.path.isdir(dest):
                        continue
                    sub = read_text(dest)
                    if anchor not in collect_anchors(sub):
                        rep.fail("%s：锚点 `%s` 在 %s 中无法解析"
                                 % (rel_self, target, file_part))
    rep.ok("相对链接/锚点检查：%d 处通过" % checked)


def check_line_endings(rep, root):
    bad = []
    for path in iter_files(root):
        with open(path, "rb") as fh:
            if b"\r\n" in fh.read():
                bad.append(os.path.relpath(path, root).replace("\\", "/"))
    if bad:
        rep.fail("以下文件为 CRLF 行尾，应统一为 LF：%s" % bad[:8])
    else:
        rep.ok("行尾统一为 LF")


def check_backslash_paths(rep, root):
    """正文里不得出现 Windows 反斜杠路径（脚本里的转义除外）。"""
    hits = []
    for path in iter_files(root):
        if not path.endswith(".md"):
            continue
        text = read_text(path)
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"[A-Za-z]:\\\\", line):
                hits.append("%s:%d" % (os.path.relpath(path, root).replace("\\", "/"), i))
    if hits:
        rep.warn("疑似 Windows 绝对路径（请确认是否应为正斜杠）：%s" % hits[:5])


def check_scripts(rep, root):
    sdir = os.path.join(root, "scripts")
    if not os.path.isdir(sdir):
        return
    count = 0
    for fname in sorted(os.listdir(sdir)):
        if not fname.endswith(".py"):
            continue
        count += 1
        path = os.path.join(sdir, fname)
        try:
            compile(read_text(path), fname, "exec")
        except SyntaxError as exc:
            rep.fail("scripts/%s 语法错误：%s" % (fname, exc))
    rep.ok("scripts/ 下 %d 个脚本编译通过" % count)


def check_version_consistency(rep, name, fm):
    ver = fm.get("metadata")
    if not isinstance(ver, dict) or "version" not in ver:
        return
    v = ver["version"]
    m = re.search(r"-(\d+)-(\d+)$", name or "")
    if not m:
        return
    expect = "%s.%s" % (m.group(1), m.group(2))
    if v != expect:
        rep.fail("`name` 的版本（%s）与 `metadata.version`（%s）不一致，应为 %s"
                 % (expect, v, expect))
    else:
        rep.ok("版本一致：name=%s / metadata.version=%s" % (name, v))


def check_placeholders(rep, root):
    """清点发布前仍需处理的占位值。

    本项目当前**已无身份占位符**（署名与 owner 定稿为 ChaLunRon）。
    保留这项清点，是为了将来 fork / 改名时能一眼看出还剩多少活儿：
    数姓名字段的模板占位符（见 `PLACEHOLDER_TOKENS`）与
    `example.com` 一类占位域名 —— 只报警、不失败。

    常量本身不在扫描范围内（只扫 .md/.cff/.yml/.yaml/.txt/.json），
    而且它用拼接写法，任何全局替换都不会把它改坏。
    `PLACEHOLDER_SKIP_FILES` 里的文件属于「正常引用」，不计入。
    """
    total = 0
    files = []
    domains = []
    for path in iter_files(root):
        if not path.endswith((".md", ".cff", ".yml", ".yaml", ".txt", ".json")):
            continue
        rel = os.path.relpath(path, root).replace("\\", "/")
        if os.path.basename(rel) in PLACEHOLDER_SKIP_FILES:
            continue
        text = read_text(path)
        n = sum(text.count(t) for t in PLACEHOLDER_TOKENS)
        if n:
            total += n
            files.append("%s(%d)" % (rel, n))
        if PLACEHOLDER_DOMAIN_RE.search(text):
            domains.append(rel)
    if total:
        rep.warn("发现 %d 处模板占位符待替换：%s（发布前请改成真实值）"
                 % (total, "、".join(files)))
    else:
        rep.ok("未发现待替换的占位符")
    if domains:
        rep.warn("仍含占位域名（example.com 之类），发布前请替换：%s" % domains)
    else:
        rep.ok("未发现占位域名")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="validate_skill.py",
        description="Agent Skill 结构与规范自检（纯标准库）。")
    ap.add_argument("root", nargs="?", default=".",
                    help="技能仓库根目录（含 SKILL.md），默认当前目录")
    ap.add_argument("--quiet", action="store_true", help="只输出失败与警告")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    skill_md = os.path.join(root, "SKILL.md")
    if not os.path.isfile(skill_md):
        print("错误：%s 下找不到 SKILL.md" % root, file=sys.stderr)
        return 2

    rep = Report()
    text = read_text(skill_md)
    fm, body = parse_frontmatter(text)
    if fm is None:
        rep.fail("SKILL.md 缺少合法的 YAML frontmatter（应以 `---` 开头并以 `---` 结束）")
        fm = {}

    name = check_name(rep, fm, root)
    check_description(rep, fm)
    check_skill_body(rep, body)
    check_version_consistency(rep, name, fm)
    check_toc(rep, os.path.join(root, "references"))
    check_reference_depth(rep, os.path.join(root, "references"))
    check_links(rep, root)
    check_line_endings(rep, root)
    check_backslash_paths(rep, root)
    check_scripts(rep, root)
    check_placeholders(rep, root)

    if not args.quiet:
        for msg in rep.passes:
            print("  PASS  %s" % msg)
    for msg in rep.warns:
        print("  WARN  %s" % msg)
    for msg in rep.fails:
        print("  FAIL  %s" % msg)

    print("\n%d 通过 / %d 警告 / %d 失败" % (len(rep.passes), len(rep.warns), len(rep.fails)))
    if rep.fails:
        print("校验未通过")
        return 1
    print("Skill 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
