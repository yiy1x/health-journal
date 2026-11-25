# 原开发目录与 GitHub 历史统一记录

日期：2026-11-25。用户明确指定目标仓库：[yiy1x/health-journal](https://github.com/yiy1x/health-journal)。仅处理源码、测试、文档与 Git 历史；不读取或迁移私人档案，不开放服务，不创建部署或 Release。

## 统一前状态

- 原开发目录已存在，分支名为 `main`，但没有任何本地提交，也没有 Git remote。
- GitHub 已有 **13 个提交**，基于早期 1.3.1 源码。读取时最新 `main` 为 [`d7a16a719707892c03d32ea547aacde0e891ed14`](https://github.com/yiy1x/health-journal/commit/d7a16a719707892c03d32ea547aacde0e891ed14)。
- 本地在原基础上有 1.4 Apple 健康导入与本轮 1.5 独立日常手记；不是应该被远端旧版本替换的副本。
- 远端最新两项修正：
  - [`72620f09c93fe1710c864493a206521ce802ade2`](https://github.com/yiy1x/health-journal/commit/72620f09c93fe1710c864493a206521ce802ade2)：手机异步测试等待真实完成状态，而非固定等待两个事件循环。
  - [`d7a16a719707892c03d32ea547aacde0e891ed14`](https://github.com/yiy1x/health-journal/commit/d7a16a719707892c03d32ea547aacde0e891ed14)：Python 3.9 使用 Ubuntu 22.04 运行器。

## 先备份，再比较

在读取和接入远端之前，按明确允许列表备份本地代码、测试、文档、静态资源和 CI。**没有扫描或打包任何 `.local-*`、`.health-import-*`、认证目录、数据库、病历、备份或下载文件。**

本地源码备份（位于已忽略的 `dist/`，不提交 GitHub）：

```text
source-before-reconcile-2026-11-25.zip
SHA-256: 7f66960dce4586b5364bc3688f7cb837aa1945df649e013d6288b883e839724a
source-before-reconcile-2026-11-25.manifest.json
```

远端先克隆到独立临时目录做只读差异比较，并保存包含完整历史的 Git bundle：

```text
remote-history-before-reconcile-2026-11-25.bundle
SHA-256: 62c7bbdda7fd4858f517970ddefb1e0b1875130e0d3792a4406626ef9a723324
```

该 bundle 已通过 `git bundle verify`；它保存 GitHub 源码历史，不包含本地私人资料。备份用于回溯，不将备份包当作提交源码或强行恢复覆盖当前目录。

比较时远端 80 个跟踪文件：58 个字节一致，22 个不同，0 个仅远端存在；另有本地新增模块、测试、研究和截图。后续本轮文档/测试继续增加，所以这些数字表示**初始比较快照**，不是最终变更行数。

## 合并取舍

| 范围 | 处理 |
| --- | --- |
| 本地 Apple 导入/样本/备份功能 | 保留并继续回归 |
| 本地独立饮食日记/统一页面/照片关联 | 保留，新增 schema v4 和备份 v4 |
| `.github/workflows/test.yml` | 保留远端 Ubuntu 22.04，叠加本地 `wearables.js` 语法检查 |
| `tests/web-phone-state.test.cjs` | 接纳远端异步修正，合并后与远端文件逐字节一致 |
| 其余相同文件 | 不做无意义格式重写 |
| 文档 | 更新当前版本与行为；历史验收保留，不把过去“无远端”当作当前状态 |
| 私人档案、凭证、数据库 | 不读取、不迁移、不暂存、不提交 |

另在合并审查中修正 Apple 预览 SQLite 连接显式关闭，避免 Windows 清理临时目录时仍持有句柄；新增回归断言解析和确认阶段的连接均关闭。这不是删除资料或跳过失败用例。

## Git 历史怎样接上

原目录没有本地历史，无须制造一条不相关的初始历史再强行合并。实际采用：

1. 在原目录配置 `origin=https://github.com/yiy1x/health-journal.git`。
2. `git fetch origin main`，仅获取对象和远端引用。
3. 将索引读入远端 main，并将尚不存在的本地 main 指向已核对的 `d7a16a7`；**没有使用工作区更新选项，没有 checkout/reset --hard，没有清空目录**。
4. 原有工作区原样保留，成为相对于该远端基线的修改和新增文件。
5. 明确暂存允许的源码文件并审查后，创建远端历史上的正常后继提交。
6. 推送使用普通 fast-forward；若远端变动导致拒绝，先获取并重新比较，不强推。

不使用 `--force`、`--force-with-lease`、`--allow-unrelated-histories`，也不替换整个 `.git` 或工作区。用户明确要求的既有 GitHub 提交继续是新提交的祖先。

## 维护约定

原开发目录就是后续由本聊天维护的唯一工作源码仓库，`main` 跟踪 `origin/main`。临时远端克隆只是比较材料，不另行开发/部署；后续不能继续往另一个 ZIP 副本改代码再声称已同步。

每次接续工作先检查：

```bash
git status --short --branch
git remote -v
git fetch origin
git log --oneline --decorate -8
```

工作区不干净或远端有新提交时先比较；不要自动覆盖、不把私人目录加入 Git。只在用户授权时提交/推送，按实际结果报告 SHA、远端分支和 CI 状态。当前文档与本轮真实验证见 [1.5 验收](ACCEPTANCE-v1.5.0.md)。

本轮没有改用户全局 Git 配置，也不读取系统凭证内容。若原目录未配置作者，新增自动化提交使用明确的 `Codex` 作者身份，不伪造用户个人邮箱；推送认证使用系统既有 Git 凭据机制或由用户完成授权。

## 如何验证已同步

最终应满足以下可复查条件，不能仅凭本文判断推送成功：

- `git merge-base --is-ancestor d7a16a719707892c03d32ea547aacde0e891ed14 HEAD` 返回成功。
- `git status --short --branch` 没有未提交源码差异。
- 再次 fetch 后，本地 HEAD、`origin/main`、`git ls-remote origin refs/heads/main` 是同一个提交。
- GitHub 页面能打开对应提交；Actions 状态单独报告，不能把本机测试通过等同于远端 CI 通过。

实际提交链接由本轮完成回复给出，不在提交本身里预填一个尚不存在的自引用 SHA。
