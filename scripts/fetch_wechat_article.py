# -*- coding: utf-8 -*-
"""
微信公众号文章提取器 — 免登录、纯 HTTP。
已验证：浏览器 UA + 直接请求 https://mp.weixin.qq.com/s/<id> 即可拿到完整正文。

用法:
    python fetch_wechat_article.py <url> [--json out.json]
"""
import sys
import re
import json
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "identity",
}

# 命中这些说明被风控/文章失效
BLOCK_MARKERS = [
    "环境异常", "完成验证", "去验证", "点击验证",
    "参数错误", "该内容已被发布者删除", "此内容因违规无法查看",
    "该公众号已迁移",
]


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    rec = extract(fetch(url))
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

    if "--json" in sys.argv:
        i = sys.argv.index("--json")
        if i + 1 < len(sys.argv):
            with open(sys.argv[i + 1], "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            print("\n[saved]", sys.argv[i + 1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
