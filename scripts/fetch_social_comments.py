# -*- coding: utf-8 -*-
"""
自媒体内容与评论读取 —— 用真实浏览器"旁观"页面自己发出的数据接口。

为什么需要这个脚本：
  小红书 / 抖音 / 微博 / 知乎 / 贴吧 这类平台，评论接口都带**请求签名**
  （X-s / a_bogus / x-zse-96 / w_rid ...），算法混淆、频繁更换，逆向不可持续。

  本脚本走另一条路：**让浏览器自己算签名**。

  做法不是"破解签名"，而是三步旁观：
    1. 用真实浏览器打开目标页面 —— 页面自己的 JS 会算出签名并发请求
    2. 只**旁观**它发了什么 —— `network requests` 定位评论接口
    3. 取回那条请求的响应体 —— `network request <id>`

  签名在我们看到它之前就已经算好了。所以本脚本内部**没有一行签名算法**，
  也不做任何风控对抗、不处理验证码、不规避检测。

  ⚠️ 这条路线**不是万能的**：站点被反爬拦住（如小红书 error_code=300012）
  时，页面自己都拿不到数据，旁观自然也没有。此时应换源或请用户协作。

依赖（缺一不可，先跑 `--doctor` 检查）：
  - Node.js + agent-browser：`npm i agent-browser`
  - 一个 Chrome/Chromium：`npx agent-browser install`，或用环境变量
    `AGENT_BROWSER_EXECUTABLE_PATH` 指向本机已有的 Chrome

用法:
    python fetch_social_comments.py <url>
    python fetch_social_comments.py <url> --max-scrolls 12 --out comments.json
    python fetch_social_comments.py <url> --list      # 只列候选接口，不解析
    python fetch_social_comments.py <url> --raw       # 打印原始响应体（调试用）
    python fetch_social_comments.py <url> --state auth.json   # 复用你自己的登录态
    python fetch_social_comments.py --doctor          # 环境自检，不联网

退出码:
    0  成功取到评论
    1  环境/依赖问题（含 --doctor 未通过）
    2  参数错误
    3  打开了页面但没取到评论（站点拦截 / 接口没匹配上 / 页面无需滚动就结束了）
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class SkillError(Exception):
    """可预期的失败：转成友好中文提示，不打印栈。"""


# ---------------------------------------------------------------- 子进程封装

# agent-browser 的 open 会长时间不返回（实测可挂 6 分钟），但页面其实已经加载好了。
# 所以要给它设上限，超时就放弃等待、直接往下走 —— 不能让它卡死整个流程。
OPEN_TIMEOUT = 75


def run(cmd, timeout=60, cwd=None, env=None, tolerate_timeout=False):
    """跑一条命令，返回 (rc, 合并后的输出)。

    实现上刻意**不用管道而用临时文件**：agent-browser 会派生一个脱离的 daemon，
    而它会继承父进程的 stdout/stderr 句柄。若父进程用的是管道，`communicate()`
    会一直等 EOF —— 而 daemon 不死，EOF 永远不来，于是整条命令"挂住"
    （实测 `open` 能挂满 6 分钟）。改成文件句柄后，读文件不受 daemon 影响。

    tolerate_timeout=True 时超时不算失败（rc 记为 -9），这是给 open 用的。
    """
    merged = dict(os.environ)
    if env:
        merged.update(env)

    fo_fd, fo_path = tempfile.mkstemp(prefix="ab-", suffix=".out")
    fe_fd, fe_path = tempfile.mkstemp(prefix="ab-", suffix=".err")
    try:
        with os.fdopen(fo_fd, "wb") as fo, os.fdopen(fe_fd, "wb") as fe:
            try:
                p = subprocess.Popen(cmd, stdout=fo, stderr=fe,
                                     stdin=subprocess.DEVNULL,
                                     cwd=cwd, env=merged)
            except FileNotFoundError as e:
                raise SkillError("找不到可执行文件：%s" % (e.filename or cmd[0]))
            except OSError as e:
                raise SkillError("无法执行 %s：%s" % (cmd[0], e))
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                try:
                    p.wait(timeout=15)
                except Exception:
                    pass
                rc = -9
        out = b""
        for path in (fo_path, fe_path):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    out += f.read()
        text = out.decode("utf-8", "replace").strip()
        if rc == -9 and not tolerate_timeout:
            text = (text + "\n（命令超时 %ds）" % timeout).strip()
        return rc, text
    finally:
        for path in (fo_path, fe_path):
            try:
                os.remove(path)
            except OSError:
                pass


# ---------------------------------------------------------------- 环境定位

def find_agent_browser():
    """定位 agent-browser CLI。返回可执行的命令行前缀（list）。"""
    env_bin = os.environ.get("AGENT_BROWSER_BIN")
    if env_bin and os.path.exists(env_bin):
        return [env_bin]

    here = os.getcwd()
    node = shutil.which("node") or shutil.which("node.exe")

    # 优先「node + .js」这种形式：不依赖 .cmd/.sh 外壳，跨平台最稳
    if node:
        for root in (here, os.path.expanduser("~")):
            js = os.path.join(root, "node_modules", "agent-browser", "bin",
                              "agent-browser.js")
            if os.path.exists(js):
                return [node, js]

    # 全局安装的 shim
    for name in ("agent-browser", "agent-browser.cmd", "agent-browser.exe"):
        found = shutil.which(name)
        if found:
            return [found]

    # 项目本地 .bin 外壳
    for name in ("agent-browser.cmd", "agent-browser"):
        cand = os.path.join(here, "node_modules", ".bin", name)
        if os.path.exists(cand):
            return [cand]

    # npx 兜底（可能触发联网下载，慢但能用）
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [npx, "--no-install", "agent-browser"]

    raise SkillError(
        "找不到 agent-browser。装法：在任意目录执行 `npm i agent-browser`，"
        "或设环境变量 AGENT_BROWSER_BIN 指向它的可执行文件。")


def find_chrome():
    """定位一个可用的 Chrome/Chromium，返回路径或 None。"""
    env_path = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    cands = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            cands += [
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
    cands += [
        "/usr/bin/google-chrome", "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in cands:
        if os.path.exists(c):
            return c

    # agent-browser 自己下载的 Chrome 缓存
    cache = os.path.expanduser(os.path.join("~", ".agent-browser", "chrome"))
    if os.path.isdir(cache):
        for root, _dirs, files in os.walk(cache):
            for f in files:
                if f in ("chrome.exe", "chrome", "chromium"):
                    return os.path.join(root, f)
    return None


class Ab(object):
    """agent-browser 的薄封装。"""

    def __init__(self, cmd, chrome, state=None, session=None, verbose=False):
        self.cmd = cmd
        self.chrome = chrome
        self.verbose = verbose
        self.globals = []
        if state:
            self.globals += ["--state", state]
        if session:
            self.globals += ["--session", session]

    def call(self, *args, **kw):
        timeout = kw.pop("timeout", 60)
        tolerate = kw.pop("tolerate_timeout", False)
        full = list(self.cmd) + list(self.globals) + [str(a) for a in args]
        # 指定浏览器走环境变量（比 --executable-path 稳妥：daemon 已在跑时
        # 命令行选项会被忽略，环境变量则在启动 daemon 时就被读到）
        env = {"AGENT_BROWSER_EXECUTABLE_PATH": self.chrome} if self.chrome else None
        rc, out = run(full, timeout=timeout, tolerate_timeout=tolerate, env=env)
        if self.verbose:
            sys.stderr.write("  $ %s  -> rc=%s\n" % (" ".join(full[-6:]), rc))
        return rc, out

    def close_all(self):
        self.call("close", "--all", timeout=45)

    def open(self, url):
        """打开页面，并**确认真的打开了**。

        为什么要确认：daemon 版本不匹配时 agent-browser 会自己重启一个 daemon，
        若重启正好插在 open 之后，页面就没加载上 —— 后续所有取数都会"空手而归"，
        而且不报错。所以这里必须回读一次 url 来确认。
        """
        for attempt in range(2):
            # open 可能长时间不返回（daemon 持有句柄），超时即继续；页面通常已加载
            self.call("open", url, timeout=OPEN_TIMEOUT, tolerate_timeout=True)
            for _ in range(4):
                self.wait(1500)
                rc, out = self.call("get", "url", timeout=35)
                if rc == 0 and out.strip().startswith("http"):
                    return True
            if self.verbose:
                sys.stderr.write("  （第 %d 次 open 后仍未加载，重试）\n" % (attempt + 1))
        return False

    def wait(self, ms):
        self.call("wait", ms, timeout=30)

    def scroll_bottom(self):
        self.call("eval", "window.scrollTo(0, document.body.scrollHeight)", timeout=45)

    def page_title(self):
        rc, out = self.call("get", "title", timeout=40)
        return out.strip() if rc == 0 else ""

    def json_requests(self):
        rc, out = self.call("network", "requests", "--type", "xhr,fetch",
                            "--json", timeout=60)
        if rc != 0:
            return []
        try:
            d = json.loads(out)
        except ValueError:
            return []
        return ((d.get("data") or {}).get("requests")) or []

    def request_body(self, request_id):
        rc, out = self.call("network", "request", request_id, "--json", timeout=60)
        if rc != 0:
            return None
        try:
            d = json.loads(out)
        except ValueError:
            return None
        return ((d.get("data") or {}).get("responseBody"))


# ---------------------------------------------------------------- 平台预设

# pattern 用来在"页面发出的所有 XHR/Fetch"里认出评论接口。
# 认不出也没关系：--list 会把候选全列出来，人工挑一个再用 --request-id。
PLATFORMS = {
    "bilibili":     dict(hosts=("bilibili.com",),       pattern="x/v2/reply"),
    "weibo":        dict(hosts=("weibo.com", "weibo.cn"), pattern="(buildComments|/comments)"),
    "zhihu":        dict(hosts=("zhihu.com",),          pattern="/(comments|root_comments|child_comments)"),
    "tieba":        dict(hosts=("tieba.baidu.com",),    pattern="(totalComment|/comment)"),
    "xiaohongshu":  dict(hosts=("xiaohongshu.com",),    pattern="(comment/page|/comments)"),
    "douyin":       dict(hosts=("douyin.com",),         pattern="comment/list"),
    "kuaishou":     dict(hosts=("kuaishou.com",),       pattern="photo/comment"),
    "douban":       dict(hosts=("douban.com",),         pattern="(comment|review)"),
    "nga":          dict(hosts=("nga.cn", "ngacn.cc"),  pattern="(read|post|comment)"),
    "smzdm":        dict(hosts=("smzdm.com",),          pattern="(comment|article)"),
}


def guess_platform(url):
    """按域名猜平台 key；猜不出返回 None。"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    for key, cfg in PLATFORMS.items():
        for h in cfg["hosts"]:
            if host == h or host.endswith("." + h):
                return key
    return None


# ---------------------------------------------------------------- 评论抽取

TEXT_KEYS = ("message", "content", "text", "comment", "body")
AUTHOR_KEYS = ("uname", "user_name", "screen_name", "nickname", "userName",
               "author_name", "username")
LIKE_KEYS = ("like", "like_count", "likeCount", "likes", "attitudes_count",
             "voteup_count", "digg_count", "praise_count", "up")
TIME_KEYS = ("ctime", "create_time", "created_at", "createTime", "publish_time",
             "time", "mtime")
ID_KEYS = ("rpid", "comment_id", "commentId", "cid", "tid", "id")
REPLY_COUNT_KEYS = ("rcount", "reply_count", "comment_count", "sub_comment_count",
                    "subCommentCount", "commentCount")

# 超过这个长度基本不是单条评论（多半是整页 HTML 或配置块）
MAX_TEXT_LEN = 1500


def _pick(d, keys):
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                return v
    return None


def _author_of(d):
    """作者名可能在顶层，也可能在 member / user / author 子对象里。"""
    v = _pick(d, AUTHOR_KEYS)
    if isinstance(v, str) and v.strip():
        return v.strip()
    for k in ("member", "user", "author", "user_info", "userInfo"):
        sub = d.get(k)
        if isinstance(sub, dict):
            v = _pick(sub, AUTHOR_KEYS + ("name",))
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


# 正文常被平台多套一层，例如 B站：{"content": {"message": "..."}}
TEXT_WRAPPER_KEYS = ("content", "content_detail", "comment", "body", "data", "text")


def _find_text(d):
    """在本层找正文；找不到就下沉一层再找（应对 content.message 这种套法）。"""
    v = _pick(d, TEXT_KEYS)
    if isinstance(v, str) and v.strip():
        return v.strip()
    for k in TEXT_WRAPPER_KEYS:
        sub = d.get(k)
        if isinstance(sub, dict):
            v = _pick(sub, TEXT_KEYS)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _looks_like_html(s):
    low = s[:80].lower()
    return "<html" in low or "<!doctype" in low or "<div" in low or "function(" in low


def extract_comments(obj, _depth=0, _path=""):
    """递归遍历 JSON，挑出"像一条评论"的对象。

    判据（宁缺毋滥）：有正文文本 + （有作者 或 有点赞数）。
    这样既能跨平台通用，又不会把配置项当成评论。
    """
    found = []
    if _depth > 12:
        return found
    if isinstance(obj, dict):
        t = _find_text(obj)
        if t and 0 < len(t) <= MAX_TEXT_LEN and not _looks_like_html(t):
            author = _author_of(obj)
            like = _pick(obj, LIKE_KEYS)
            if author or like is not None:
                found.append({
                    "text": t,
                    "author": author,
                    "like": int(like) if isinstance(like, (int, float)) else None,
                    "time": _pick(obj, TIME_KEYS),
                    "id": _pick(obj, ID_KEYS),
                    "reply_count": _pick(obj, REPLY_COUNT_KEYS),
                })
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                found += extract_comments(v, _depth + 1, _path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                found += extract_comments(v, _depth + 1, "%s[%d]" % (_path, i))
    return found


def dedup(rows):
    """按 (作者, 正文) 去重，保留赞数最高的那条，按赞数降序。"""
    best = {}
    for r in rows:
        key = (r.get("author") or "", r["text"])
        old = best.get(key)
        if old is None or (r.get("like") or 0) > (old.get("like") or 0):
            best[key] = r
    out = sorted(best.values(),
                 key=lambda r: (r.get("like") or 0), reverse=True)
    return out


# ---------------------------------------------------------------- 主流程

def list_mode(ab, url, want_platform, max_scrolls, log):
    """--list：只列出页面发出的 JSON 接口，不动解析。"""
    log("打开页面：%s" % url)
    if not ab.open(url):
        raise SkillError("页面没能打开（回读不到 URL）。先跑 `--doctor` 自检环境。")
    ab.wait(5000)
    for _ in range(max_scrolls):
        ab.scroll_bottom()
        ab.wait(2500)
    ab.wait(3000)

    reqs = ab.json_requests()
    if not reqs:
        raise SkillError("没有捕获到任何 XHR/Fetch 请求。可能是页面没打开成功，"
                         "或该站点的内容不由前端接口加载。")

    pat = None
    if want_platform in PLATFORMS:
        pat = re.compile(PLATFORMS[want_platform]["pattern"], re.I)

    log("")
    log("共捕获 %d 条 XHR/Fetch 请求，其中 JSON 接口如下：" % len(reqs))
    log("")
    log("  %-14s %-6s %s" % ("requestId", "状态", "URL"))
    log("  " + "-" * 74)
    hits = []
    for r in reqs:
        url_r = r.get("url") or ""
        if "application/json" not in (r.get("mimeType") or ""):
            continue
        mark = ""
        if pat and pat.search(url_r):
            mark = "  ← 平台预设命中"
            hits.append(r)
        log("  %-14s %-6s %s%s" % (r.get("requestId"), r.get("status"),
                                   url_r[:110], mark))
    log("")
    if hits:
        log("预设命中的接口 %d 条，取第一条即可：" % len(hits))
        log("  python %s %s --request-id %s" %
            (os.path.basename(sys.argv[0]), url, hits[0].get("requestId")))
    else:
        log("预设没命中。从上面挑一条像评论接口的，用 --request-id 直接取它。")
    return 0


def comments_mode(ab, url, want_platform, max_scrolls, out_path, raw,
                  request_id, log):
    log("打开页面：%s" % url)
    if not ab.open(url):
        raise SkillError("页面没能打开（回读不到 URL）。先跑 `--doctor` 自检环境。")
    title = ab.page_title()
    if title:
        log("页面标题：%s" % title)
    ab.wait(5000)

    log("向下滚动 %d 次，等评论按需加载……" % max_scrolls)
    for i in range(max_scrolls):
        ab.scroll_bottom()
        ab.wait(2500)
    ab.wait(3000)

    target = None
    if request_id:
        target = request_id
        log("使用指定的 requestId：%s" % target)
    else:
        reqs = ab.json_requests()
        if not reqs:
            raise SkillError("没有捕获到任何请求。页面可能没加载成功。")
        pat = None
        if want_platform in PLATFORMS:
            pat = re.compile(PLATFORMS[want_platform]["pattern"], re.I)
        cands = []
        for r in reqs:
            u = r.get("url") or ""
            if "application/json" not in (r.get("mimeType") or ""):
                continue
            if pat and pat.search(u):
                cands.append(r)
        if not cands:
            raise SkillError(
                "没在页面发出的请求里找到评论接口（平台=%s）。\n"
                "  可能的原因：\n"
                "    ① 该站点把评论拦住了 —— 页面自己都没拿到，旁观自然也没有；\n"
                "    ② 评论不走前端接口（服务端直出），该走 DOM 路线；\n"
                "    ③ 接口名变了，平台预设没命中。\n"
                "  下一步依次试：\n"
                "    a) 先看全部 JSON 接口，人工挑一个：\n"
                "       python %s %s --list\n"
                "    b) 服务端直出的页面，直接用整页文本（评论就在里面）：\n"
                "       agent-browser get text body\n"
                "    c) 页面自己都拿不到时（登录墙），见手册「登录态复用」一节。"
                % (want_platform or "自动", os.path.basename(sys.argv[0]), url))
        # 优先挑 URL 里带 main/page/list 的（多半是列表接口而非描述接口）
        cands.sort(key=lambda r: (0 if re.search(r"(main|page|list|comments)", r.get("url") or "", re.I) else 1))
        target = cands[0].get("requestId")
        log("命中评论接口：%s" % (cands[0].get("url") or "")[:120])

    body = ab.request_body(target)
    if not body:
        raise SkillError(
            "拿到了接口 %s，但取不到响应体。\n"
            "  常见原因：该请求在停止前还没返回 —— 试着把 --max-scrolls 调大。" % target)

    if raw:
        log("")
        log("===== 原始响应体（前 4000 字）=====")
        log(body[:4000])
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(body)
            log("")
            log("原始响应体已写入：%s" % out_path)
        return 0

    try:
        payload = json.loads(body)
    except ValueError:
        raise SkillError(
            "响应体不是 JSON（前 200 字）：%s\n"
            "  这条多半不是评论接口，换一条重试（先跑 --list）。" % body[:200])

    rows = dedup(extract_comments(payload))
    if not rows:
        raise SkillError(
            "接口拿到了、也是 JSON，但没能从里面认出评论条目。\n"
            "  下一步：用 `--raw --request-id %s` 看原始结构，判断是否换接口。" % target)

    result = {
        "source_url": url,
        "page_title": title,
        "platform": want_platform or "auto",
        "request_id": target,
        "count": len(rows),
        "comments": rows,
    }

    log("")
    log("取到 %d 条评论（已按 (作者,正文) 去重、按赞数降序）：" % len(rows))
    log("")
    for r in rows[:15]:
        like = "" if r.get("like") is None else "%s 赞" % r["like"]
        who = r.get("author") or "（无作者）"
        log("  [%s] %s：%s" % (like, who, r["text"][:64].replace("\n", " ")))
    if len(rows) > 15:
        log("  …… 其余 %d 条见输出文件" % (len(rows) - 15))

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log("")
        log("已写入：%s" % out_path)
    else:
        log("")
        log("（加 --out comments.json 可把完整结果落盘）")
    return 0


# ---------------------------------------------------------------- 参数与入口

def doctor(log):
    """环境自检：不联网，只报依赖状态。"""
    ok = True
    log("agent-browser 环境自检")
    log("=" * 58)

    try:
        cmd = find_agent_browser()
        log("[通过] agent-browser：%s" % " ".join(cmd[-2:]))
        # 上限给短一点：若走的是 npx 兜底，这一步可能尝试联网下载，不该拖太久
        rc, out = run(list(cmd) + ["--version"], timeout=20)
        log("       版本：%s" % (out.strip().splitlines() or ["?"])[0][:60])
    except SkillError as e:
        ok = False
        log("[失败] %s" % e)
        cmd = None

    chrome = find_chrome()
    if chrome:
        log("[通过] Chrome/Chromium：%s" % chrome)
    else:
        ok = False
        log("[失败] 没找到 Chrome/Chromium。两条出路：")
        log("       ① npx agent-browser install   （若从 Google CDN 下载超时，换镜像：")
        log("          https://registry.npmmirror.com/-/binary/chrome-for-testing/ ）")
        log("       ② 设 AGENT_BROWSER_EXECUTABLE_PATH 指向本机已有的 Chrome")

    node = shutil.which("node") or shutil.which("node.exe")
    log("[%s] Node.js：%s" % ("通过" if node else "提醒", node or "未找到（用 npx 方式时需要它）"))

    log("=" * 58)
    log("结论：%s" % ("依赖齐备，可以取评论" if ok else "依赖不全，按上面提示补齐"))
    return 0 if ok else 1


def build_parser():
    ap = argparse.ArgumentParser(
        prog="fetch_social_comments.py",
        description="用真实浏览器旁观页面自己发出的评论接口（不做签名逆向）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="帖子/视频/笔记的页面地址")
    ap.add_argument("--platform", default=None,
                    help="平台预设：%s" % "、".join(sorted(PLATFORMS)) + "（默认按域名自动判断）")
    ap.add_argument("--max-scrolls", type=int, default=8,
                    help="向下滚动次数，评论按需加载（默认 8）")
    ap.add_argument("--out", default=None, help="评论结果写入的 JSON 路径")
    ap.add_argument("--state", default=None,
                    help="复用自己的登录态文件（需自备；见手册「登录态复用」一节）")
    ap.add_argument("--list", dest="do_list", action="store_true",
                    help="只列出页面发出的 JSON 接口，不解析")
    ap.add_argument("--request-id", default=None,
                    help="直接指定接口的 requestId（配合 --list 使用）")
    ap.add_argument("--raw", action="store_true",
                    help="打印原始响应体（调试用）")
    ap.add_argument("--doctor", action="store_true",
                    help="环境自检，不联网")
    ap.add_argument("--session", default=None, help="agent-browser 会话名")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印底层命令")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)

    def log(s=""):
        print(s)

    if args.doctor:
        try:
            return doctor(log)
        except SkillError as e:
            log("失败：%s" % e)
            return 1

    if not args.url:
        ap.error("需要给出 url（或用 --doctor 自检环境）")
    if args.max_scrolls < 0:
        ap.error("--max-scrolls 不能为负数")
    if args.platform and args.platform not in PLATFORMS:
        ap.error("--platform 只支持：%s" % "、".join(sorted(PLATFORMS)))

    platform = args.platform or guess_platform(args.url)
    if platform is None and not args.request_id:
        log("提醒：没认出这是什么平台，将做通用匹配。"
            "认不出接口时用 --list 手动挑。")

    try:
        cmd = find_agent_browser()
        chrome = find_chrome()
        if chrome is None:
            raise SkillError(
                "没找到 Chrome/Chromium。先跑 `--doctor` 看完整清单，"
                "或设 AGENT_BROWSER_EXECUTABLE_PATH 指向本机 Chrome。")
        ab = Ab(cmd, chrome, state=args.state, session=args.session,
                verbose=args.verbose)
        ab.close_all()
        try:
            if args.do_list:
                return list_mode(ab, args.url, platform, args.max_scrolls, log)
            return comments_mode(ab, args.url, platform, args.max_scrolls,
                                 args.out, args.raw, args.request_id, log)
        finally:
            ab.close_all()
    except SkillError as e:
        print("")
        print("失败：%s" % e)
        return 3
    except KeyboardInterrupt:
        print("")
        print("已中断。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
