# Smart Buy Research · 全网口碑调研与购买决策

<p>
  <img alt="version" src="https://img.shields.io/badge/version-5.1-blue">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-yellow">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-none-brightgreen">
  <img alt="agent skills" src="https://img.shields.io/badge/Agent%20Skills-compatible-purple">
</p>

一个给 AI Agent 用的 **Skill**：把「买什么」从「看商家详情页」降级为「看真实用户在说什么、厂商资质是否经得起查」。

> **核心立场**：商家的详情页是营销材料，用户的抱怨才是产品说明书。

**为什么值得一看**：这个仓库解决的问题不是「搜不到」，而是「搜到的全是洗稿」。
它用一套可执行的纪律（黑名单、垂直社区定位、交叉验证、资质核验、反水军特征库）
把购物推荐从「看起来很专业」拉回「依据经得起查」。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [它有什么不一样](#它有什么不一样)
- [快速开始](#快速开始)
- [安装](#安装)
- [使用](#使用)
- [项目结构](#项目结构)
- [脚本用法](#脚本用法)
- [平台可读性实测](#平台可读性实测)
- [版本命名规则](#版本命名规则)
- [依赖](#依赖)
- [已知限制](#已知限制)
- [贡献与安全](#贡献与安全)
- [致谢](#致谢)
- [License](#license)

---

## 它解决什么问题

问 AI「XX 值得买吗」，最常见的失败模式是：它去搜一圈，把**今日头条、百家号、评测聚合站**的洗稿内容当成「用户共识」，然后给你一份看起来很专业、但依据是空的推荐。

这个 Skill 的做法是：

- **先问要不要买，再问买哪个** —— 大量消费决策的错误不在于选错型号，而在于根本不需要
- **差评比好评值钱** —— 好评的分辨成本极高（刷单/返现/水军），差评的信息密度极高
- **资质不查不下结论** —— 涉及「厂商」「认证」必须先过官方平台，且官方站打不开时有降级预案
- **优惠信息要能核对** —— 国补等补贴有明确的**品类门槛与按件封顶**；脚本按封顶截断，并对超门槛、非目录品类、金额与比例冲突发出告警

## 它有什么不一样

| 常见做法 | 本 Skill 的做法 |
|---|---|
| 直接取搜索结果前几条 | **黑名单过滤 + 同源去重 + 强制至少一个垂直社区来源** |
| 泛泛「网上说」 | 标注来源类型：`（B站拆解实测）` `（样本不足）` `（仅摘要）` |
| 输出七章长文 | **默认 400 字以内，四块结构**（结论 / 理由 / 价格 / 一个坑） |
| 遇到反爬就放弃或硬编 | **实测过的可读性速查表 + 分级降级路径** |
| 忽略「其实不用买」 | **必要性拷问**作为独立步骤 |
| 「标价 ×15% 就是国补」 | 按 **两条通道 + 品类门槛 + 按件封顶** 计算，超门槛/非目录品类/金额冲突均告警 |

---

## 快速开始

**最快路径**：把本技能目录放进运行时的技能搜索路径，然后用自然语言提问。

```bash
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.workbuddy/skills/smart-buy-research-5-1
```

装好后直接说人话：

```
预算 6000，大一计算机专业，买笔记本，值不值？
```

Agent 会自动加载本技能。要详细版就在追问里说「详细说说」「给我一份报告」。
各运行时的详细安装与排错见 [docs/getting-started.md](./docs/getting-started.md)。

## 安装

这是一个标准的 Agent Skill（`SKILL.md` + `references/` + `scripts/`），遵循
[Agent Skills 规范](https://agentskills.io/specification)。

> **安装目录名必须与 `SKILL.md` 里的 `name` 字段完全一致**（`smart-buy-research-5-1`），
> 这是规范要求，否则校验不通过。注意 `name` 里**不能出现点号**，
> 所以版本 `5.1` 写作 `5-1`。

```bash
# 用户级安装（对所有项目生效，macOS / Linux）
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.workbuddy/skills/smart-buy-research-5-1
```

Windows：

```powershell
git clone https://github.com/ChaLunRon/smart-buy-research.git `
  "$env:USERPROFILE\.workbuddy\skills\smart-buy-research-5-1"
```

也可手动指定 `/smart-buy-research-5-1` 调用。**Claude Code 及其他 Agent 的安装方式**
（marketplace / Cursor / Windsurf / Codex / Copilot）见
[docs/getting-started.md](./docs/getting-started.md)。

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
> **坑**：网卡可能随机装配廉价型号（掉线），买前问清是不是 Intel 网卡；万一中招，自己换一块约 70-100 元。

要详细版就在追问里说「详细说说」「给我一份报告」。

---

## 项目结构

本仓库的目录划分遵循 Agent Skills 的**三层披露**原则：
只把每次都用得到的放进 `SKILL.md`，其余按需加载。
设计理由与改动决策树见 [docs/skill-anatomy.md](./docs/skill-anatomy.md)。

| 层 / 目录 | 路径 | 作用 |
|---|---|---|
| 主入口 | `SKILL.md` | 工作流主干、不可协商原则、能力边界（**< 500 行**） |
| 方法论 | `references/`（8 个文件） | 按需加载的详细方法，不进默认上下文 |
| 可执行 | `scripts/`（3 个脚本） | 确定性计算与网络抓取，纯标准库 |
| 示例 | `examples/usage.md` | 5 个场景的完整输入 → 输出 |
| 文档 | `docs/` | 面向贡献者的安装、排错、结构说明 |
| 治理 | `.github/` | Issue / PR 模板 |
| 元数据 | `README.md` `CONTRIBUTING.md` `SECURITY.md` `CHANGELOG.md` `CITATION.cff` `LICENSE` `AGENTS.md` `CODE_OF_CONDUCT.md` `THIRD_PARTY_NOTICES.md` | 开源仓库标准治理文件 |
| 环境 | `.editorconfig` `.gitattributes` `.gitignore` | 统一行尾 LF / UTF-8，防止跨平台 diff 噪音 |

```
smart-buy-research-5-1/
├── SKILL.md                        # 技能主体（Agent 加载入口，约 400 行）
├── references/                     # 按需加载的方法论（不进上下文）
│   ├── methodology.md              # Step 1–5 完整工作流
│   ├── sources-map.md              # 垃圾源黑名单 + 信息源地图 + 垂直社区对照表
│   ├── scraping-playbook.md        # 受限平台获取方案（无头浏览器 / API / 反爬）
│   ├── price-and-channel.md        # 四平台比价 + 优惠券 + 国补（两条通道/封顶）+ 三包
│   ├── review-analysis.md          # 水军识别 + 好评/差评读法 + 必要性分析
│   ├── category-cheatsheets.md     # 品类专属避坑小抄
│   ├── official-registries.md      # 官方资质核验平台清单
│   └── report-template.md          # 报告文件模板
├── scripts/                        # 可执行脚本（不占上下文）
│   ├── price_tracker.py            # 到手价对比（标价陷阱/会员价/国补/单次成本）
│   ├── fetch_wechat_article.py     # 微信公众号正文提取（免登录）
│   └── fetch_bilibili.py           # B站数据获取（含 WBI 签名实现）
├── examples/
│   └── usage.md                    # 5 个场景示例（含「过程中发生了什么」）
├── docs/
│   ├── getting-started.md          # 各运行时安装与排错
│   └── skill-anatomy.md            # 技能结构与规范（改内容前必读）
├── .github/
│   ├── ISSUE_TEMPLATE/             # Bug / 内容纠错 / 平台可读性 / 功能建议 四类模板
│   └── PULL_REQUEST_TEMPLATE.md
├── README.md                       # 本文件
├── CONTRIBUTING.md                 # 贡献指南（含版本命名规则）
├── SECURITY.md                     # 安全政策（含提示注入风险说明）
├── CODE_OF_CONDUCT.md              # 贡献者公约（含本项目特有红线）
├── AGENTS.md                       # 给 AI 编码代理的仓库说明
├── CHANGELOG.md                    # v1 → 5.1 版本演进
├── CITATION.cff                    # 引用元数据
├── THIRD_PARTY_NOTICES.md          # 第三方声明（本项目无第三方代码依赖）
├── LICENSE                         # MIT
├── .editorconfig                   # 统一行尾 LF / UTF-8
├── .gitattributes                  # 行尾规范化 + 二进制标记
└── .gitignore
```

## 版本命名规则

采用 **`主版本.次版本`** 两级编号，但目录名与 `name` 字段要满足规范字符集：

| 变更性质 | 版本动作 | 示例 |
|---|---|---|
| 修正错字、死链、过期平台实测、错别信息 | 次版本 +1 | `5.1` → `5.2` |
| 新增能力、改变输出结构或判断纪律 | 大版本 +1 | `5.2` → `9.0` |

| 场合 | 写法 | 原因 |
|---|---|---|
| 文档正文、`metadata.version` | `5.1` | 标准版本写法，可读 |
| `name` 字段、目录名 | `smart-buy-research-5-1` | 规范只允许小写字母/数字/连字符，**点号非法** |

## 脚本用法

```bash
# 记录一条价格（国补金额须是能核对出来的真实值，不要用标价×15%硬算）
python scripts/price_tracker.py add --item "XX笔记本" --channel "京东自营" \
  --list 5499 --coupon 200 --promo 100 --subsidy-rate 0.15 --subsidy-included \
  --note "已核实国补资格"

# 生成比价表
python scripts/price_tracker.py report --input records.json

# 抓微信公众号正文（低频、单篇；robots.txt 禁止程序化访问，勿批量）
python scripts/fetch_wechat_article.py "https://mp.weixin.qq.com/s/xxxxx"

# 拿 B站视频信息 / 评论（评论走 WBI 签名）
python scripts/fetch_bilibili.py info BV1GJ411x7h7
python scripts/fetch_bilibili.py comments BV1GJ411x7h7 --pages 2 --mode 2   # mode 2 = 按时间
```

三个脚本均为**纯标准库**实现，无需 `pip install`。参数错误时给中文提示
并以退出码 `2` 结束，不打印 traceback。

**参数校验与报错**：三个脚本都支持 `--help`，参数错误时给中文提示而不是抛栈。

```bash
python scripts/fetch_bilibili.py --help
# fetch_bilibili.py comments BV1GJ411x7h7 --pages 99
#   → 最多 20 页（收到 99），避免触发风控

python scripts/price_tracker.py report --input no_such.json
#   → 错误：找不到文件：no_such.json
python scripts/price_tracker.py report < bad.json
#   → 错误：JSON 解析失败（第 1 行第 2 列）：Expecting property name...
#   → 错误：第 1 条缺少必需字段：channel、list_price
```

`report` 的输入 JSON 必须是非空数组，每条至少含 `item` / `channel` / `list_price` 三个字段——
可用 `price_tracker.py add --out records.json` 自动生成符合格式的文件。

---

## 平台可读性实测

**很多「读不到」其实只是少了真实浏览器。** 本 Skill 内置了实测结论：

| 平台 | 纯 HTTP | 无头浏览器 | 结论 |
|---|---|---|---|
| **B站** | 视频信息 API ✅；评论 ⚠️ 需 WBI 签名（已实现）；搜索 ❌ HTTP 412 风控 | ✅ | **可读**（搜索改用浏览器） |
| **NGA** | ❌ 403 | ✅ | **完全可读** |
| **微信公众号** | ✅ 直连可读正文 | ✅ | **可读**（免登录免爬虫） |
| **小红书** | ❌ 302 跳登录 | ❌ IP 级风控 | **本机网络下不可读**，只能换网络/用户协作 |

**微信文章的注意点**：单篇直连可读，但 `mp.weixin.qq.com/robots.txt` 禁止爬虫，
高频请求会触发验证码 —— **必须低频**，不要批量抓。

降级顺序：`换源 → 换检索形态 → 无头浏览器 → 爬虫 → 用户协作`。**不要一上来就爬。**

> ⚠️ 爬取受限平台前必须取得用户明确同意并说明账号风险。本 Skill 明确禁止未经同意的爬取，也禁止帮助规避平台规则。

---

## 依赖

- **必需**：一个能读网页的 Agent 运行时（Claude / WorkBuddy 等）
- **脚本**：Python 3.8+，纯标准库
- **强烈建议**：无头浏览器。**不装的话，NGA 完全读不到，B站搜索页也读不到**
  （这两处只有浏览器路径），只能走降级方案（标注"仅摘要"或请用户自行查看）
  ```bash
  npm i agent-browser
  npx agent-browser install        # 首次需下载 Chrome for Testing（约 196 MB）
  ```
- **不可用**：小红书在本技能实测环境下受 IP 级风控拦截，浏览器也读不到，
  只能换网络环境或由用户协助提供内容

## 已知限制

- **不替代专业检测。** 安全关键品类（儿童安全座椅、医疗器械、燃气具）只给方向性建议，以官方认证与检测报告为准。
- **不提供医疗建议。** 健康相关只做消费层面判断（成分、资质、性价比）。
- **平台可读性会被平台方单方面改变。** 表里的结论是实测时点的情况，失效时以「换源优先」为准。
- **垂直社区样本量小。** 结论中会标注「垂直社区观点，样本有限」。
- **国补政策具有时效性。** 品类目录、门槛与封顶金额随政策调整，以官方最新公告为准。

## 贡献与安全

- **贡献指南**：[CONTRIBUTING.md](./CONTRIBUTING.md) —— 四类常见贡献（平台实测更新、垂直社区修正、
  事实纠错、脚本加固）、PR 流程、版本命名规则、内容红线
- **安全政策**：[SECURITY.md](./SECURITY.md) —— 脚本的网络行为、平台账号风险、
  **提示注入（prompt injection）缓解措施**、私密报告渠道
- **贡献者公约**：[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
- **给 AI 代理的说明**：[AGENTS.md](./AGENTS.md)
- **第三方声明**：[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) —— 本项目**无第三方代码依赖**，
  仅列出文档中提及的第三方服务与政策信息来源

开 Issue 请用模板（[Bug](.github/ISSUE_TEMPLATE/bug_report.md) /
[内容纠错](.github/ISSUE_TEMPLATE/content_correction.md) /
[平台可读性](.github/ISSUE_TEMPLATE/platform_readability.md) /
[功能建议](.github/ISSUE_TEMPLATE/feature_request.md)）。
**安全问题请勿开公开 Issue。**

## 致谢

本项目的设计吸收了以下开源项目的公开做法：

- [anthropics/skills](https://github.com/anthropics/skills) —— Agent Skills 官方规范与示例，
  本仓库的三层披露结构与 frontmatter 约束以其为准
- [obra/superpowers](https://github.com/obra/superpowers) —— 技能即方法论的思路，
  以及跨 Agent 兼容的组织方式
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) —— 仓库级治理文件的完整度
  （`AGENTS.md`、`.gitattributes`、`docs/`、层级化的项目结构说明）

**本仓库不包含上述项目的任何代码**，仅在设计与文件组织上参考了公开可见的做法。

## 引用

若在论文或项目中引用本 Skill，见 [CITATION.cff](./CITATION.cff)。

## License

[MIT](./LICENSE) © ChaLunRon and Smart Buy Research Contributors
