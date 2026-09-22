# Smart Buy Research · 全网口碑调研与购买决策

一个给 AI Agent 用的 **Skill**：把「买什么」从「看商家详情页」降级为「看真实用户在说什么、厂商资质是否经得起查」。

> **核心立场**：商家的详情页是营销材料，用户的抱怨才是产品说明书。

---

## 它解决什么问题

问 AI「XX 值得买吗」，最常见的失败模式是：它去搜一圈，把**今日头条、百家号、评测聚合站**的洗稿内容当成「用户共识」，然后给你一份看起来很专业、但依据是空的推荐。

这个 Skill 的做法是：

- **先问要不要买，再问买哪个** —— 大量消费决策的错误不在于选错型号，而在于根本不需要
- **差评比好评值钱** —— 好评的分辨成本极高（刷单/返现/水军），差评的信息密度极高
- **资质不查不下结论** —— 涉及「厂商」「认证」必须先过官方平台
- **结论必须能追溯到来源** —— 每条判断挂上「谁说的、在哪说的、什么时候」

## 它有什么不一样

| 常见做法 | 本 Skill 的做法 |
|---|---|
| 直接取搜索结果前几条 | **黑名单过滤 + 同源去重 + 强制至少一个垂直社区来源** |
| 泛泛「网上说」 | 标注来源类型：`（B站拆解实测）` `（样本不足）` `（仅摘要）` |
| 输出七章长文 | **默认 400 字以内，四块结构**（结论 / 理由 / 价格 / 一个坑） |
| 遇到反爬就放弃或硬编 | **实测过的可读性速查表 + 分级降级路径** |
| 忽略「其实不用买」 | **必要性拷问**作为独立步骤 |

---

## 安装

这是一个标准的 Agent Skill（`SKILL.md` + `references/` + `scripts/`）。

```bash
# 用户级安装（对所有项目生效）
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.workbuddy/skills/smart-buy-research-4-2
```

Windows：

```powershell
git clone https://github.com/ChaLunRon/smart-buy-research.git `
  "$env:USERPROFILE\.workbuddy\skills\smart-buy-research-4-2"
```

装好后 Agent 会在遇到购物决策类问题时自动加载。也可手动指定 `/smart-buy-research-4-2`。

## 使用

直接用自然语言触发，无需特殊命令：

```
预算 6000，大一计算机专业，买笔记本，值不值？
XX 和 YY 哪个好？
这牌子的保健品靠谱吗？（危重型 → 会强制走资质核验）
这个测评是不是恰饭的？
我已经买了 XX，帮我看看有没有踩坑
想买 XX 但总觉得不太需要（必要性拷问）
```

**不触发**：纯知识问答（"什么是 OLED"）、纯参数查询、金融产品研究。

### 输出长这样

> **买 ThinkBook 14+ 2026，5000-6500 档。**
>
> 理由：
> - 32G+1T 的配置四年不用换，接口全（有网口，宿舍网络差时很有用）
> - 计算机专业的内存是刚需，这个价位它是标配最全的
> - 做工公差比同价位稳定
>
> 到手约 ¥5xxx，京东自营。
>
> **坑**：网卡可能随机装配廉价型号（掉线），买前问清是不是 Intel 网卡。

要详细版就在追问里说「详细说说」「给我一份报告」。

---

## 目录结构

```
.
├── SKILL.md                        # 技能主体（Agent 加载入口，393 行）
├── references/                     # 按需加载的方法论（不进上下文）
│   ├── methodology.md              # Step 1–5 完整工作流
│   ├── sources-map.md              # 垃圾源黑名单 + 信息源地图 + 垂直社区对照表
│   ├── scraping-playbook.md        # 受限平台获取方案（无头浏览器 / API / 反爬）
│   ├── price-and-channel.md        # 四平台比价 + 优惠券 + 国补 + 三包
│   ├── review-analysis.md          # 水军识别 + 好评/差评读法 + 必要性分析
│   ├── category-cheatsheets.md     # 品类专属避坑小抄
│   ├── official-registries.md      # 官方资质核验平台清单
│   └── report-template.md          # 报告文件模板
└── scripts/                        # 可执行脚本（不占上下文）
    ├── price_tracker.py            # 到手价对比（标价陷阱/会员价/国补/单次成本）
    ├── fetch_wechat_article.py     # 微信公众号正文提取（免登录）
    └── fetch_bilibili.py           # B站数据获取（含 WBI 签名实现）
```

## 脚本用法

```bash
# 记录一条价格
python scripts/price_tracker.py add --item "XX笔记本" --channel "京东自营" \
  --list 6799 --coupon 200 --promo 100 --subsidy-amount 975

# 生成比价表
python scripts/price_tracker.py report --input records.json

# 抓微信公众号正文
python scripts/fetch_wechat_article.py "https://mp.weixin.qq.com/s/xxxxx"

# 拿 B站视频信息 / 评论（评论走 WBI 签名）
python scripts/fetch_bilibili.py info BV1GJ411x7h7
python scripts/fetch_bilibili.py comments BV1GJ411x7h7
```

三个脚本均为**纯标准库**实现，无需 `pip install`。

---

## 平台可读性实测

**很多「读不到」其实只是少了真实浏览器。** 本 Skill 内置了实测结论：

| 平台 | 纯 HTTP | 无头浏览器 | 结论 |
|---|---|---|---|
| **B站** | 视频信息 API ✅；搜索/评论 ❌ | ✅ | **可读**（评论需 WBI 签名） |
| **NGA** | ❌ 403 | ✅ | **完全可读** |
| **微信公众号** | ✅ 直连可读正文 | ✅ | **可读**（免登录免爬虫） |
| **小红书** | ❌ 302 跳登录 | ❌ IP 级风控 | 取决于你的网络环境 |

降级顺序：`换源 → 换检索形态 → 无头浏览器 → 爬虫 → 用户协作`。**不要一上来就爬。**

> ⚠️ 爬取受限平台前必须取得用户明确同意并说明账号风险。本 Skill 明确禁止未经同意的爬取，也禁止帮助规避平台规则。

---

## 依赖

- **必需**：一个能读网页的 Agent 运行时（Claude / WorkBuddy 等）
- **脚本**：Python 3.8+，纯标准库
- **可选**：无头浏览器（用于 NGA、B站评论等场景）
  ```bash
  npm i agent-browser
  npx agent-browser install        # 首次需下载 Chrome for Testing（约 196 MB）
  ```

## 已知限制

- **不替代专业检测。** 安全关键品类（儿童安全座椅、医疗器械、燃气具）只给方向性建议，以官方认证与检测报告为准。
- **不提供医疗建议。** 健康相关只做消费层面判断（成分、资质、性价比）。
- **平台可读性会被平台方单方面改变。** 表里的结论是实测时点的情况，失效时以「换源优先」为准。
- **垂直社区样本量小。** 结论中会标注「垂直社区观点，样本有限」。

## 贡献

欢迎提交 Issue 补充垂直社区、更新平台可读性实测、修正过时信息。

## License

[MIT](./LICENSE) © Contributors
