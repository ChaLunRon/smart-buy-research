# 发布指南（Publishing）

本文件说明如何把这个技能发布到 GitHub。**核心只有一句话：一个仓库 = 一个版本历史，不要把每个版本都当成独立仓库推上去。**

## 目录

- [一、正确的心智模型](#一正确的心智模型)
- [二、发布前必做](#二发布前必做)
- [三、首次发布](#三首次发布)
- [四、仓库设置建议](#四仓库设置建议)
- [五、历史版本怎么放](#五历史版本怎么放)
- [六、常见错误](#六常见错误)
- [七、版本命名规则速查](#七版本命名规则速查)

---

## 一、正确的心智模型

**要发布的仓库根 = 本目录的内容。**

也就是「`SKILL.md` 所在的那一层」——不是它的上一级。判断方法很简单：

```bash
ls SKILL.md       # 必须存在
```

如果根目录下能看到 `smart-buy-research-5-1/`、`smart-buy-research-5-4/` 这种**并列的版本文件夹**，
说明你把归档层当成了仓库根。这样推上去，GitHub 上会出现多份高度重复的副本，
既看不出演进脉络，也会让 `SKILL.md` 不在仓库根而无法被技能发现。

```
❌ 归档层的结构（用于本地留存）        ✅ 仓库根应有的结构
   archive-note/                         .
   ├── 5.1/                              ├── SKILL.md
   ├── 5.4/                              ├── references/
   └── 5.0/                              ├── scripts/
                                         └── ...
```

**版本历史用 git tag 表达，不用并列文件夹表达**（见第五节）。

> 另外，若要支持 Claude Code 的 `/plugin marketplace add`，仓库根需要有
> `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json`（本仓库已随附）。

本仓库已按此约定准备：随附的 git 仓库里，`main` 指向 5.6，
历史版本各自打了 tag，`git log --oneline` 就能看到完整演进。

## 二、发布前必做

本仓库的署名与所有者**已定稿**（署名 = `ChaLunRon`、邮箱 = `201579029+ChaLunRon@users.noreply.github.com`），
直接发布即可。若你要 fork 到自己账号下，请把下面三样一起改（别漏）：

```bash
# 1. 换成你自己的身份（括号内为当前值）
#    · 正文署名 + metadata.author + CITATION.cff + LICENSE （现为 ChaLunRon）
#    · 所有 github.com/<owner>/ 里的 owner                  （现为 ChaLunRon，必须 ASCII）
#    · 邮箱 + git config user.email                         （现为 GitHub noreply 地址）

# 2. 自检：结构规范 + 链接 + 行尾 + 脚本可编译 + 版本一致性 + 剩余占位值
python tools/validate_skill.py .

# 3. 单元测试
python -m unittest discover -s tests -v
```

三步都通过再提交。CI 会在 push 后自动再跑一遍（见 `.github/workflows/validate.yml`）；
推 tag 后由 `.github/workflows/release.yml` 自动建 Release。

## 三、首次发布

```bash
cd <仓库根，即含 SKILL.md 的那一层>

git init -b main
git add .
git commit -m "Initial public release: 5.6"
git remote add origin https://github.com/ChaLunRon/smart-buy-research.git
git push -u origin main
```

推 tag（把已归档的历史版本一起推上去）：

```bash
git push origin --tags
```

## 四、仓库设置建议

| 设置项 | 建议 | 原因 |
|---|---|---|
| **Private vulnerability reporting** | 开启 | `SECURITY.md` 与 Issue 模板都指向它 |
| **Topics** | 已设 8 个：`agent-skill` `agent-skills` `ai-agent` `claude-code` `claude-code-plugin` `product-research` `purchase-decision` `shopping-assistant` | 让技能可被发现 |
| **Description** | 「全网口碑调研与购买决策 · Agent Skill」 | 一句话讲清楚 |
| **Branch protection**（main） | 要求 CI 通过 | 本仓库的 CI 是纯离线检查，稳定可依赖 |
| **Releases** | 已启用**自动发布**：推 tag 即建 Release 并附 zip | 见下一节 |
| **Packages** | **保持为空**（有意为之） | 本项目无包管理器载体，理由见第五节 |

## 五、历史版本怎么放

**用 tag 表达历史，用 Release 提供下载。** 两者都做，各司其职：

```bash
git tag -a 5.6 -m "5.6：CI 覆盖 3.8 + Release 自动化"
git push origin 5.6
```

- **tag** —— 读者 `git checkout 5.6` 就能拿到完整快照，仓库体积不膨胀。
  这是**版本历史的权威表达**，也是 `git log` / `git diff` 能看出演进的前提。
- **Release** —— 给「不想 clone 的人」一键下载。**本仓库已自动化**，见下。

**不要**在同一分支里并排放多个版本文件夹 —— 那是归档层做的事，不是仓库该做的事。

### 自动发布（`.github/workflows/release.yml`）

推一个形如 `主.次` 的 tag，工作流会自动：

1. 从该 tag 的 `SKILL.md` 读出 `name`（如 `smart-buy-research-5-6`）；
2. 用 `git archive --prefix=<name>/ <tag>` **从 tag 现算** zip；
3. 自检这个 zip：顶层目录唯一且等于 `name`、含 `SKILL.md`、不含 `.git` 与缓存；
4. 建 Release、把 zip 作为附件上传，Release notes 取 `CHANGELOG.md` 的对应小节。

由此得到一条重要性质：**发布物可由 tag 重现** —— 任何人执行同一条 `git archive`
都能得到逐文件相同的包，不必相信某一次手工打包的结果。

**回填历史版本**：手动触发该工作流并填 `backfill=all`，它会为每个 tag 补建 Release
（已存在的自动跳过，可重复触发）。Release notes 一律从 `main` 的 CHANGELOG 取，
因为 `tag 1.0 ~ 4.1` 当时还没有 `CHANGELOG.md`，`5.3` / `5.4` 的副本又被截断过；
早期版本按下表映射到小节：

| tag | CHANGELOG 小节 |
|---|---|
| `1.0` / `2.0` / `3.0` | `## v1` / `## v2` / `## v3` |
| `4.0` / `4.1` / `4.2` | `## v4`（三者共用同一节） |
| `5.0` | `## v5`（`## 5.0` 这个标题在 5.2 之后已不再单列） |
| `5.1` 起 | 与 tag 同名的 `## 5.x` |

> ⚠️ **别拿 GitHub 为 tag 自动生成的 "Source code" 归档当安装包。**
> 它的顶层目录是 `{仓库名}-{tag}`，即 `smart-buy-research-5.6`（**点号**）；
> 而技能规范要求 `name` 与目录名一致、且**点号非法**，必须写成 `smart-buy-research-5-6`。
> 下载 Release 里那个 zip 才是开箱即用的。

### 为什么 Packages 是空的

**这是有意的，不是漏了。** GitHub Packages 支持 npm / PyPI / NuGet / Maven / RubyGems / 容器，
而本项目的分发形态是**一个目录** —— 把整个目录放进运行时的技能搜索路径即可。
它没有包管理器载体：

- 仓库内没有 `pyproject.toml` / `setup.py` / `package.json` / `Dockerfile` / `requirements.txt`；
- `scripts/` 下三个脚本**只用 Python 标准库**，用 `pip install` 分发对它们没有意义；
- 把技能塞进某个注册表，反而要引入一层与「**零依赖**」定位相冲突的依赖。

要让 Packages 非空，**唯一有真实价值的方向是容器镜像** —— 把无头浏览器与抓取工具链
预先装好，做成 `ghcr.io/…` 供「受限平台读取」使用。但那是一件**独立的交付物**：
它有自己的版本节奏与维护成本，还要背第三方的许可与合规责任。真要做，就该单独起号位、
单独发布，而不是挂在技能仓库下充数。

**判据**：一个空标签页只是不完整；一个没人会用的包是**误导**。后者更贵。

## 六、常见错误

| 错误做法 | 后果 |
|---|---|
| 把归档层（含多个版本文件夹）整个推上去 | GitHub 出现多份重复副本；`SKILL.md` 不在仓库根，技能无法被加载 |
| 改了 `SKILL.md` 的 `name` 却没改目录名 | 规范校验不通过；安装后无法被识别 |
| clone 到与 `name` 不同的目录（如默认的 `smart-buy-research`） | 本地目录名对不上 `name`，校验不通过。**必须显式指定目标目录**：`git clone <url> ~/.workbuddy/skills/smart-buy-research-5-6` |
| `name` 里写点号（`5.6`） | 规范只允许小写字母/数字/连字符，必须写 `5-6` |
| 拿 GitHub 自动生成的 "Source code" 归档当安装包 | 顶层目录名是 `smart-buy-research-5.6`（**点号**），与 `name` 不符 → 校验不通过。请用 Release 里的 zip |
| 把中文署名直接当 GitHub 登录名用 | GitHub 登录名只允许 ASCII，`https://github.com/<中文名>/...` **打不开**、徽章裂图。正文署名可以留中文，但**凡是填进 URL 的 owner 必须是 ASCII**；`validate_skill.py` 第 12 项会清点残留的模板占位符 |
| 每个版本建一个新仓库 | 版本历史断成互不相干的仓库，无法 diff、无法追溯 |
| 忘了推 tag | 本地有历史，GitHub 上只有最新一版 |

## 七、版本命名规则速查

| 场合 | 写法 | 说明 |
|---|---|---|
| 文档正文 / `metadata.version` | `5.6` | 标准两级写法 |
| `name` 字段 / 目录名 / zip 文件名 | `smart-buy-research-5-6` | 规范禁止点号，必须用连字符 |
| git tag | `5.6` 或 `v5.6` | 与 `metadata.version` 对齐最省事 |

**三条命名必须完全一致**（zip 名 / 目录名 / `name` 字段），否则同时安装多个版本会触发名冲突。
详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
