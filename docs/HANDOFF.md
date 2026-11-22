# 知己 · 健康手记：实现说明与 GitHub 发布交接

> 交接日期：2026-11-16（Asia/Shanghai）  
> 当前源码版本：**1.3.1**  
> 面向对象：接手代码审查、首次 GitHub 提交、README/项目摘要/Release Notes 撰写的开发者或大模型。  
> 本文件记录交接时的状态和已验证事实，不是执行 GitHub 发布、登录账号、上传个人资料或消费模型额度的额外授权。

## 1. 请接手者先读这里

这是一个已经可以在本地运行的、中文优先的个人健康档案项目，不是只有设计稿的概念项目。当前交付是**默认空白的个人初版**，不预置人物、病历、检验数值或餐单。可选 AI 通道已实现，但不能把程序功能与模型的医学可靠性混为一谈。

接手的主要任务是：

1. 复核当前代码、文档、许可、测试结果和敏感文件排除情况。
2. 向用户确认目标 GitHub 账号/组织、仓库名、可见性、远端地址、提交身份，以及是否创建 Release。
3. 只提交经过检查的源码、文档、测试、合成夹具和静态资源。
4. 撰写准确的仓库简介、中英文摘要和首次发布说明。
5. 在获准推送后核验远端提交与 CI，交付真实的仓库/提交链接，而不是只给命令示例。

**不要一上来重写项目、清空数据库、把手机改成直接访问电脑服务，或执行未经检查的 `git add .`。**

### 1.1 信息优先级

如发现资料冲突，按以下顺序核验：

1. 当前源码与实际运行结果。
2. [1.3.1 验收说明](ACCEPTANCE-v1.3.1.md)。
3. [README](../README.md)、[API 说明](API.md)、[Codex 说明](CODEX.md)、[手机说明](MOBILE.md)。
4. 历史验收和研究报告。

[IMPLEMENTATION.md](IMPLEMENTATION.md) 包含早期实现及阶段性增量，不是所有当前细节的最终规格。旧文档里的版本号或手机横向导航描述，不应覆盖当前源码。

### 1.2 本文中的路径

所有代码路径均相对仓库根目录；从收到本文件的 `docs/` 目录向上一级即为根目录。执行命令前先运行 `pwd` 和 `git rev-parse --show-toplevel` 确认位置。本文不写入原开发电脑的用户名、绝对私有路径、账号邮箱或令牌，以便可以随公共源码提交。

## 2. 用户想做什么，我们实际怎样落地

原需求是一个个人医疗助理：本地保留个人资料、像诊所一样分科整理、记录症状与检查、提供每日饮食灵感，支持拍照导入、手机本地保存、多端交换资料，以及可选大模型分析。后来增加了不填 API Key、通过 ChatGPT 账号使用 Codex 的要求。

落地时采用三个原则：

- **原件与事实优先**：先可靠保存，再摘录和核对；空白不等于正常、未填写不等于没有。
- **AI 是可核对的草稿**：识别、建议和待补充问题独立保存，不自动写成诊断、用药或已确认科室。
- **数据边界明确**：电脑本地数据库、手机浏览器加密库、第三方模型调用是三种不同的数据流。

“可能得什么病”没有实现成自动诊断或概率预测。当前提供健康问题状态、症状自述、原报告记载和就医问题整理；不确诊、开药、调整剂量或排除急症。

## 3. 当前成果总览

| 项目 | 当前实现 | 不应宣称 |
| --- | --- | --- |
| 个人档案 | SQLite 保存基本信息、就诊、指标、用药、症状、健康问题、随访 | 多用户医院 EMR、挂号收费系统 |
| 原件 | PDF/JPG/PNG/UTF-8 TXT 导入、内容哈希去重、下载校验 | 本地自动 OCR、病理或医学影像诊断 |
| 科室 | 7 组、55 个常见科室目录、多科关联、关键词建议与人工确认 | 全国统一完整科室全集、自动医学分诊 |
| 指标 | 保留单位、机构/方法、比较符、原报告参考范围和来源 | 自动单位换算、跨机构数值天然可比 |
| 饮食 | 12 个家常示例菜谱、规则限制、三餐安排、替换、实际饮食 | 临床营养处方、精准热量或治疗膳食 |
| 本地助理 | 检索和摘录已有记录；可选本机 Ollama 草稿 | 已完成向量检索/RAG 医学知识库 |
| API 模型 | OpenAI/百炼/硅基流动/自定义兼容接口；每次授权 | 所有服务商/模型均已真实验证 |
| ChatGPT/Codex | 独立官方 CLI 连接、管理登录、模型选择、图文草稿、取消 | 通用第三方 ChatGPT OAuth、订阅转 API、无限免费 |
| 手机资料版 | 拍照、相册、文件、文字、加密 IndexedDB、加密备份 | 手机已具有全部桌面功能或模型连接 |
| 多端 | 手动原件资料包交换与合并 | 自动同步、全病历同步、电脑远程访问 |
| 备份 | 桌面 ZIP、手机加密备份及独立原件互传格式 | 所有备份都加密、所有格式可以互相恢复 |
| 空白初版 | 新目录不填个人信息、不注入演示数据 | 每次启动清空已有内容 |

## 4. 开发过程与设计取舍

### 4.1 调研

历史研究在以下文件中：

- [个人健康助理现状调研](research/2026-11-13-personal-health-assistant-landscape.md)：个人健康档案、自托管 AI、医疗内容风险、营养及监管边界；记录了 GitHub 仓库/README/许可等核查方法。
- [多模态与交互升级调研](research/2026-11-13-multimodal-and-ux-upgrade.md)：图文任务、原件分科、视觉与交互借鉴。
- [Codex 说明](CODEX.md)：官方 App Server、认证、配置文档和本地 CLI 的实际兼容边界。

这些研究是对应日期的核查记录，不是本次交接时重新检索整个互联网的结果。**参考开源仓库不等于安装运行过它们、审计过它们或可以复制其全部代码/许可。** 如发布摘要要引用仓库星标、版本、价格、计划权限，请重新核验，不能沿用历史数字声称“最新”。

### 4.2 版本演进

| 阶段 | 主要完成内容 |
| --- | --- |
| 1.0 | 个人本地档案、来源、时间线、趋势、受限餐单、就医摘要、备份 |
| 1.1 | API 图文分析、三类结构化草稿、55 科目录与多科关联、schema v2 |
| 1.1.1 | 输入/导航/版本冲突、严格 HTTP/JSON、后台异步不覆盖表单等修订 |
| 1.2 / 1.2.1 | 独立手机资料版、加密库和互传、旧备份兼容、跨语言协议测试 |
| 1.3.0 | 独立 Codex/ChatGPT 登录连接、安全配置校验、取消和协议测试 |
| 1.3.1 | 默认空白个人档案、可空姓名、未填饮食偏好、去除首页开发演示说明 |

完整记录见 [CHANGELOG.md](../CHANGELOG.md)。**版本号是源码演进记录，不代表这些版本已经在 GitHub 发布。**

### 4.3 技术选择

- Python 标准库 + SQLite：核心运行时无第三方 Python 包，部署路径短，便于审查。
- 原生 HTML/CSS/JavaScript：无需 npm 构建，无外部字体/CDN/分析脚本。
- 单人回环 HTTP 服务：降低误部署造成的数据暴露风险，不伪装成具有多租户鉴权的平台。
- 原件内容寻址：一份文件可被多个科室/记录引用，而非复制多份互相失配的附件。
- 手机独立静态应用：手机本地存储不依赖电脑持续开机，但明确限制同步范围。
- AI 显式授权：连接模型不等于授权读取全库，上传本地文件不等于外发。

## 5. 架构与数据流

```text
桌面浏览器（原生 JS / Hash 路由）
    │ 回环 HTTP；Host / Origin / Fetch Metadata / 随机令牌
    ▼
server.py → validation.py → Store（SQLite + attachments/）
    ├─ assistant.py → 本地事实摘录 / 可选回环 Ollama
    ├─ nutrition.py → 约束检查 → 用户主动生成餐单
    ├─ cloud.py → 冻结授权 → 确认 → HTTPS API → 校验草稿
    └─ codex_ai.py → 冻结授权 → 确认 → codex_rpc.py
                                              │ stdio
                                              ▼
                                隔离的官方 Codex CLI → OpenAI

手机浏览器（可信 HTTPS 静态站点）
    ├─ phone.js：拍照/导入/文字/查看/锁定/备份界面
    ├─ core.js：格式、摘要、加密、合并
    ├─ db.js：IndexedDB 加密快照与并发版本检查
    └─ sw.js：只缓存允许的静态资源

手机 ↔ 手机：用户传递 .hjvault 加密备份并确认合并
手机 ↔ 电脑：用户传递 .hj-transfer.json 明文原件包
```

不存在中心患者数据库、自动中继、公开健康 API、后台诊断任务、账户同步服务器或服务端遥测平台。

## 6. 代码在哪里

### 6.1 Python 代码索引

| 路径 | 职责 | 推荐检索入口 |
| --- | --- | --- |
| [health_journal/__init__.py](../health_journal/__init__.py) | 当前源码版本 | `__version__` |
| [health_journal/__main__.py](../health_journal/__main__.py) | CLI、默认目录、启动和清理 | `main`、`default_directory`、`--data-dir`、`--codex-bin` |
| [health_journal/server.py](../health_journal/server.py) | HTTP 路由、安全头、会话保护、依赖组装 | `JournalServer`、`Handler.guard`、`create_server` |
| [health_journal/store.py](../health_journal/store.py) | SQLite、附件、事务、版本、ZIP | `Store`、`save_record`、`add_document`、`merge_documents`、`backup`、`restore` |
| [health_journal/validation.py](../health_journal/validation.py) | 字段/类型/日期/记录/基本档案校验 | `validate_record`、`validate_profile`、`unique_json_object` |
| [health_journal/vault_lock.py](../health_journal/vault_lock.py) | 单资料目录进程锁 | `vault_lock` |
| [health_journal/departments.py](../health_journal/departments.py) | 科室目录与归属建议 | `CATALOG`、`suggest_departments`、`validate_routing` |
| [health_journal/nutrition.py](../health_journal/nutrition.py) | 示例菜谱、适用限制、计划 | `RECIPES`、`restrictions`、`make_plan`、`validate_plan` |
| [health_journal/assistant.py](../health_journal/assistant.py) | 本地检索、来源摘录、本机模型 | `grounded_answer`、`model_answer`、`ollama_request` |
| [health_journal/cloud.py](../health_journal/cloud.py) | API 适配、授权、响应和草稿校验 | `CloudAI`、`prepare`、`run`、`request_completion`、`parse_result` |
| [health_journal/codex_ai.py](../health_journal/codex_ai.py) | Codex 账号与分析状态机 | `CodexAI`、`control`、`configure`、`prepare`、`run`、`cancel` |
| [health_journal/codex_rpc.py](../health_journal/codex_rpc.py) | 子进程、stdio 协议、安全配置 | `CodexRPC`、`SAFE_CONFIG`、`check_config`、`official_auth_url` |
| [health_journal/transfer.py](../health_journal/transfer.py) | 原件资料包跨端协议 | `read_transfer`、`export_transfer` |
| [health_journal/export_phone.py](../health_journal/export_phone.py) | 手机静态资源白名单导出 | `ASSETS`、`export_phone` |
| [health_journal/demo.py](../health_journal/demo.py) | 显式开发演示数据 | `seed_demo`；普通启动不调用 |

### 6.2 桌面前端索引

| 路径 | 职责 |
| --- | --- |
| [web/index.html](../health_journal/web/index.html) | 页面壳、会话令牌占位、对话框及文件输入 |
| [web/app.js](../health_journal/web/app.js) | 全部桌面页面、路由、表单、异步状态和模型交互 |
| [web/style.css](../health_journal/web/style.css) | 布局、组件、手机断点、打印样式 |
| [web/favicon.svg](../health_journal/web/favicon.svg) | 本地静态图标 |

`app.js` 是单文件原生前端，不要误当 React/Vue 项目。需要定位行为时优先搜索：

- 路由：`routeState`、`navigate`、`render`、`selectTask`。
- 表单防丢：`dirtyForms`、`confirmDiscard`、`canLeave`、`data-saving`。
- 异步顺序：`refreshSequence`、`refresh`，丢弃落后的状态响应。
- 导入：`importMenu`、`uploadFiles`、文字导入及 `change` 事件。
- 科室：`departmentCatalog`、`specialtyData`、`routeModal`。
- 模型：`previewCloud`、`runCloud`、`selectEngine`、`codexConnectionView`、`cancelCodex`。
- 输出：`escape` 对用户/模型文本转义；`analysisResult` 展示待核对草稿。

### 6.3 手机前端索引

| 路径（均在 `health_journal/web/phone/`） | 职责 |
| --- | --- |
| `index.html`、`phone.css` | 手机壳、三项主导航、大触控区、安全边距 |
| `phone.js` | 创建/解锁库、相机/相册/文件/文字、预览、导出与合并 |
| `core.js` | 文件名/类型/Base64/哈希/格式校验，Web Crypto 加解密与合并 |
| `db.js` | IndexedDB 单事务写入，按预期 revision 拒绝旧窗口覆盖 |
| `sw.js` | 静态缓存白名单及更新生命周期 |
| `manifest.webmanifest`、`icon.svg` | 安装到主屏幕所需元数据与图标 |
| `_headers` | 支持该文件的静态托管服务可使用的响应头配置 |
| `LICENSE.txt` | 手机静态分发的许可文本 |

`catalog.json` 由服务或导出器生成，不是需要手工维护的另一份私有数据库。手机静态版本当前仍为 **1.2.1**；1.3.x 改动主要在桌面，不能把手机缓存版本差异误判为漏升级。

### 6.4 项目与协作文档

- [pyproject.toml](../pyproject.toml)：包名 `health-journal-local`、Python `>=3.9`、无运行时依赖、setuptools 构建与资源打包。
- [.gitignore](../.gitignore)：排除本地档案、数据库、认证、密钥、备份、构建结果等。
- [README.md](../README.md)：用户入口，不应把完整交接文档原样塞进 README。
- [LICENSE](../LICENSE)：MIT 正文，当前版权行为 `Copyright (c) 2026 Health Journal contributors`。
- [DISCLAIMER.md](../DISCLAIMER.md)、[PRIVACY.md](../PRIVACY.md)、[SECURITY.md](../SECURITY.md)：医学边界、数据流、威胁模型与报告方式。
- [CONTRIBUTING.md](../CONTRIBUTING.md)：合成复现、贡献要求。
- [.github/workflows/test.yml](../.github/workflows/test.yml)：只读权限 CI，checkout 不保留凭据。
- [.github/ISSUE_TEMPLATE/bug_report.yml](../.github/ISSUE_TEMPLATE/bug_report.yml)、[PR 模板](../.github/pull_request_template.md)：防止用户在协作中上传医疗资料。

## 7. 本地数据库和持久化是怎样做的

### 7.1 桌面存储结构

```text
<用户选择的资料目录>/
├── journal.sqlite3
├── attachments/             # 以内容哈希命名的原件
├── .instance.lock           # 进程锁，不是密码/加密锁
└── .codex-connection/       # 仅主动连接 Codex 后才产生
    ├── auth/               # CLI 管理的持久凭证及可能的元数据
    └── session-.../         # 活跃连接的临时 HOME/工作目录
```

SQLite schema 为 v2，主要表：

| 表 | 内容 |
| --- | --- |
| `settings` | profile、本机模型及非密钥配置等键值设置 |
| `records` | 六类结构化健康记录、来源、核对状态和版本 |
| `documents` | 原件文件名、MIME、大小、SHA-256、时间 |
| `document_routes` | 原件多科关联、依据、待确认/确认状态及版本 |
| `meal_plans` | 指定日期的三餐计划、约束和实际用餐备注 |
| `analyses` | AI 草稿、模型来源、发送文本、原件关联和实际饮食确认 |
| `audit` | 操作时间/动作/实体/ID，不记录医疗正文或 Key |

采用参数化 SQL、外键、事务和版本冲突检查。下载原件会核对字节长度与哈希。正在使用的附件/记录关系不能任意破坏。SQLite 文件和桌面附件**没有应用层加密或密码锁**，应由用户启用磁盘加密和系统访问保护。

### 7.2 默认空白状态

`validate_profile({})` 的核心结果：

```json
{
  "name": "",
  "birth_date": "",
  "sex": "unspecified",
  "allergies": [],
  "diet": "unspecified",
  "clinical_diet": false,
  "diet_acknowledged": false,
  "diet_notes": "",
  "emergency_contact": "",
  "notes": ""
}
```

新目录中的记录、附件、餐单、草稿、操作历史均为空。55 科目录、过敏选项、菜谱规则和输入占位示例不是个人资料，不应为“清空信息”而删掉功能定义。

现有资料不自动清除、不自动用默认值覆盖。1.3.1 新备份可能包含空称呼或 `diet: unspecified`；旧版本校验器可能拒绝这些值，恢复须使用 1.3.1 或更新版本，不能仅因为 schema 仍为 v2 就承诺任意降级。

### 7.3 备份边界

- 桌面便携 ZIP：包含 profile、记录、原件、分科、餐单、草稿等，**未加密**；不含模型配置、密钥、Codex 认证目录和旧操作日志。
- 手工完整目录副本：会包含数据库设置/日志，以及可能存在的 Codex 凭证；应停服后复制并私密保存。
- 手机 `.hjvault`：加密快照；需要对应密码，不是桌面 ZIP。
- `.hj-transfer.json`：原件文件名、类型、哈希和 Base64 字节；**Base64 不是加密**，不是完整病历备份。

ZIP 恢复只允许合适的空档案，检查格式、允许路径、条目、总量和来源一致性，失败回滚本次写入。不要“修复导入失败”时放宽路径校验或直接覆盖旧库。

## 8. 核心用户流程

### 8.1 导入与分科

选择文件/拍照/粘贴文字 → 本机校验文件 → 按 SHA-256 去重保存 → 文件名/TXT 关键词给出科室建议 → 用户核对 → 确认多科关联。

图片/PDF 的本地分类只参考文件名，不假装读懂图片。可另行授权模型整理报告内容，但模型给出的数值、日期、科室仍需要核对原件。指标进入正式记录时使用原单位/比较符/报告参考范围，不自动把一次异常写成某疾病。

### 8.2 饮食

用户选择偏好、填写限制并确认适用范围 → 规则检查 → 主动生成计划 → 可换菜 → 用户记录实际吃了什么。

未选择偏好、未确认一般成人范围、记录了特殊饮食需求/医嘱、未成年、无法识别的过敏原或特定需个别评估的健康问题时，会暂停自动规划。关键词规则不是完整病种识别，例子菜谱没有经过临床营养验证。

### 8.3 三种 AI 草稿

| 任务 ID | 输出 | 人工确认边界 |
| --- | --- | --- |
| `breakfast` | 可能识别食物、份量不确定、建议、追问 | 用户自行填写实际饮食，不把识别当事实 |
| `document` | 摘录候选、原文位置、科室建议与依据 | 逐项核对原件，不自动创建确诊或指标 |
| `chat` | 基于授权资料的整理、建议、不确定点 | 不预测概率，不代替医生 |

所有草稿公共字段包含 `summary`、`uncertainties`、`questions`。完整格式见 [API.md](API.md)。模型自评置信度不是医学概率或校准误差。

## 9. API Key 通道

实现位于 `cloud.py`，使用兼容 Chat Completions 的单次非流式请求。

1. 页面保存 provider、Base URL、model、vision；API Key 只保留服务端内存，不写 SQLite 或便携备份。
2. `prepare` 生成冻结快照，默认不包含个人限制或病历摘录；用户选择后才加入最小上下文。
3. 页面展示文本、附件、接收方和提示词。授权 10 分钟有效、单次消费、每个连接最多 8 份待确认。
4. 用户确认才执行 `run`；配置变更/授权过期使旧预览失效。
5. 验证输出 JSON、字段类型、长度、条目数和科名，保存独立草稿，不执行模型输出。

API 适配器只允许公网 HTTPS/443，检查全部 DNS 地址并连接已校验 IP，TLS 仍校验原域名；不跟随重定向、不使用环境代理、不自动重试。上游错误不原样回显。

OpenAI API 请求使用 `store:false` **不等于零留存**；更不适用于其他服务商或 Codex 账号政策。附件不自动去除 EXIF、姓名、二维码等。已发送内容和费用无法由本应用撤回。

## 10. ChatGPT / Codex 通道

### 10.1 采用的官方方式

使用 `codex app-server --listen stdio://`，由本机官方 CLI 管理 ChatGPT 登录。连接没有把 ChatGPT 当成第三方网站的通用身份提供方，也不生成 API Key，不抓 Cookie，不复制用户原来的 `~/.codex/auth.json`。

主要协议流程：

```text
启动隔离进程
  → initialize / initialized
  → config/read（逐项确认安全配置）
  → account/read
用户点击登录
  → account/login/start(type=chatgpt)
  → 官方网页由用户登录
  → 刷新 account/read / model/list
选择模型并保存
  → prepare → 用户确认
  → thread/start(ephemeral)
  → turn/start(受限只读策略 + outputSchema)
  → item/completed / turn/completed
  → 本地 parse_result → 保存草稿 → thread/unsubscribe
```

### 10.2 隔离与恢复

- 独立 HOME/USERPROFILE/CODEX_HOME、临时空工作目录和环境白名单。
- 强制 ChatGPT 登录、内置 OpenAI provider、只读沙箱及禁止审批；禁用 shell、MCP、插件、钩子、技能、浏览器、电脑操作和多代理等。
- 校验实际生效配置，而不是只相信启动参数。不兼容就失败，不降低隔离要求。
- 登录链接必须是允许的官方 HTTPS 来源；不接受应用内手填 Token。
- 账号代次、模型 revision、一次性授权、控制锁与在途请求共同约束并发。
- 服务端主动工具请求或不允许的工具事件导致停止，不代替用户批准操作。
- 文本和 JPG/PNG 可用；是否支持图片来自账号返回的模型能力。**Codex 不直传 PDF**。
- 取消终止独立连接，不保存尚未提交的本次草稿；如保存先完成则取消返回冲突。此前草稿不被删除。
- 断开连接不等于退出账号，持久登录由 CLI 保留；账号退出是独立动作。

协议通常每次 RPC 等待 15 秒，分析事件截止时间 150 秒；清理、RPC、系统调度可能增加时间，不是严格端到端 SLA。应用不自动重试，不代表官方 CLI/上游内部绝对没有网络重试。

修复过一个实际兼容问题：用户消息事件可能回显整张 Base64 图片，不能套用普通模型输出的 2 MiB 限额。当前输入/用户回显最多 13 MiB，回显内容立即移除冗余；一般响应/事件最多 2 MiB，只对需要的生命周期事件排队，队列上限 32。

### 10.3 认证风险与真实验证程度

Codex 的文件型凭证位于资料目录 `.codex-connection/auth`，**可能包含明文访问/刷新令牌**。本应用不解析/返回它们，但完整目录复制会包含，不能宣称这类凭证与 API Key 一样只在 RAM 中。

本机实际验证官方 `codex-cli 0.167.0-alpha.3.2` 的匿名握手、配置和未登录账号状态，也验证过生产 HTTP 路由到 CLI 的连接。**没有替用户完成真实 OAuth，也没有调用真实模型分析健康内容或消费用户额度。** 图文成功/超时/取消/额度或协议失败流程由独立假 CLI 和合成数据覆盖。

CLI 属于受信任程序，不是恶意二进制隔离器。其他 CLI 版本、Windows/Linux 沙箱和账号权益需要重新验收。账号政策不能照搬 API `store:false`。详细依据见 [CODEX.md](CODEX.md)；该文档列出官方来源链接。

## 11. 手机、本地加密和互传

手机资料版不是桌面页面缩小。它有“记一笔/资料夹/备份互传”三项主功能，拍照入口突出，原件保存到当前设备当前来源的浏览器库。

加密采用浏览器 Web Crypto：

- PBKDF2-HMAC-SHA-256，600000 次迭代、16 字节随机盐。
- AES-256-GCM，每次随机 12 字节 IV、128 位认证标签、固定格式附加认证数据。
- 文件名和原件均在加密载荷中；IndexedDB 保存密文包与并发 revision。
- 密码/不可导出的 CryptoKey 在解锁页面内存中；5 分钟无操作锁定，后台恢复时检查。
- 忘记密码不能找回；清除站点数据可能删除唯一副本。加密不保护已被攻陷的页面或已解锁系统。

导入单文件最多 20 MiB，手机原件合计 40 MiB、500 份，普通批次最多 50 份；传输包最多 58 MiB，加密文件最多 80 MiB。HEIC 不支持，不静默转码。

合并以内容哈希去重，保留接收端已有名称/关联；同名不同内容都保留，不传播删除。整体资料包先校验后事务新增；普通多文件导入逐份保存，失败项单独重试。

手机需要可信 HTTPS 静态来源。**不要把电脑服务改为 `0.0.0.0`、开隧道、映射端口或发布整个源码目录来解决手机访问问题。** GitHub Pages 不会自动应用 `_headers` 文件，也不是具有健康资料鉴权的后端。

## 12. 页面与交互完整性

桌面有 11 个 Hash 路由：

| 路由 | 页面 |
| --- | --- |
| `#home` | 健康总览 |
| `#departments` | 全科室档案 |
| `#timeline` | 诊疗时间线 |
| `#documents` | 原始资料 |
| `#trends` | 指标趋势 |
| `#care` | 用药与症状 |
| `#meals` | 饮食计划 |
| `#assistant` | 档案助理 |
| `#summary` | 就医摘要 |
| `#models` | 模型连接 |
| `#settings` | 设置与备份 |

任务、草稿、科室详情和护理标签使用白名单子路由参数；未知/失效路由回退而不是渲染异常。表单绑定展示时的版本；保存中防重入；后台响应不能覆盖用户尚未保存的表单。离页确认使用应用内对话框，浏览器关闭仍只能尽力提示。

新版遵循现有墨蓝/松绿/浅色面板视觉体系，系统中文字体，无远端资源。手机宽度采用底部导航、更多菜单和至少 44px 的主要触控目标。采用文字/来源/状态提示，不用“健康分数”或装饰曲线填补空数据。

## 13. 测试在哪里、哪些结论可以引用

### 13.1 测试文件索引

| 文件 | 核心覆盖 |
| --- | --- |
| `tests/test_core.py` | 输入、Store、备份恢复、营养、默认空档案、历史数据保留 |
| `tests/test_http.py` | 会话/跨站/文件/API/Codex 路由与空白初始状态 |
| `tests/test_cloud.py` | API 配置、授权、最小上下文、响应校验、草稿/分科 |
| `tests/test_codex.py` | 实际 stdio 假进程、账号/模型/授权、超时/取消/安全配置 |
| `tests/fake_codex.py` | 离线协议替身和错误场景；不是生产模式 |
| `tests/test_transfer.py` | 原件资料包、去重、原子合并和非法输入 |
| `tests/web.test.cjs` | 渲染、转义、趋势、11 页空态 |
| `tests/web-state.test.cjs` | 事件、路由、脏表单、异步顺序、Codex 页面状态 |
| `tests/web-phone.test.cjs` | 加密/格式/兼容/合并与缓存约束 |
| `tests/web-phone-db.test.cjs` | IndexedDB 适配器、事务、并发 revision |
| `tests/web-phone-state.test.cjs` | 手机事件/锁定/导入/失败保护 |
| `tests/web-transfer-roundtrip.test.cjs` | JavaScript → Python → JavaScript 的真实跨运行时协议 |
| `tests/browser_fixture.py` | 独立临时合成库、离线 API/Codex 浏览器验收，端口 8767 |

### 13.2 最近完成的结果

源码 1.3.1 的上一轮完整执行记录：

- **259 个不同自动化测试通过：164 Python + 95 Node。**
- Python 3.9.6：164/164，32.180 秒。
- Python 3.12.14：164/164，30.223 秒；不把重复执行算作新增测试。
- Node 25.6.0：95/95，约 1.1 秒；5 个 JS 文件语法检查通过。
- 真实浏览器：11 页 × 320/390/1280 像素，标题正确、无页面级横向溢出、无演示残留；设置字段确认为空。
- 安装包在独立临时目标安装后，验证版本、静态资源和创建空白档案。
- 代码/文档打包使用白名单，未包含本地数据库、凭证或私有档案；本地 Markdown 文件链接检查通过。

本次撰写交接文档只核对当前代码/Git/文件，不把上述结果伪装成本轮重新运行的测试。接手者在修改代码或发布前必须重新执行并报告真实结果。测试“通过”不等于无 Bug、安全认证或医学验证；VM/协议替身测试也不等于真实浏览器/真实模型。

### 13.3 复现命令

在仓库根目录执行，HTTP 用例需要允许临时回环监听：

```bash
python3 -m unittest discover -s tests -v
node --check health_journal/web/app.js
node --check health_journal/web/phone/phone.js
node --check health_journal/web/phone/core.js
node --check health_journal/web/phone/db.js
node --check health_journal/web/phone/sw.js
node --test tests/web*.test.cjs
```

Windows 使用对应 `python`/`py -3`。Node 22+ 用于测试，不是应用运行依赖。可单独运行 `python3 -m unittest tests.test_codex -v` 定位 Codex 故障。需要浏览器假模型验收时使用 `python3 -m tests.browser_fixture`，不要当成正式启动命令。

### 13.4 CI 现状

GitHub Actions 配置 Ubuntu Python 3.9/3.11/3.12/3.13、Windows Python 3.13，以及 Node 22 + Python 3.12 前端/跨语言任务。权限 `contents: read`，checkout 不保留凭据，不需要真实模型密钥。

**目前尚无远端执行结果。** 不要在 README 添加虚假的绿色徽章。Action 当前按 `@v4` 标签引用，没有固定到 commit SHA；发布者可按组织安全策略评估固定版本，但应单独验证改动。

## 14. 已知风险、限制和不能擅自“修复”的事项

1. 电脑数据库/附件/ZIP 未做应用层加密，无多用户登录。回环限制不防同机恶意程序、扩展或管理员。
2. 手机支持本地加密，但需可信代码和 HTTPS 来源；浏览器清理/设备损坏仍可能丢数据。
3. API Key 只在内存；Codex 认证可能落地明文，两者不能混写成一个隐私承诺。
4. 真实 Codex OAuth/推理及 API 服务商未完成真实账号端到端测试；模型医学准确率未评测。
5. 物理 iOS/Android 相机/选择器、Windows/Linux 官方 CLI 沙箱未做全覆盖验收。
6. 不自动同步全病历，不支持手机模型调用、HEIC、本地 OCR、处方识别或治疗性餐单。
7. 没有外部安全审计、渗透认证、临床试验或医疗器械监管批准。
8. 任何模型建议都要核对；危险症状不能等待 AI 或记录软件判断。
9. 构建时 setuptools 对 `project.license` 表格形式给出弃用警告；当前构建成功。迁移到 SPDX 字符串/`license-files` 需同时评估构建后端版本和旧 Python 兼容性，不应未经验证只改一个字段。
10. 早期默认 profile、手机旧文件名兼容和旧备份有历史包袱；修改校验时必须保留回归，不静默清理用户旧资料。

## 15. 当前本地工作区与 Git 状态

以下是本次交接时实际核对的状态；接手时请再次检查：

| 项目 | 状态 |
| --- | --- |
| 分支名 | `main` |
| HEAD | 尚不存在，是未产生首次提交的仓库 |
| Git 远端 | `git remote -v` 无输出，尚未配置 |
| 代码状态 | 项目源码、文档、测试和 `.github/` 均未跟踪 |
| 已有提交/推送/PR | 本次工作未创建提交、推送或 PR |
| 当前个人页面 | `http://127.0.0.1:8769/#home`，交接时端口在监听；进程结束后需重启 |
| 当前个人目录 | `.local-personal-v1`，当前开发会话选择的新目录；禁止入 Git |
| 原演示目录 | `.local-codex-v1.3-demo` 保留；禁止入 Git，不迁移其凭证 |

`git diff` 在文件尚未跟踪时不会显示完整变更，空 diff **不等于没有代码或没有风险**。需要查看文件本身、未跟踪清单以及经过明确暂存后的差异。也不要运行 `git diff HEAD` 并把“没有 HEAD”的失败误认为仓库损坏。

普通用户默认目录在仓库外；当前 `.local-personal-v1` 是明确选择的本地开发目录例外。它当前为空不意味着以后也为空，绝不能上传。

## 16. 启动、安装和生成产物

### 16.1 普通空档案启动

```bash
python3 -m health_journal
```

默认端口 8765；macOS、Windows、Linux 的默认资料路径见 README。必须使用新目录验证首次空态，已有目录按设计保留内容。当前本机工作会话如需重启，可在确认 8769 无其他服务占用后使用：

```bash
python3 -m health_journal --data-dir .local-personal-v1 --port 8769
```

这条命令不清空已有个人数据；不要为了“恢复初始状态”覆盖该目录。Codex 不在 PATH 时由用户提供官方可执行文件的绝对路径，通过 `--codex-bin` 指定，不把原开发电脑的安装路径硬编码到公共代码。

### 16.2 从源码安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/health-journal
```

Windows 的虚拟环境入口在 `.venv\Scripts\`。这里安装的是用户已经审查的本地源码，不是在 PyPI 搜索并安装一个来源不明的同名包。

### 16.3 手机静态导出

```bash
python3 -m health_journal.export_phone --output dist/phone-release
```

输出目录必须不存在，避免覆盖。只部署这个输出目录到可信 HTTPS，不部署 SQLite、源码工作区或 `dist/` 中的所有历史文件。

### 16.4 现有交付文件

交接前已生成：

- `dist/health-journal-1.3.1-source.zip`
- `dist/health_journal_local-1.3.1-py3-none-any.whl`
- `dist/SHA256SUMS-v1.3.1`

**这些文件在本交接文档创建之前生成，不含本文件。** 它们仍可代表上一轮已测试源码，但如果作为最终 GitHub Release，建议从经审核的最终提交重新构建、安装验收并生成新校验和。不要照抄之前的哈希到新产物。

`pyproject.toml` 的文档资源模式包含 `docs/*.md`，后续新构建会包含本交接文档；因此本文保持可公开的相对路径和无凭证内容。`dist/` 已被忽略，不应强制加入源码历史；只按需把选定文件作为 Release 附件。

## 17. 接手后的 GitHub 发布执行顺序

### 阶段 A：只读核验

```bash
pwd
git rev-parse --show-toplevel
git status --short --untracked-files=all
git status --ignored --short
git branch --show-current
git remote -v
git ls-files
```

检查适用的 `AGENTS.md` 和当前环境权限。不要读取 `auth.json`、API Key 文件或个人病历正文来“验证是否敏感”；检查候选提交清单、文件类型和来源即可，确需内容审查时应先取得相应授权。

### 阶段 B：必须向用户确认的信息

- GitHub 账号或组织、仓库名称、真实远端 URL。
- 新建还是已有仓库；可见性 public/private，未明确时不擅自公开。
- Git 作者姓名/邮箱或用户选择的 GitHub noreply 身份，不猜测个人资料、不修改全局 Git 配置。
- 是否仅提交/推送，还是还要创建 tag、Release、PR 或手机静态部署。
- 版权署名和私有安全报告渠道；现有贡献者署名是否由用户接受。

若已有仓库包含 README/许可/提交，先读取远端状态并选择正常整合流程，**不能 force push、重写历史或用 unrelated histories 强行覆盖**。建议先私有检查，但这是建议，不是已获授权的可见性选择。

### 阶段 C：发布前审查清单

- [ ] 全量测试通过，失败没有被跳过/伪装。
- [ ] 新安装默认空白；已有个人记录不丢失。
- [ ] 医学/隐私/同步限制与代码一致，README 不夸大。
- [ ] 所有截图逐张确认：当前空白截图、历史合成截图；不含真实姓名、邮箱、病历或认证信息。
- [ ] MIT 许可及作者/贡献来源复核；Codex、Ollama、第三方模型的独立条款不被“项目 MIT”覆盖。
- [ ] 文档/Issue/PR 模板中没有真实 API Key、本地用户名、私有目录或用户病历。
- [ ] `.local-*`、`.codex-connection/`、`auth.json`、`.env*`、数据库、附件、备份/互传包、运行日志未入候选清单。
- [ ] 不仅看 `.gitignore`；它不保护已跟踪文件，也不能判断任意命名的 PDF/JPG/TXT 是否含医疗资料。
- [ ] 没有宣称已经上线托管、CI 全绿、真实模型已测或手机已自动同步。

### 阶段 D：明确暂存和首次提交

仅在阶段 B/C 完成、用户授权后执行。下面是允许目录的模板，不代表无须查看其中每个新增文件：

```bash
git add -- .gitignore pyproject.toml README.md LICENSE DISCLAIMER.md PRIVACY.md SECURITY.md CONTRIBUTING.md CHANGELOG.md
git add -- health_journal tests docs .github
git diff --cached --name-status
git diff --cached --stat
git diff --cached --check
git diff --cached
```

图片/二进制不能只靠文本 diff，需独立检查。若发现误暂存的私有文件，先仅取消它的暂存，保留工作区文件；不要直接删除用户数据。当前是首次提交前状态，不使用依赖有效 HEAD 的命令作为唯一恢复手段。

建议提交标题（可由接手者调整）：

```text
feat: introduce local-first health journal v1.3.1
```

建议提交正文：

```text
- Add an empty-by-default Chinese personal health journal with SQLite records and traceable originals.
- Add specialty folders, timelines, comparable trends, constrained meal planning and visit summaries.
- Add opt-in API and isolated Codex/ChatGPT analysis with per-request consent and validated drafts.
- Add a mobile encrypted document vault and manual original-file transfer.
- Include synthetic tests, CI configuration, MIT license and explicit medical/privacy limitations.
```

如用户没有要求新分支，不必为了首次发布新建分支；当前已有 `main` 名称但没有提交。实际 `git commit` 前确认本地身份正确，不能使用本文件里的示例作为作者身份。

### 阶段 E：远端、推送和 CI

确认 `origin` 不存在后才添加用户确认的地址：

```bash
git remote add origin <USER_CONFIRMED_REMOTE_URL>
git remote -v
git push -u origin main
```

占位符不能原样执行。若 `origin` 已存在或远端不为空，先核验，不覆盖。GitHub 登录由用户使用受支持工具完成，不读取本机私有凭证、不要把 PAT 粘贴进 README/命令日志。

推送后检查实际提交 SHA、仓库可见性和 Actions 运行状态。仅报告观察到的结果；CI 仍运行/失败时明确说明，不声称已通过。首次提交到空仓库通常不需要 PR；已有仓库要求 PR 时遵守其流程。

### 阶段 F：可选 Release

仅在用户明确要求 Release 时：

1. 从最终已审查提交的干净副本构建，不从含私人目录的工作区一把打包。
2. Wheel 检查版本、许可证、静态资源、当前文档；独立安装验证。
3. 源码包包含必要源文件、测试、文档与 CI，不含数据库、认证和历史构建缓存。
4. 重新计算 SHA-256；从附件本身验证，不使用旧哈希。
5. tag/release 名称建议 `v1.3.1`，确认是否预发布；不要覆盖用户已有 tag 或把尚未提交的改动称为该 tag 的内容。
6. 使用准确说明，附已知限制和升级/备份注意事项。没有授权不要同时做 PyPI 发布、GitHub Pages 部署或公网服务开放。

## 18. 给另一个模型的可直接复制任务提示

> 请接手本仓库的 GitHub 首次发布与文档摘要工作。首先阅读 `docs/HANDOFF.md`、`README.md`、`docs/ACCEPTANCE-v1.3.1.md`、`PRIVACY.md`、`SECURITY.md`、`DISCLAIMER.md`，并核对当前代码与 Git 状态。当前源码为 1.3.1；交接时 main 尚无提交、无 remote，项目文件未跟踪。不要假设状态未变化。  
> 目标是发布默认空白的中文本地个人健康档案，不是演示数据库、自动诊断产品或全量多端同步系统。保留核心医疗/隐私边界；不要把 Codex 模拟测试称作真实账号/模型成功。  
> 先向我确认 GitHub 账号/组织、仓库名、可见性、远端地址、提交身份，以及是否创建 Release。仅在确认授权后进行提交、推送、tag/Release/PR 等操作。不要擅自部署公网服务。  
> 全量测试并检查候选提交文件；明确排除 `.local-*`、数据库、附件、`.codex-connection`、`auth.json`、Key、日志、医疗备份与互传包。不要读取/复制既有登录凭证，不删除我的任何本地资料。  
> 撰写简洁的中英文项目摘要、仓库简介、当前功能与未完成功能、安装步骤、测试情况、首次 Release Notes。现有 dist 包早于交接文档，若发布附件请从最终提交重新构建、验证并计算哈希。  
> 最后给我真实仓库地址、提交 SHA、实际测试/CI 状态、发布附件与校验和、已知限制和仍需我完成的事项。不要只输出计划或未经执行的“完成”声明。

## 19. 可供改写的项目简介和摘要

以下为文案候选，不是已经发布的内容。应结合最终测试及实际仓库链接更新。

### 19.1 中文一句话简介

> 中文优先的本地个人健康档案：可追溯原件、分科记录、可选 AI 草稿，以及手机加密资料和手动互传。

### 19.2 English repository description

> A Chinese-first, local-first personal health journal with traceable records, opt-in AI drafts, an encrypted mobile document vault, and manual file transfer.

### 19.3 中文项目摘要

> 知己 · 健康手记是一款默认从空白档案开始的个人健康记录工具。电脑端使用 Python 标准库、SQLite 和原生网页界面，组织就诊、检验、用药、症状、健康问题与随访，保留原件及出处，提供 55 个常见科室目录、指标趋势、一般饮食灵感和就医摘要。用户可按次授权 API 模型或独立的官方 Codex/ChatGPT 连接，生成餐食、报告及资料问答草稿；结果不自动转成临床事实。独立手机资料版支持拍照导入、加密本地保存、加密备份和手动原件互传。项目采用 MIT 许可，明确区分本地存储、第三方模型外发和跨端交换；不确诊、不开药，不提供治疗性营养计划或自动全病历同步。

### 19.4 English overview

> Health Journal is an empty-by-default, Chinese-first personal health record application. Its desktop edition uses the Python standard library, SQLite, and vanilla web assets to organize visits, lab observations, medications, symptoms, health concerns, reminders, and source documents. Optional API models or an isolated official Codex connection can generate structured drafts after explicit per-request consent. AI output is kept separate from verified records. A standalone mobile document vault offers local encryption, backups, and manual original-file transfer. The project is MIT-licensed and is not a diagnostic system, a prescribing tool, or an automatic multi-device medical-record sync service.

### 19.5 首次 Release Notes 草稿

```markdown
# 知己 · 健康手记 v1.3.1

默认空白的中文本地个人健康档案初版。核心运行无需云账号或前端构建。

## 包含什么
- 六类健康记录、原件追溯、55 科目录、多科关联、时间线、指标趋势和就医摘要。
- 受约束的一般成人家常餐单与实际饮食记录。
- 逐次授权的 API / 独立 Codex 连接，餐食、报告与问答草稿。
- 手机本地加密资料库、拍照入口、加密备份及手动原件互传。
- 默认不填姓名、饮食偏好或病历，不自动注入演示数据。

## 验证情况
发布者填写此次实际运行的测试数量、环境、CI 链接和已知失败。
交接基线是 259 个不同测试通过（164 Python + 95 Node），不是未经重跑可直接沿用的发布结论。

## 重要边界
- 不确诊、不开药、不调整剂量，不以 AI 代替医生。
- 桌面数据库/附件/ZIP 未做应用层加密；Codex 凭证可能落地明文。
- 手机当前仅为资料版，不提供桌面全部功能或模型登录；跨端仅手动原件交换。
- 真实账号/模型推理和物理手机兼容性尚未完成全面验证。
- 含空称呼或未填饮食偏好的新备份应由 1.3.1 或更新版本恢复。

请阅读 README、DISCLAIMER、PRIVACY、SECURITY 和对应验收报告，再决定是否保存真实资料。
```

### 19.6 不要采用的宣传用语

- “保证不会有任何 Bug / 100% 安全 / 医学准确率保证”。
- “自动诊断全身疾病 / 精准预测患病概率 / 自动调整用药”。
- “任何 ChatGPT 账号都能免费无限调用 / ChatGPT 订阅就是 API 额度”。
- “所有健康资料从不离开设备 / 全部数据都端到端加密”。
- “手机与电脑病历实时全量同步 / 手机可直接登录桌面 Codex”。
- “所有科室全集 / 已完成临床验证 / 已通过外部安全认证”。
- “Actions 已通过 / GitHub 已发布”，除非已经实际观察到相应状态。

## 20. 最终交付应包含什么

- 用户确认的仓库地址、可见性与真实提交 SHA。
- 实际执行的测试命令、数量、环境和结果；Actions 链接及观察到的状态。
- 发布摘要、README 主要更新和限制说明。
- 如有 Release：实际 tag、Release 链接、选定附件、重新计算的校验和。
- 明确说明没有上传个人数据、登录凭证或历史本地库；如未能完成某项审查，说明范围而非声称全覆盖。
- 尚需用户完成的账号授权、真机验证、私有安全渠道配置或托管决策。

交接的成功标准是：**下一位维护者能找到代码、理解真实边界、复现运行和测试，并把不含私人资料的项目安全地提交到用户指定仓库。** 不是把功能数量或测试数字包装成医疗效果保证。
