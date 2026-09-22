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
import sys
import re
import json
import time
import random
import hashlib
import urllib.request
import urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# B站前端固定的 64 位混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _get(url, referer="https://www.bilibili.com/"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get_wbi_keys():
    """未登录也会返回 img_key / sub_key（code=-101 是正常的）。"""
    d = _get("https://api.bilibili.com/x/web-interface/nav")
    wbi = (d.get("data") or {}).get("wbi_img") or {}
    img_key = wbi["img_url"].rsplit("/", 1)[1].split(".")[0]
    sub_key = wbi["sub_url"].rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


def mixin_key(img_key, sub_key):
    orig = img_key + sub_key
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
    dd = d["data"]
    st = dd.get("stat") or {}
    print("标题:", dd.get("title"))
    print("UP主:", (dd.get("owner") or {}).get("name"))
    print("发布:", time.strftime("%Y-%m-%d %H:%M", time.localtime(dd.get("pubdate", 0))))
    print("时长: %ss" % dd.get("duration"))
    print("播放: %s  点赞: %s  投币: %s  收藏: %s  评论: %s" % (
        st.get("view"), st.get("like"), st.get("coin"), st.get("favorite"), st.get("reply")))
    print("简介:", (dd.get("desc") or "").strip()[:300])
    print("aid=%s bvid=%s" % (dd.get("aid"), dd.get("bvid")))


def cmd_comments(bvid, pages=1):
    d = _get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
    if d.get("code") != 0:
        print("!! 拿不到 aid:", d.get("message"))
        return
    aid = d["data"]["aid"]

    img_key, sub_key = get_wbi_keys()
    offset = ""
    for page in range(pages):
        p = sign({"oid": aid, "type": 1, "mode": 3, "plat": 1,
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


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    arg = sys.argv[2]
    if cmd == "info":
        cmd_info(arg)
    elif cmd == "comments":
        pages = 1
        if "--pages" in sys.argv:
            pages = int(sys.argv[sys.argv.index("--pages") + 1])
        cmd_comments(arg, pages)
    elif cmd == "search":
        cmd_search(arg)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
