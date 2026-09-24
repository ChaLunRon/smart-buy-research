# -*- coding: utf-8 -*-
"""
B站数据获取（免登录）—— 视频信息 / 评论 / 搜索。

为什么需要这个脚本：
  B站评论接口 x/v2/reply/wbi/main 现在必须带 WBI 签名（w_rid + wts），
  没有签名会返回 -352，这就是"老爬虫全挂"的原因。本脚本实现了签名。

用法:
    python fetch_bilibili.py info  BV1GJ411x7h7
    python fetch_bilibili.py comments BV1GJ411x7h7 [--pages 2]
    python fetch_bilibili.py search "笔记本 推荐"      # 走浏览器搜索页，更可靠
"""
import argparse
import sys
import re
import json
import time
import random
import hashlib
import urllib.request
import urllib.parse
import urllib.error


class FetchError(Exception):
    """网络或接口层面可预期的失败（转成友好提示，不打印栈）。"""


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# 单次 HTTP 请求超时（秒）。见 _get() 中的说明。
REQUEST_TIMEOUT = 25

# B站前端固定的 64 位混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _get(url, referer="https://www.bilibili.com/"):
    """GET 一个 JSON 接口。网络/解析失败时抛 FetchError（由 main 转成友好提示）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    # 25s：B站接口在跨境/弱网下偶有长尾延迟，过短会误判为「读不到」，
    # 过长则会在风控静默丢包时卡死。25s 是实测的折中值。
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 412:
            # 注意：这是 **HTTP 状态码 412**（内容风控层拒绝，返回非 JSON），
            # 与接口体内的业务错误码 code=-412 不是一回事。
            # WBI 签名**解决不了** HTTP 412——签名只对评论接口有效，
            # 搜索接口的 412 属于风控，需要带 Cookie。别照"补签名"这条错路排查。
            raise FetchError(
                "接口返回 HTTP 412（内容风控拒绝，非签名问题）：%s\n"
                "  这是平台风控层拦截，WBI 签名无效。\n"
                "  可行路径：改用浏览器读取页面文本（见 search 子命令的输出）。" % url)
        raise FetchError("接口返回 HTTP %s（%s）" % (e.code, url))
    except urllib.error.URLError as e:
        raise FetchError("网络请求失败（%s）：%s\n"
                         "  排查：能否访问 bilibili.com？是否需要代理？"
                         % (url, getattr(e, "reason", e)))
    except (TimeoutError, OSError) as e:
        raise FetchError("请求超时或中断（%s）：%s" % (url, e))

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise FetchError("接口返回的不是 JSON（%s），可能被风控拦截。"
                         "前 120 字符：%s" % (url, body[:120].replace("\n", " ")))


def get_wbi_keys():
    """未登录也会返回 img_key / sub_key（code=-101 是正常的）。"""
    d = _get("https://api.bilibili.com/x/web-interface/nav")
    wbi = (d.get("data") or {}).get("wbi_img") or {}
    try:
        img_key = wbi["img_url"].rsplit("/", 1)[1].split(".")[0]
        sub_key = wbi["sub_url"].rsplit("/", 1)[1].split(".")[0]
    except (KeyError, IndexError):
        raise FetchError(
            "拿不到 WBI 密钥（nav 接口未返回 wbi_img）。\n"
            "  通常是被风控或接口改版；评论功能会不可用。\n"
            "  返回内容：%s" % str(d)[:150])
    return img_key, sub_key


def mixin_key(img_key, sub_key):
    """按前端固定混淆表重排 img_key + sub_key，取前 32 位。

    B站的 img_key / sub_key 都是 32 位十六进制（拼起来 64 位，正好对上
    0..63 的混淆表下标）。这里显式校验长度：万一接口改版返回了短密钥，
    原实现会抛出一句英文的 `IndexError: string index out of range`，
    与本技能「失败要有中文提示」的承诺不符，定位也很费劲。
    """
    orig = (img_key or "") + (sub_key or "")
    if len(orig) < max(MIXIN_KEY_ENC_TAB) + 1:
        raise FetchError(
            "WBI 密钥长度异常：img_key=%d 位、sub_key=%d 位（应为各 32 位）。\n"
            "  通常是 nav 接口返回内容被风控替换了。\n"
            "  处理：稍后重试；仍失败则改走浏览器读取页面文本。"
            % (len(img_key or ""), len(sub_key or "")))
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign(params, img_key, sub_key):
    mk = mixin_key(img_key, sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    # 过滤 !'()* 并按 key 排序
    params = {k: "".join(c for c in str(v) if c not in "!'()*")
              for k, v in sorted(params.items())}
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mk).encode()).hexdigest()
    return params


def cmd_info(bvid):
    d = _get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
    if d.get("code") != 0:
        print("!! 接口返回 code=%s msg=%s" % (d.get("code"), d.get("message")))
        return
    dd = d.get("data")
    if not isinstance(dd, dict):
        raise FetchError("接口返回 code=0 但没有 data 字段，可能被风控或接口改版")
    st = dd.get("stat") or {}
    print("标题:", dd.get("title"))
    print("UP主:", (dd.get("owner") or {}).get("name"))
    print("发布:", time.strftime("%Y-%m-%d %H:%M", time.localtime(dd.get("pubdate", 0))))
    print("时长: %ss" % dd.get("duration"))
    print("播放: %s  点赞: %s  投币: %s  收藏: %s  评论: %s" % (
        st.get("view"), st.get("like"), st.get("coin"), st.get("favorite"), st.get("reply")))
    print("简介:", (dd.get("desc") or "").strip()[:300])
    print("aid=%s bvid=%s" % (dd.get("aid"), dd.get("bvid")))


def cmd_comments(bvid, pages=1, mode=3):
    d = _get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
    if d.get("code") != 0:
        print("!! 拿不到 aid:", d.get("message"))
        return
    aid = (d.get("data") or {}).get("aid")
    if not aid:
        raise FetchError("拿不到视频 aid，无法查询评论：接口返回 %s"
                         % str(d)[:120])

    img_key, sub_key = get_wbi_keys()
    offset = ""
    for page in range(pages):
        p = sign({"oid": aid, "type": 1, "mode": mode, "plat": 1,
                  "pagination_str": json.dumps({"offset": offset}, separators=(",", ":")),
                  "web_location": "1315875"},
                 img_key, sub_key)
        url = "https://api.bilibili.com/x/v2/reply/wbi/main?" + urllib.parse.urlencode(p)
        d2 = _get(url, referer="https://www.bilibili.com/video/" + bvid)
        code = d2.get("code")
        if code != 0:
            print("!! 第 %d 页 code=%s msg=%s" % (page + 1, code, d2.get("message")))
            if code == -352:
                print("   -352 通常是签名失效或频率过高，稍后重试")
            elif code == -412:
                print("   -412 是限流，必须放慢频率")
            return
        data = d2.get("data") or {}
        replies = data.get("replies") or []
        print("\n=== 第 %d 页，%d 条 ===" % (page + 1, len(replies)))
        for r in replies:
            msg = ((r.get("content") or {}).get("message") or "").replace("\n", " ")
            print("  [%s赞] %s: %s" % (r.get("like"),
                                       (r.get("member") or {}).get("uname"), msg[:120]))
        cur = data.get("cursor") or {}
        if cur.get("is_end"):
            print("\n(已是最后一页)")
            break
        offset = ((cur.get("pagination_reply") or {}).get("next_offset")) or ""
        if not offset:
            break
        time.sleep(random.uniform(0.5, 1.5))


def cmd_search(keyword):
    print("# B站搜索接口无 Cookie 时会返回 -412 限流。")
    print("# 可靠做法：用浏览器打开下面的地址，再读取页面文本。")
    print()
    print("https://search.bilibili.com/all?keyword=" + urllib.parse.quote(keyword))
    print()
    print("agent-browser open '%s'" % ("https://search.bilibili.com/all?keyword=" + urllib.parse.quote(keyword)))
    print("agent-browser wait --load networkidle")
    print("agent-browser get text body")


class _PagesAction(argparse.Action):
    """校验 --pages 并给出中文报错（用 type=int 的话报错信息是英文的）。"""

    def __call__(self, parser, ns, values, option_string=None):
        try:
            n = int(values)
        except (TypeError, ValueError):
            raise argparse.ArgumentError(self, "必须是整数（收到 %r）" % (values,))
        if n < 1:
            raise argparse.ArgumentError(self, "必须是正整数（收到 %s）" % n)
        if n > 20:
            raise argparse.ArgumentError(
                self, "最多 20 页（收到 %s），避免触发风控" % n)
        setattr(ns, self.dest, n)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="fetch_bilibili.py",
        description="B站数据获取（免登录）：视频信息 / 评论 / 搜索。",
        epilog="例：fetch_bilibili.py comments BV1GJ411x7h7 --pages 2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", metavar="{info,comments,search}")

    p_info = sub.add_parser("info", help="取视频信息（标题/UP主/播放/点赞等）")
    p_info.add_argument("bvid", help="视频 BV 号，如 BV1GJ411x7h7")

    p_cmt = sub.add_parser("comments", help="取评论（走 WBI 签名）")
    p_cmt.add_argument("bvid", help="视频 BV 号")
    p_cmt.add_argument("--pages", action=_PagesAction, default=1,
                       help="抓取页数，默认 1，上限 20")
    p_cmt.add_argument("--mode", type=int, default=3, choices=(2, 3),
                       help="排序：2=按时间（找刷单/集中好评用这个），3=按热度（默认）")

    p_s = sub.add_parser("search", help="输出搜索页地址与浏览器命令")
    p_s.add_argument("keyword", help="搜索关键词")

    return ap


def main(argv=None):
    ap = build_parser()
    # argparse 在自定义 Action 抛 ArgumentError 时会把异常继续向上冒泡，
    # 用户会看到英文 traceback。统一兜住转中文 + 退出码 2。
    try:
        args = ap.parse_args(argv)
    except argparse.ArgumentError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2
    if not args.cmd:
        ap.print_help()
        return 1
    try:
        if args.cmd == "info":
            cmd_info(args.bvid)
        elif args.cmd == "comments":
            cmd_comments(args.bvid, args.pages, args.mode)
        elif args.cmd == "search":
            cmd_search(args.keyword)
    except FetchError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
