# 智能体说明（AGENTS.md）

本文件告诉 AI 编码代理在本仓库中工作时需要知道的事。
如果你是人类贡献者，请直接看 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 这是什么仓库

一个 **Agent Skill** 的源码仓库，不是普通软件库。产物是**给 AI 读的指令**，
所以一条含糊的规则会在成千上万次调用里持续产生误判 —— 改动的影响面远大于代码。

## 仓库结构

```
.
├── .claude-plugin/          # Claude Code 插件清单（市场 + 插件）
├── SKILL.md                 # 主入口；硬约束 < 500 行
├── references/              # 按需加载的方法论（不进默认上下文）
├── scripts/                 # 可执行脚本，纯标准库
├── examples/                # 使用示例
├── docs/                    # 面向贡献者的说明
├── .github/                 # Issue / PR 模板
└── README.md / CONTRIBUTING.md / SECURITY.md / CHANGELOG.md / LICENSE ...
```

## 改动前必须知道的硬约束

1. **`SKILL.md` 正文必须 < 500 行。** 超了就下沉到 `references/`。
2. **`name` 只能是小写字母、数字、连字符**，且**必须与目录名完全一致**。
   **点号非法**，所以版本 `5.5` 写作 `5-5`。
3. **`description` ≤ 1024 字符**，第三人称，不得含 XML 标签。
4. **`references/` 只能有一层深度** —— 参考文件**不得再引用其它参考文件**。
   需要交叉说明时，把内容直接写进去，或用一节文字说清。
5. **>100 行的 `references/` 文件需要有 `## 目录`。**
6. **路径一律用正斜杠**，不要用 Windows 反斜杠。
7. **行尾统一 LF**（见 `.editorconfig` / `.gitattributes`）。

## 脚本改动规范

三个脚本（`price_tracker.py`、`fetch_bilibili.py`、`fetch_wechat_article.py`）的共同要求：

- 参数错误 → **中文提示 + 退出码 `2`**，**绝不打印 traceback**
- 网络错误 → 明确说明失败原因与降级方向
- 只使用 **Python 标准库**，不新增第三方依赖
- 新增参数 → 同步更新模块 docstring 与 `README.md`

自测（三项都应 `rc=0` 且无 traceback）：

```bash
python scripts/price_tracker.py --help
python scripts/fetch_bilibili.py --help
python scripts/fetch_wechat_article.py --help
```

## 事实性内容规范

本项目最看重的不是「加了多少内容」，而是**可验证**：

- 政策、法规、时限 → 必须附**官方来源**（政府网站、发证机构数据库）
- 平台可读性结论 → 必须**实测**并注明测试日期与三条路径的结果
- 机构/站点名称 → 必须确认**仍可访问且名称准确**
- **二手转述（尤其内容农场）不能作为依据** —— 这正是本技能要对抗的东西

## 不要做的事

- 不要为了让校验通过而把内容塞进 `SKILL.md` 的 frontmatter
- 不要新增第三方依赖
- 不要提交编造的优惠信息或把商业数据商包装成官方核验
- 不要更新 `_*` 临时文件到仓库（`.gitignore` 已忽略，但别强行加）
