# Skill 结构与规范

本文件说明本仓库的技能如何组织，以及为什么这样组织。
改内容之前读一遍，能省掉一轮返工。

## 目录

- [三层披露（progressive disclosure）](#三层披露progressive-disclosure)
- [目录职责](#目录职责)
- [仓库目录树](#仓库目录树)
- [`references/` 的硬规矩](#references-的硬规矩)
- [frontmatter 字段](#frontmatter-字段)
- [加新内容的决策树](#加新内容的决策树)
- [校验](#校验)

## 三层披露（progressive disclosure）

Agent Skills 的核心设计是**分层加载**：不会一次性把所有内容塞进上下文。

| 层 | 内容 | 何时加载 | 体量约束 |
|---|---|---|---|
| L1 | `SKILL.md` 的 frontmatter（`name` + `description`） | **每次会话**都会预加载 | `description` ≤ 1024 字符 |
| L2 | `SKILL.md` 正文 | 技能被激活时 | **< 500 行** |
| L3 | `references/`、`scripts/`、`examples/` | 按需读取 | 无硬上限 |

**这个分层决定了改动放哪里**：

- 每次都用得到的判断纪律 → L2
- 只有特定品类/场景才需要的细节 → L3
- 需要执行的确定性计算 → `scripts/`

## 目录职责

| 目录 / 文件 | 放什么 | 不放什么 |
|---|---|---|
| `SKILL.md` | 工作流主干、不可协商原则、能力边界、资源索引 | 长篇方法论、品类细节、代码 |
| `references/` | 按需查阅的方法论与清单 | 主流程（主流程在 L2） |
| `scripts/` | 确定性计算与网络抓取 | 需要模型判断的逻辑 |
| `examples/` | 输入 → 输出的完整示例 | 规范说明 |
| `docs/` | 面向**贡献者**的说明 | 面向 Agent 的指令 |

## 仓库目录树

```
smart-buy-research-5-9/
├── .claude-plugin/                 # Claude Code 插件清单
│   ├── marketplace.json            # 市场清单（name / owner / plugins）
│   └── plugin.json                 # 插件清单（只需 name）
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
├── tests/                          # 单元测试（纯标准库 unittest，不发真实请求）
│   ├── test_price_tracker.py       # 国补封顶 / 渠道类型 / CLI 契约
│   ├── test_fetch_bilibili.py      # WBI 签名 / 混淆表 / 参数校验
│   ├── test_fetch_wechat_article.py# 正文提取 / 拦截图误判 / 实体反转义
│   └── test_validate_skill.py      # 校验器自身：目录同步 / 自指链接 / 锚点算法
├── tools/
│   └── validate_skill.py           # 结构规范自检 + 发布前占位值清点（CI 也用它）
├── examples/
│   └── usage.md                    # 5 个场景示例（含「过程中发生了什么」）
├── docs/
│   ├── getting-started.md          # 各运行时安装与排错
│   ├── skill-anatomy.md            # 本文件：技能结构与规范（改内容前必读）
│   └── publishing.md               # 发布指南（仓库根怎么选、tag 怎么打）
├── .github/
│   ├── workflows/validate.yml      # CI：规范自检 + 单元测试（py3.8 / 3.9 / 3.12）
│   ├── workflows/release.yml       # 打 tag 自动建 Release，附「解压即可用」的 zip
│   ├── dependabot.yml              # 每周提 actions 更新（与「钉 SHA」成对存在）
│   ├── ISSUE_TEMPLATE/             # Bug / 内容纠错 / 平台可读性 / 功能建议 四类模板
│   └── PULL_REQUEST_TEMPLATE.md
├── README.md                       # 门面：使用者向在前，维护者向在后
├── CONTRIBUTING.md                 # 贡献指南（含版本命名规则）
├── SECURITY.md                     # 安全政策（含提示注入风险、撤回门槛）
├── CODE_OF_CONDUCT.md              # 贡献者公约（含本项目特有红线）
├── AGENTS.md                       # 给 AI 编码代理的仓库说明
├── CHANGELOG.md                    # v1 → 5.9 版本演进
├── CITATION.cff                    # 引用元数据
├── THIRD_PARTY_NOTICES.md          # 第三方声明（本项目无第三方代码依赖）
├── LICENSE                         # MIT
├── .editorconfig                   # 统一行尾 LF / UTF-8
├── .gitattributes                  # 行尾规范化 + 二进制标记
└── .gitignore
```

> 这是**维护者视图**。使用者真正需要的只有 `SKILL.md` + `references/` + `scripts/` 三样，
> 其余是仓库治理与开发用的 —— README 因此只保留一层摘要表，细节放在这里。

## `references/` 的硬规矩

这是最容易踩坑的一层：

1. **只能一层深。** `references/a.md` **不得**再写"详见 `references/b.md`"要求 Agent 跳转。
   需要交叉说明时，把必要内容直接写进本文件，或用一节文字讲清楚。
2. **>100 行必须有 `## 目录`。** 否则 Agent 无法快速定位。
3. **文件名用连字符，不用空格。**
4. 文件内路径一律**正斜杠**。

> 为什么这么严：Agent 在 L3 不会自动遍历目录。一份"嵌套引用"链条会让它
> 要么漏读内容，要么多读好几轮，两种情况都是成本。

## frontmatter 字段

必需：

```yaml
---
name: smart-buy-research-5-9
description: ...
---
```

本仓库还使用以下可选字段：

| 字段 | 用途 |
|---|---|
| `license` | `MIT` |
| `compatibility` | 运行时要求（Python 版本、无头浏览器依赖等） |
| `metadata` | `author` / `version` / `homepage` |

**约束**：`name` 只允许小写字母、数字、连字符，**点号非法**，
且**必须与目录名完全一致**。所以版本 `5.9` 写作 `5-9`。

## 加新内容的决策树

```
这条内容每次调用都用得到吗？
├─ 是 → SKILL.md 正文（注意 < 500 行；超了先压缩别处）
└─ 否 → 它是确定性计算/网络请求吗？
        ├─ 是 → scripts/（纯标准库、中文报错、rc=2）
        └─ 否 → 它是特定品类/场景的细节吗？
                ├─ 是 → 找到对应的 references/ 文件追加
                └─ 否 → 它是给贡献者看的吗？
                        ├─ 是 → docs/
                        └─ 否 → 重新想想要不要加
```

## 校验

**本仓库自带校验器，提交前必跑**（它同时也是 CI 的第一步）：

```bash
python tools/validate_skill.py .              # 全部 14 项
python tools/validate_skill.py . --quiet      # 只看问题与警告
```

14 项检查里，**机器能判定的都判定了**：`name` 字符集/长度/保留字/与目录名一致、
`description` 长度与口吻、`SKILL.md` 正文 < 500 行、`references/` 超长文件必须带目录、
引用不得嵌套、相对链接与锚点可达、`## 目录` 与二级标题**同集同序**、行尾 LF、
路径用正斜杠、脚本可编译、版本号前后一致、发布前占位值清点、
自指链接不得指向未开启的仓库功能。

> 第 13 项（目录同集同序）与第 14 项（自指链接）是 **5.9 补上的**，
> 起因是 5.8 发布后审计发现两个盲区：原检查只验证「目录里的锚点能否解析」，
> 于是**漏收录**与**顺序错乱**都报不出来（README 漏了「引用」、CONTRIBUTING 漏了「License」，
> 两个门面文档带着错发布）；而**外部链接一个都不查**，于是 Issue 模板里指向
> 未开启的 Discussions 的死链也没被拦下。第 14 项**刻意不做网络探测**——
> 校验器要保持纯离线、结果稳定，把可达性断言打在外网上会带来随机变红。

**官方校验器**（若本地有 `skill-creator` 技能）可再跑一遍，两边不冲突：

```bash
python <path-to>/quick_validate.py .
# 期望输出：Skill is valid!
```
