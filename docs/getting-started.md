# 安装与使用

本文件覆盖各运行时的安装路径与排错。

## 通用前提

技能目录名**必须与 `SKILL.md` 里的 `name` 字段完全一致**（`smart-buy-research-5-5`）。
这是 Agent Skills 规范的硬要求，改错会导致校验不通过或加载失败。

注意 `name` 里**不能出现点号**，所以版本 `5.5` 写作 `5-5`。

## 按运行时安装

### WorkBuddy / 兼容 Agent Skills 的运行时

**用户级**（对所有项目生效）：

```bash
# macOS / Linux
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.workbuddy/skills/smart-buy-research-5-5
```

```powershell
# Windows
git clone https://github.com/ChaLunRon/smart-buy-research.git `
  "$env:USERPROFILE\.workbuddy\skills\smart-buy-research-5-5"
```

**项目级**（只对当前项目生效）：把仓库克隆到 `<项目>/.workbuddy/skills/smart-buy-research-5-5`。

### Claude Code

**路径 A（推荐）：作为插件安装。** 本仓库随附 `.claude-plugin/marketplace.json`
与 `.claude-plugin/plugin.json`，因此可以用 Claude Code 的插件市场直接装：

```bash
/plugin marketplace add ChaLunRon/smart-buy-research
/plugin install smart-buy-research-5-5@smart-buy-research
```

**路径 B：克隆到技能目录。** 不想要插件机制的话，直接克隆即可
（个人级一般是 `~/.claude/skills/`），`SKILL.md` 会被按 Agent Skills 规范自动发现：

```bash
git clone https://github.com/ChaLunRon/smart-buy-research.git \
  ~/.claude/skills/smart-buy-research-5-5
```

> 仓库根同时是插件根：根目录直接放着 `SKILL.md`、没有 `skills/` 子目录，
> 按 Claude Code 的规则会**作为单个技能加载**。

### 其他 Agent（Cursor / Windsurf / Codex / Copilot 等）

技能是**纯 Markdown + Python 标准库**，任何接受系统提示或指令文件的 Agent 都能用：

- 把 `SKILL.md` 正文并入你的指令文件，或
- 把整个技能目录放到该 Agent 的技能搜索路径下，或
- 直接告诉 Agent「读 `<路径>/SKILL.md` 并照它执行」

## 依赖

| 依赖 | 必需性 | 说明 |
|---|---|---|
| 能读网页的 Agent 运行时 | **必需** | 否则技能无法执行检索 |
| Python 3.8+ | 用脚本时必需 | 三个脚本**纯标准库**，无需 `pip install` |
| 无头浏览器 | **强烈建议** | 不装的话 **NGA 完全读不到，B站搜索页也读不到** |

无头浏览器：

```bash
npm i agent-browser
npx agent-browser install        # 首次需下载 Chrome for Testing（约 196 MB）
```

## 触发方式

用自然语言直接说就行，不需要特殊命令：

```
预算 6000，大一计算机专业，买笔记本，值不值？
XX 和 YY 哪个好？
这牌子的保健品靠谱吗？（危重型 → 会强制走资质核验）
这个测评是不是恰饭的？
我已经买了 XX，帮我看看有没有踩坑
想买 XX 但总觉得不太需要（必要性拷问）
```

**不会触发**：纯知识问答（"什么是 OLED"）、纯参数查询、金融产品研究。

## 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| Agent 从不自动加载本技能 | `name` 与目录名不一致，或 frontmatter 语法错 | 两边改成完全一致；用校验器检查 |
| `python scripts/*.py` 报 `SyntaxError` | Python < 3.8 | 升级 Python |
| 脚本报"找不到文件" | 参数路径写错，或未在仓库根目录运行 | 用绝对路径，或先 `cd` 到仓库根 |
| NGA / B站搜索页读不到 | 未装无头浏览器 | 见上文；或走降级方案（标注"仅摘要"） |
| 小红书始终读不到 | IP 级风控，**浏览器也读不到** | 换网络环境，或请用户自行提供内容 |
| 微信公众号抓取触发验证码 | 请求过快，违反其 `robots.txt` | **必须低频**，仅限本人单篇读取 |

## 降级顺序

读不到内容时按这个顺序退，**不要一上来就爬**：

```
换源 → 换检索形态 → 无头浏览器 → 爬虫 → 用户协作
```

爬取受限平台前**必须取得用户明确同意并说明账号风险**，
且本技能**不帮助规避平台规则**。
