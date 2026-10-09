# -*- coding: utf-8 -*-
"""
微信公众号文章提取器 — 免登录、纯 HTTP。

已验证：浏览器 UA + 直接请求 https://mp.weixin.qq.com/s/<id> 即可拿到完整正文。

⚠️ 合规前提：
  mp.weixin.qq.com/robots.txt 的内容是 `User-Agent: * -> Disallow: /`，
  Allow 白名单不含 /s/。也就是说本脚本的请求路径在 robots.txt 层面是被
  明确禁止的。

  因此本脚本的定位是：**仅供用户本人低频读取自己有权访问的单篇文章**
  （不批量、不绕过验证、不并发）。批量抓取请改用授权渠道（自己的公众号
  后台导出、付费数据平台等）。

  调用方有义务在批量使用前取得用户明确同意，并说明这一限制。

用法:
    python fetch_wechat_article.py <url> [--json out.json]
"""
import argparse
import sys
import re
import json
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "identity",
}

# 命中这些说明被风控/文章失效。
# 注意：只在**正文容器缺失**时才会真正判定为被拦（见 extract()），
# 所以正常文章正文里出现这些词不会误报。标记本身仍要尽量具体——
# 「参数错误」这种通用词单独出现时歧义太大，改成完整串。
BLOCK_MARKERS = [
    "环境异常", "完成验证", "去验证", "点击验证",
    "参数错误，请返回首页", "该内容已被发布者删除", "此内容因违规无法查看",
    "该公众号已迁移", "请在微信客户端打开链接", "此内容发送失败无法查看",
]


class FetchError(Exception):
    """网络或页面层面可预期的失败（转成友好提示，不打印栈）。"""


def fetch(url, timeout=25):
    """拉取文章 HTML。失败时抛 FetchError 而不是裸的 URLError。"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FetchError("HTTP %s —— 链接可能已失效或被限制（%s）" % (e.code, url))
    except urllib.error.URLError as e:
        raise FetchError(
            "网络请求失败：%s\n"
            "  排查：能否访问 mp.weixin.qq.com？是否需要代理？" % getattr(e, "reason", e))
    except (TimeoutError, OSError) as e:
        raise FetchError("请求超时或中断：%s" % e)


def _unescape(s):
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&ldquo;", "“"), ("&rdquo;", "”")]:
        s = s.replace(a, b)
    return s


def extract(html):
    out = {"title": None, "author": None, "account": None,
           "publish_ts": None, "content": None, "blocked": None, "images": []}

    for m in BLOCK_MARKERS:
        # 只在正文容器缺失时才判定为被拦截
        if m in html:
            out["blocked"] = m

    for pat, key in [
        (r'var msg_title\s*=\s*[\'"](.*?)[\'"]', "title"),
        (r'property="og:title"\s+content="(.*?)"', "title"),
        (r'<h1[^>]*class="rich_media_title[^"]*"[^>]*>\s*<span[^>]*>(.*?)</span>', "title"),
    ]:
        m = re.search(pat, html, re.S)
        if m and not out[key]:
            out[key] = _unescape(m.group(1).strip())

    for pat, key in [
        (r'var nickname\s*=\s*[\'"](.*?)[\'"]', "account"),
        (r'var author\s*=\s*[\'"](.*?)[\'"]', "author"),
        (r'var ct\s*=\s*"(\d+)"', "publish_ts"),
    ]:
        m = re.search(pat, html, re.S)
        if m:
            out[key] = m.group(1).strip()

    m = re.search(
        r'<div[^>]*class="rich_media_content[^"]*"[^>]*>(.*?)</div>\s*(?:<script|<div class="rich_media_tool)',
        html, re.S)
    if not m:
        m = re.search(r'id="js_content"[^>]*>(.*?)</div>\s*<script', html, re.S)
    if m:
        inner = m.group(1)
        out["images"] = re.findall(r'data-src="([^"]+)"', inner)
        txt = re.sub(r"<br\s*/?>", "\n", inner)
        txt = re.sub(r"</p>", "\n", txt)
        txt = re.sub(r"<[^>]+>", "", txt)
        txt = _unescape(txt)
        txt = re.sub(r"[ \t\u00a0]+", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
        out["content"] = txt
        out["blocked"] = None  # 拿到正文就说明没被拦
    return out


def build_parser():
    ap = argparse.ArgumentParser(
        prog="fetch_wechat_article.py",
        description="微信公众号文章正文提取（免登录、免爬虫、纯 HTTP）。",
        epilog="例：fetch_wechat_article.py 'https://mp.weixin.qq.com/s/xxxx' --json rec.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("url", help="mp.weixin.qq.com/s/... 文章地址")
    ap.add_argument("--json", metavar="FILE", default=None,
                    help="把结果另存为 JSON 到 FILE")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)

    url = args.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        # 防止不是 URL 的输入掉进 urllib 抛 ValueError
        ap.error("url 必须以 http:// 或 https:// 开头（收到：%s）" % url)
    if "mp.weixin.qq.com" not in url:
        print("!! 警告：这不是 mp.weixin.qq.com 的链接，很可能提取不到正文。")

    try:
        rec = extract(fetch(url))
    except FetchError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2
    rec["url"] = url

    if rec.get("content"):
        print("=" * 60)
        print("标题:", rec.get("title"))
        print("公众号:", rec.get("account") or rec.get("author"))
        if rec.get("publish_ts"):
            import datetime
            print("发布:", datetime.datetime.fromtimestamp(int(rec["publish_ts"])))
        print("图片数:", len(rec.get("images") or []))
        print("=" * 60)
        print(rec["content"])
    else:
        print("!! 未能提取正文。blocked marker =", rec.get("blocked"))
        print("   可能原因：文章已删除 / 需要验证 / 链接不完整")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        print("\n[saved]", args.json)

    # 取不到正文必须给非零退出码：只打印警告就 return 0，
    # 调用方（Agent）按退出码判断时会把"没取到"误当成"取到了"。
    return 0 if rec.get("content") else 3


if __name__ == "__main__":
    sys.exit(main())
