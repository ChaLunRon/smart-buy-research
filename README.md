# Smart Buy Research · 全网口碑调研与购买决策

<p>
  <img alt="version" src="https://img.shields.io/badge/version-5.9-blue">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-yellow">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-none-brightgreen">
  <img alt="agent skills" src="https://img.shields.io/badge/Agent%20Skills-compatible-purple">
  <img alt="tests" src="https://img.shields.io/badge/tests-120%20passing-brightgreen">
  <img alt="ci" src="https://github.com/ChaLunRon/smart-buy-research/actions/workflows/validate.yml/badge.svg">
</p>

一个给 AI Agent 用的 **Skill**：把「买什么」从「看商家详情页」降级为「看真实用户在说什么、厂商资质是否经得起查」。

> **核心立场**：商家的详情页是营销材料，用户的抱怨才是产品说明书。

它要解决的不是「搜不到」，而是**「搜到的全是洗稿」** —— 用一套可执行的纪律（黑名单、垂直社区定位、交叉验证、资质核验、反水军特征库），把购物推荐从「看起来很专业」拉回「依据经得起查」。

---

## 目录

**想用它**

- [它解决什么问题](#它解决什么问题)
- [它有什么不一样](#它有什么不一样)
- [安装](#安装)
- [使用](#使用)
- [平台可读性实测](#平台可读性实测)
- [脚本用法](#脚本用法)
- [依赖](#依赖)
- [已知限制](#已知限制)

**想改它 / 发版**

- [项目结构](#项目结构)
- [自检与测试](#自检与测试)
- [版本历史](#版本历史)
- [发布到 GitHub](#发布到-github)
- [贡献与安全](#贡献与安全)

**其它**

- [致谢](#致谢)
- [引用](#引用)
- [License](#license)

---

## 它解决什么问题

问 AI「XX 值得买吗」，最常见的失败模式是：它去搜一圈，把**今日头条、百家号、评测聚合站**的洗稿内容当成「用户共识」，然后给你一份看起来很专业、但依据是空的推荐。这个 Skill 的做法是：

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

## 安装

这是一个标准的 Agent Skill（`SKILL.md` + `references/` + `scripts/`），遵循
[Agent Skills 规范](https://agentskills.io/specification)。

```bash
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.workbuddy/skills/smart-buy-research-5-9
```

```powershell
# Windows
git clone https://github.com/ChaLunRon/smart-buy-research.git `
  "$env:USERPROFILE\.workbuddy\skills\smart-buy-research-5-9"
```

> - **目录名必须与 `SKILL.md` 里的 `name` 完全一致**（`smart-buy-research-5-9`），否则校验不通过。
>   `name` 里**不能出现点号**，所以版本 `5.9` 写作 `5-9`。
> - **不想用 git？** 到 [Releases](https://github.com/ChaLunRon/smart-buy-research/releases) 下载
>   `smart-buy-research-5-9.zip`，解压后整个目录放进技能目录即可（包里顶层目录名已正确，**不要改名**）。
> - **Fork 到自己账号下**要同步改署名、`metadata.author`、`CITATION.cff`、`LICENSE`、
>   所有 `github.com/<owner>/` 里的 owner 与邮箱；`tools/validate_skill.py` 第 12 项会清点残留占位符。

**其他运行时**（Claude Code marketplace / Cursor / Windsurf / Codex / Copilot）见
[docs/getting-started.md](./docs/getting-started.md)。

## 使用

直接用自然语言触发，无需特殊命令：

```
预算 6000，大一计算机专业，买笔记本，值不值？
XX 和 YY 哪个好？
这牌子的保健品靠谱吗？（危重型 → 会强制走资质核验）
这个测评是不是恰饭的？
想买 XX 但总觉得不太需要（必要性拷问）
```

**不触发**：纯知识问答（"什么是 OLED"）、纯参数查询、金融产品研究。

### 输出长这样

> **买 ThinkBook 14+ 2026，5000-6500 档。**
>
> - 32G+1T 的配置四年不用换，接口全（有网口，宿舍网络差时很有用）
> - 计算机专业的内存是刚需，这个价位它是标配最全的
>
> 到手约 ¥5xxx，京东自营。
>
> **坑**：网卡可能随机装配廉价型号（掉线），买前问清是不是 Intel 网卡；万一中招，自己换一块约 70-100 元。

要详细版就在追问里说「详细说说」「给我一份报告」。

---

## 平台可读性实测

**很多「读不到」其实只是少了真实浏览器。** 下表是 **2026-09 实测过的 4 个平台**：

| 平台 | 纯 HTTP | 无头浏览器 | 结论 |
|---|---|---|---|
| **B站** | 视频信息 API ✅；评论 ⚠️ 需 WBI 签名（已实现）；搜索 ❌ HTTP 412 风控 | ✅ | **可读**（搜索改用浏览器） |
| **NGA** | ❌ 403 | ✅ | **完全可读** |
| **微信公众号** | ✅ 直连可读正文 | ✅ | **可读**（免登录；但 `robots.txt` 禁爬，**必须低频、勿批量**） |
| **小红书** | ❌ 302 跳登录 | ❌ 风控拦截（`error_code=300012`） | **受限**：判定在**网络出口**层；换网络或请用户提供内容 |

> ⚠️ **没测过就不写「可读」。** 贴吧 / 知乎 / 微博**目前没有可读性实测记录** ——
> 它们不在上表内，而这张表也**不是**「所有平台」的全集。这三处按
> [references/sources-map.md](./references/sources-map.md) 的降级路径**现场试**，
> 实测成功也只算「本次实测」，不要援引本表当结论。

降级顺序：`换源 → 换检索形态 → 无头浏览器 → 爬虫 → 用户协作`。**不要一上来就爬。**
爬取受限平台前**必须取得用户明确同意并说明账号风险**；本 Skill 禁止未经同意的爬取，也禁止帮助规避平台规则。

---

## 脚本用法

```bash
# 记录一条价格（国补金额须是能核对出来的真实值，不要用标价×15%硬算）
python scripts/price_tracker.py add --item "XX笔记本" --channel "京东自营" \
  --list 5499 --coupon 200 --promo 100 --subsidy-rate 0.15 --subsidy-included

# 生成比价表（输入须是非空数组，每条至少含 item / channel / list_price）
python scripts/price_tracker.py report --input records.json

# 抓微信公众号正文（低频、单篇）
python scripts/fetch_wechat_article.py "https://mp.weixin.qq.com/s/xxxxx"

# 拿 B站视频信息 / 评论（评论走 WBI 签名）
python scripts/fetch_bilibili.py info BV1GJ411x7h7
python scripts/fetch_bilibili.py comments BV1GJ411x7h7 --pages 2 --mode 2   # mode 2 = 按时间
```

三个脚本均为**纯标准库**实现，无需 `pip install`；都支持 `--help`，参数错误时给**中文提示 + rc=2**、
**不打印 traceback**（例如 `--pages 99` 会被截到 20 并说明原因，避免触发风控）。

## 依赖

- **必需**：一个能读网页的 Agent 运行时（Claude / WorkBuddy 等）
- **脚本**：Python 3.8+，纯标准库（CI 矩阵**实跑** 3.8 / 3.9 / 3.12，不是「应该能跑」）
- **强烈建议**：无头浏览器。**不装的话 NGA 完全读不到，B站搜索页也读不到**（这两处只有浏览器路径）
  ```bash
  npm i agent-browser
  npx agent-browser install        # 首次需下载 Chrome for Testing（约 196 MB）
  ```

## 已知限制

- **不替代专业检测。** 安全关键品类（儿童安全座椅、医疗器械、燃气具）只给方向性建议，以官方认证与检测报告为准。
- **不提供医疗建议。** 健康相关只做消费层面判断（成分、资质、性价比）。
- **平台可读性会被平台方单方面改变。** 表里的结论是实测时点的情况，失效时以「换源优先」为准。
- **垂直社区样本量小。** 结论中会标注「垂直社区观点，样本有限」。
- **国补政策具有时效性。** 品类目录、门槛与封顶金额随政策调整，以官方最新公告为准。

---

**以下几节面向仓库维护者。** 只想用这个技能的话，上面已经讲完了 ——
下面只给入口，细节都在 `docs/` 与 `CHANGELOG.md` 里，放在这里只会把使用者要读的东西挤走。

## 项目结构

遵循 Agent Skills 的**三层披露**：只把每次都用得到的放进 `SKILL.md`，其余按需加载 ——
`references/`（8 个文件，方法论）· `scripts/`（3 个脚本）· `tests/`（4 个文件，120 个用例）·
`tools/validate_skill.py`（结构自检）· `docs/`（贡献者文档）· `.github/`（模板 + 工作流 + 依赖更新）。

**完整目录树、每个文件的职责、「新内容该放哪一层」的决策树**：
[docs/skill-anatomy.md](./docs/skill-anatomy.md)

## 自检与测试

```bash
python tools/validate_skill.py .              # 结构规范自检（14 项）
python -m unittest discover -s tests -v       # 120 个单元测试
```

任一条不过即以退出码 1 结束，可直接当 CI 用；完整检查清单见
[docs/skill-anatomy.md](./docs/skill-anatomy.md#校验)。测试只跑离线用例（网络层用桩替换），
**不会因为平台风控而随机变红**。

**CI 的依赖也要定期核对**：工作流里的 `actions/*` 已钉到**完整 SHA**，并由
`.github/dependabot.yml` 每周提更新 —— 这两件事**必须成对存在**：只钉 SHA 而没有升级机器人，
等于把「懒得更新」升级成「永远不更新」。判断现状看**最新一次运行的注解**，不是历史运行。

## 版本历史

工作版本 **5.9**；历史用 **git tag** 表达，不是并列的文件夹 —— 这样 `git log` / `git diff`
才能看出每一步改了什么。

| tag | 主题 |
|---|---|
| `5.9` | **当前版本**：对外文档与门面修正 |
| `5.8` | MediaCrawler 集成加固 |
| `5.7` | CI 依赖跟到 Node 24 + 三处表述修正 |

> 其余 13 个 tag（`1.0` … `5.6`）与每一次的完整理由见 [CHANGELOG.md](./CHANGELOG.md)。
> 每个 tag 都有对应的 **[Release](https://github.com/ChaLunRon/smart-buy-research/releases)**，
> 附一个由该 tag **现算**的「解压即可用」zip。**安装请用它**，不要用 GitHub 为 tag 自动生成的
> "Source code" 归档（顶层目录是 `smart-buy-research-5.9`，**点号**，与 `name` 的连字符写法不一致）。

## 发布到 GitHub

**仓库根 = 含 `SKILL.md` 的那一层**，不要把多个版本文件夹并排推上去。先自检，再
`git push -u origin main`，最后**逐个推精确 tag**（`git push origin 5.9`）——
⚠️ **不要用 `git push --tags`**：它会把本地**全部** tag 一并推上去（包括临时打的），
而本项目的纪律是**只推精确 ref**：多做的动作就多一分意外。

推 tag 后 Release 由 `.github/workflows/release.yml` 自动生成，zip 由该 tag 现算。
完整的发布流程、仓库设置建议（含 Discussions / Homepage / Dependabot）、常见错误，
以及 **Packages 为何保持为空**：[docs/publishing.md](./docs/publishing.md)

## 贡献与安全

- **[CONTRIBUTING.md](./CONTRIBUTING.md)** —— 四类常见贡献、PR 流程、版本命名规则、内容红线
- **[SECURITY.md](./SECURITY.md)** —— 脚本网络行为、平台账号风险、**提示注入缓解措施**、**撤回门槛**、私密报告渠道
- **[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)** · **[AGENTS.md](./AGENTS.md)**（给 AI 编码代理）·
  **[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)**（本项目**无第三方代码依赖**）

开 Issue 请用模板（[Bug](.github/ISSUE_TEMPLATE/bug_report.md) /
[内容纠错](.github/ISSUE_TEMPLATE/content_correction.md) /
[平台可读性](.github/ISSUE_TEMPLATE/platform_readability.md) /
[功能建议](.github/ISSUE_TEMPLATE/feature_request.md)）。**安全问题请勿开公开 Issue。**

---

## 致谢

本项目的设计参考了以下开源项目的公开做法：**[anthropics/skills](https://github.com/anthropics/skills)**
（Agent Skills 规范与三层披露结构）、**[obra/superpowers](https://github.com/obra/superpowers)**
（技能即方法论、跨 Agent 兼容）、**[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)**
（仓库级治理文件的完整度）。**本仓库不包含上述项目的任何代码。**

## 引用

若在论文或项目中引用本 Skill，见 [CITATION.cff](./CITATION.cff)。

## License

[MIT](./LICENSE) © ChaLunRon and Smart Buy Research Contributors
