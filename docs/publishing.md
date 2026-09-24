# 发布指南（Publishing）

本文件说明如何把这个技能发布到 GitHub。**核心只有一句话：一个仓库 = 一个版本历史，不要把每个版本都当成独立仓库推上去。**

## 目录

- [一、正确的心智模型](#一正确的心智模型)
- [二、发布前必做](#二发布前必做)
- [三、首次发布](#三首次发布)
- [四、仓库设置建议](#四仓库设置建议)
- [五、历史版本怎么放](#五历史版本怎么放)
- [六、常见错误](#六常见错误)

---

## 一、正确的心智模型

**要发布的仓库根 = 本目录的内容。**

也就是「`SKILL.md` 所在的那一层」——不是它的上一级。判断方法很简单：

```bash
ls SKILL.md       # 必须存在
```

如果根目录下能看到 `smart-buy-research-5-1/`、`smart-buy-research-5-2/` 这种**并列的版本文件夹**，
说明你把归档层当成了仓库根。这样推上去，GitHub 上会出现多份高度重复的副本，
既看不出演进脉络，也会让 `SKILL.md` 不在仓库根而无法被技能发现。

```
❌ 归档层的结构（用于本地留存）        ✅ 仓库根应有的结构
   archive-note/                         .
   ├── 5.1/                              ├── SKILL.md
   ├── 5.2/                              ├── references/
   └── 5.0/                              ├── scripts/
                                         └── ...
```

**版本历史用 git tag 表达，不用并列文件夹表达**（见第五节）。

本仓库已按此约定准备：随附的 git 仓库里，`main` 指向 5.2，
历史版本各自打了 tag，`git log --oneline` 就能看到完整演进。

## 二、发布前必做

本仓库的署名与所有者**已定稿**（署名 = `ChaLunRon`、邮箱 = `201579029+ChaLunRon@users.noreply.github.com`），
直接发布即可。若你要 fork 到自己账号下，请把下面三样一起改（别漏）：

```bash
# 1. 换成你自己的身份（括号内为当前值）
#    · 正文署名 + metadata.author + CITATION.cff + LICENSE （现为 ChaLunRon）
#    · 所有 github.com/<owner>/ 里的 owner                  （现为 ChaLunRon，必须 ASCII）
#    · 邮箱 + git config user.email                         （现为 201579029+ChaLunRon@users.noreply.github.com）

# 2. 自检：结构规范 + 链接 + 行尾 + 脚本可编译 + 版本一致性 + 剩余占位值
python tools/validate_skill.py .

# 3. 单元测试
python -m unittest discover -s tests -v
```

三步都通过再提交。CI 会在 push 后自动再跑一遍（见 `.github/workflows/validate.yml`）。

## 三、首次发布

```bash
cd <仓库根，即含 SKILL.md 的那一层>

git init -b main
git add .
git commit -m "Initial public release: 5.2"
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
| **Topics** | `agent-skills` `claude` `shopping` `reviews` `china` | 让技能可被发现 |
| **Description** | 「全网口碑调研与购买决策 · Agent Skill」 | 一句话讲清楚 |
| **Branch protection**（main） | 要求 CI 通过 | 本仓库的 CI 是纯离线检查，稳定可依赖 |
| **Releases** | 每个版本一个 release，附 zip | 见下一节 |

## 五、历史版本怎么放

两种做法，按需要选：

**做法 A（推荐）：用 tag，不放 zip**

```bash
git tag -a 5.2 -m "5.2：恢复 frontmatter、补 CI 与测试"
git push origin 5.2
```

读者用 `git checkout 5.2` 就能拿到完整快照，仓库体积也不膨胀。

**做法 B：Release 附件**

在 GitHub 上为每个版本建一个 Release，把该版本的 zip 作为附件上传。
适合给「不想 clone 的人」提供一键下载。

**不要**在同一分支里并排放多个版本文件夹 —— 那是归档层做的事，不是仓库该做的事。

## 六、常见错误

| 错误做法 | 后果 |
|---|---|
| 把归档层（含多个版本文件夹）整个推上去 | GitHub 出现多份重复副本；`SKILL.md` 不在仓库根，技能无法被加载 |
| 改了 `SKILL.md` 的 `name` 却没改目录名 | 规范校验不通过；安装后无法被识别 |
| clone 到与 `name` 不同的目录（如默认的 `smart-buy-research`） | 本地目录名对不上 `name`，校验不通过。**必须显式指定目标目录**：`git clone <url> ~/.workbuddy/skills/smart-buy-research-5-2` |
| `name` 里写点号（`5.2`） | 规范只允许小写字母/数字/连字符，必须写 `5-2` |
| 把中文署名直接当 GitHub 登录名用 | GitHub 登录名只允许 ASCII，`https://github.com/<中文名>/...` **打不开**、徽章裂图。正文署名可以留中文，但**凡是填进 URL 的 owner 必须是 ASCII**；`validate_skill.py` 第 12 项会清点残留的模板占位符 |
| 每个版本建一个新仓库 | 版本历史断成互不相干的仓库，无法 diff、无法追溯 |
| 忘了推 tag | 本地有历史，GitHub 上只有最新一版 |

## 七、版本命名规则速查

| 场合 | 写法 | 说明 |
|---|---|---|
| 文档正文 / `metadata.version` | `5.2` | 标准两级写法 |
| `name` 字段 / 目录名 / zip 文件名 | `smart-buy-research-5-2` | 规范禁止点号，必须用连字符 |
| git tag | `5.2` 或 `v5.2` | 与 `metadata.version` 对齐最省事 |

**三条命名必须完全一致**（zip 名 / 目录名 / `name` 字段），否则同时安装多个版本会触发名冲突。
详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
