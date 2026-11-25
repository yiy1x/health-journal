# 本地 API 与数据约束

## DeepSeek 兼容适配（1.5 补充）

`cloud.py` 新增 `deepseek` 预设（`https://api.deepseek.com`），同时兼容在 `custom` 下填写 `https://api.deepseek.com` 或 `https://api.deepseek.com/v1`：

- 纯文字请求将 `messages[].content` 归一化为字符串，避免只接受字符串 `content` 的兼容端点返回 400；携带图片或 PDF 时继续发送多模态数组。
- 对 DeepSeek 请求显式设置 `thinking: {"type": "disabled"}`、`response_format: {"type": "json_object"}` 与 `max_tokens: 8192`，避免默认思考模式消耗完输出长度导致草稿被截断或返回空白内容；不依赖 OpenAI 专用的 `store` / `max_completion_tokens`。
- 补充 `402`（余额不足）、`422`（参数或模型名无效）和空 `content` 的中文错误提示；公网 HTTPS 连接超时调整为 120 秒，仍保持全公网 DNS 校验、固定 IP、禁止重定向与不自动重试。

## 日常手记（1.5）

数据库 schema v4，新增 `food_entries`，不替换旧餐单/分析记录。新接口使用同一回环/随机令牌/跨站/严格 JSON 保护：

| 接口 | 行为 |
| --- | --- |
| `POST /api/food` | `{id,date,time,meal,note,document_id}`；id 为客户端 UUID，同 id 同内容重复请求返回已存内容，不重复新增；不同内容冲突 409 |
| `PUT /api/food` | 同字段加 `version`；旧版本/已删除返回 409；不能用 PUT 创建不存在的记录 |
| `DELETE /api/food` | `{id,version,confirm:true}`；只删除日记，照片保留 |
| `GET /api/food?from=...&to=...` | 返回 1–366 日的独立实际饮食，按日期/时间/ID 排序 |
| `GET /api/day?date=...` | 当天 steps/sleep/heart_rate/distance 概况；可附每项 `*_source`，指标独立选择来源，不改变原样本 |

`time` 可空或 HH:MM，`meal` 为 breakfast/lunch/dinner/snack，`note` 必填最多 2000 字符，日期不能晚于本地服务今天，原件必须存在并通过校验；最多 10000 条。查询拒绝未知或重复参数。

`GET /api/wearables` 的 meals 新增独立日记 `origin:journal`，旧餐单为 `origin:plan`、AI 旁人工核对备注为 `origin:analysis`。不自动合并同餐，保留编辑来源。`/api/state` 不返回整个饮食表；按日期查询。AI `include_records` 不增加对新日记的隐含读取。

有日记时 ZIP manifest 使用 v4，必须包含 `food_entries`；可带已有 `wearable`/`wearable.jsonl`。无日记的备份仍用 v2/v3。恢复验证记录、版本、日期和附件引用，整体事务写新空库。旧程序不能打开新 schema 或 v4 备份。

## Apple 健康 / 日常健康（1.4）

统一受回环会话、Host/Origin/Fetch Metadata 和 JSON 严格检查保护。全部为本机操作，不访问 Apple 账号或远程网络。

| 方法与路径 | 输入和行为 |
| --- | --- |
| `POST /api/wearables/import` | 二进制 ZIP/XML，`Content-Type: application/octet-stream`、百分号编码 `X-Filename` 和明确 Content-Length；上限 256 MiB，返回 202 和 job ID |
| `GET /api/wearables/import` | 当前 job 状态 `idle/uploading/parsing/ready/error/cancelled/completed`、进度、有效/重复/跳过报告；不返回原 XML |
| `DELETE /api/wearables/import` | `{id}`，取消对应预览/解析，不删除已提交样本 |
| `POST /api/wearables/commit` | `{id,metrics:[...],from,to,confirm:true}`；冻结预览、类型/结束日期范围、本人确认，事务保存；过期/重复消费 409 |
| `GET /api/wearables?from=YYYY-MM-DD&to=YYYY-MM-DD&metric=steps&source=` | 最多 366 日；返回 catalog、来源、日值、实际饮食与导入批次；source 为空时多来源日值留空 |
| `GET /api/wearables/details?day=YYYY-MM-DD&metric=steps&source=&offset=0` | 一页最多 50 条，返回原值/单位、标准化值、时间、来源和手工标记 |
| `DELETE /api/wearables/batches` | `{id,confirm:true}`，删除批次引用及无其他批次引用的样本；不修改 Apple 健康或饮食 |

查询不接受重复/未知参数；ID 和 source 都是应用生成的不可执行标识，不是文件路径。`/api/state` 只增加 `wearables` 的指标目录、样本计数、最早/最近日期概况，不返回百万条样本。设备数据不加入 AI 默认或 `include_records` 摘录。

SQLite schema v3；有设备数据的便携备份清单 v3 声明 `wearable: {path:"wearable.jsonl",sha256}`。JSONL 依序保存 batch/sample/member，检查原值标准化一致性、身份哈希、批次数量和范围引用，恢复只能到空档案并与其它数据事务提交。上限与完整口径见 [APPLE_HEALTH.md](APPLE_HEALTH.md)。

## 空白个人档案（1.3.1）

新建目录不预置资料。`profile.name` 可为空字符串；`profile.diet` 支持 `unspecified`（未填写，初始值）、`balanced`、`vegetarian`。出生日期/联系人/备注/饮食医嘱为空，性别初始 `unspecified`，过敏数组为空、膳食确认 false，不等于无过敏或可安全生成餐单。`diet` 未选择时，即使勾选一般成人适用确认，生成餐单仍返回 422。已有设置不自动清除。

新值兼容于当前 schema v2，但旧应用可能拒绝空称呼/未填偏好；含这些值的备份用 1.3.1 或更新版本恢复。

## Codex 可选接口（1.3）

全部使用同一回环会话保护，不提供通用 RPC 代理：

| 方法与路径 | 请求及效果 |
| --- | --- |
| `POST /api/codex/connect` | `{confirm:true}`，启动隔离 stdio CLI 并核验配置 |
| `POST /api/codex/login` | `{confirm:true}`，开始官方 ChatGPT 登录，返回允许的官方链接 |
| `POST /api/codex/refresh` | `{confirm:true}`，更新账号与模型，不分析资料 |
| `POST /api/codex/cancel-login` | `{confirm:true}`，取消待完成登录 |
| `POST /api/codex/logout` | `{confirm:true}`，退出该隔离连接的账号 |
| `POST /api/codex/disconnect` | `{confirm:true}`，停子进程但保留凭证 |
| `PUT /api/codex/config` | `{model,vision,revision}`，只接受账号模型列表及报告的图像能力 |
| `POST /api/codex/prepare` | 与 AI 预览相同的 task/text/document_id/include_profile/include_records；冻结授权 |
| `POST /api/codex/run` | `{approval_id,confirm:true}`，消费单次授权并保存校验后的草稿 |
| `POST /api/codex/cancel` | `{approval_id}`，仅取消匹配的在途请求 |

`GET /api/state` 增加 `codex`：连接/认证状态、邮箱/套餐、模型列表、模型配置/revision、登录链接、busy 和在途 operation ID，不返回凭证。这里 `has_key` 兼容原界面字段，表示已登录且选中可用模型，**不代表存在 API Key**。控制操作/账号变化使待确认授权失效。

不直传 PDF，不访问任意模型端点。Codex 采用 stdio JSONL，不适用本文后续 API Key 的 Chat Completions 传输细节。RPC 通常 15 秒，分析事件截止 150 秒；清理等可能增加等待时间。输入 JSONL 最多 13 MiB；一般响应/事件最多 2 MiB；用户消息回显允许到 13 MiB，立即移除重复内容，仅保留类型/ID；仅对需要的生命周期事件排队，队列 32 项。输出草稿还受本地字段/数量/长度约束。错误没有自动重试，取消不保证上游未计费。设计、凭证风险和兼容边界见 [CODEX.md](CODEX.md)。

这些接口服务于同一台电脑上的单人界面，不是开放医疗平台。请勿公开映射端口或给其他站点访问权限。

## 访问要求

默认地址 `http://127.0.0.1:8765`。页面从服务端 HTML 中取得每次启动生成的令牌，通过 `X-Journal-Token` 发送；所有 `/api/` 请求都要求令牌。服务重启后需要刷新页面。

Host 必须匹配本机地址及服务端口；如果存在 Origin/Fetch Metadata，也必须满足同源规则。令牌不是操作系统用户间的身份验证，能读取本机页面的程序可能取得它。

JSON 请求使用 `Content-Type: application/json`，根对象必须是对象，不允许 NaN/Infinity、重复字段或无法编码为 UTF-8 的文字。正常错误返回 `{"error":"可展示的错误信息"}`。

1.1.1 拒绝重复 Host、Origin、Sec-Fetch-Site、X-Journal-Token、Content-Type、Content-Length，返回 400；缺少请求体长度返回 411。非 ASCII 令牌为 401。所有应用响应带 `Connection: close`，不复用有未读请求体的连接。模型 Base URL 拒绝控制字符，避免 URL 解析时静默去除字符。

## 接口列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 当前档案、记录、原件元数据、餐单、一般食谱、安全限制、操作日志等；不包含原件正文 |
| PUT | `/api/profile` | 完整替换档案；必须提交 `_version`，取自 state 的 `profile_version`，不符返回 409 |
| POST | `/api/records` | 新增记录，返回 201 及服务端 ID/版本/创建时间 |
| PUT | `/api/records/{id}` | 完整替换记录；提交读取时的整数 `version`，不符返回 409 |
| DELETE | `/api/records/{id}` | JSON `{"version":1}`；仅删除记录，不删除原件 |
| POST | `/api/documents` | 原始二进制请求体；`X-Filename` 为 UTF-8 百分号编码文件名；单文件 ≤20 MB |
| GET | `/api/documents/{id}` | 读取并校验 SHA-256；作为附件下载，不在服务器内执行 |
| DELETE | `/api/documents/{id}` | 若被临床记录或分析草稿引用，返回 409 |
| PUT | `/api/documents/{id}/routing` | `version`、`status:confirmed`、`method`、`links`；最多 12 个目录内科室 |
| PUT | `/api/ai/config` | `provider`、`base_url`、`model`、布尔 `vision`、`api_key`、当前 `revision`；不调用服务商 |
| DELETE | `/api/ai/key` | 清空 RAM Key 及待授权快照，不能撤回已发送请求 |
| POST | `/api/ai/prepare` | `task`、`text`、可空 `document_id`、布尔 `include_profile` / `include_records`（默认 false）；仅生成预览 |
| POST | `/api/ai/run` | `approval_id` 与严格布尔 `confirm:true`；消费一次授权，返回独立草稿 |
| PUT | `/api/analyses/{id}` | 仅早餐草稿可编辑实际饮食：`version`、`date`、`meal`（breakfast/lunch/dinner/snack）、`note` |
| DELETE | `/api/analyses/{id}` | `version`；删除草稿及附属实际饮食，不删除源文件或临床记录 |
| POST | `/api/plans` | `{"date":"YYYY-MM-DD"}`；按当前限制生成三餐，有实际记录时拒绝覆盖 |
| PUT | `/api/plans/{date}` | `meal`、`revision` 及 `swap:true`，或 `eaten`/`note`；采用版本保护 |
| POST | `/api/assistant` | `question` 和可选布尔 `use_model`；默认规则检索，不写入医疗记录 |
| GET | `/api/models` | 获取固定回环地址 Ollama 的模型列表，不发送健康记录 |
| PUT | `/api/model` | `{"model":"本机模型名"}`；空字符串关闭配置，不在保存时发送健康资料 |
| GET | `/api/backup` | 导出经完整性检查的未加密 ZIP；请按敏感信息保护 |
| POST | `/api/restore` | 原始 ZIP 请求体，并带 `X-Confirm-Restore: empty-vault`；只能恢复到空档案 |
| GET | `/api/transfer` | 导出未加密原件 JSON 资料包；不含临床记录、个人信息字段、餐单、AI、分科确认或 Key，但附件本身可能含身份信息 |
| POST | `/api/transfer` | `Content-Type: application/json` 和 `X-Confirm-Transfer: append-originals`；先整体校验，再事务新增；返回 imported/duplicates |

1.2 互传格式：`{"format":"health-journal-transfer","version":1,"documents":[...]}`，每项严格只含 `filename`、`mime`、`sha256`、`content`（规范 Base64）。上限 58 MB 请求体、500 份、解码原件合计 40 MB，单份 20 MB；未知字段/版本、重复摘要、非法编码、签名/哈希不一致均拒绝。相同内容保留已有名称与分类，同名不同内容都新增；不传播删除。重复 `X-Confirm-Transfer` 头拒绝。该 API 仍仅允许本机同源会话，不是手机网络同步 API。

独立 `/phone/` 页面与允许的静态资源不含桌面 API 令牌；`/phone/catalog.json` 是公开目录数据。手机页面不调用桌面 API。托管手机端应使用静态导出器，而不是暴露本机 HTTP 服务。详见 [MOBILE.md](MOBILE.md)。

除原件导入和恢复以外，请求体默认上限为 1 MB。拒绝 Transfer-Encoding 请求和重复 Content-Length。文件签名检查不是完整格式解码或恶意文件扫描。

## 记录结构

通用字段：`kind`、`title`、`date`、`department`、`topic`、`notes`、`source_label`、`document_id`、`verification`、`data`。

- `kind`：`visit` / `observation` / `medication` / `symptom` / `condition` / `reminder`。
- `date`：ISO 日期，除提醒外不能晚于电脑本地今天，年份不早于 1900。
- `document_id`：空或现存原件 UUID；不是外部 URL。
- `verification`：`pending` 或 `verified`；仅表示用户是否核对录入，不代表医学可信度。
- 服务端增加 `id`、`version`、`created_at`、`updated_at`，不接受客户端任意指定新记录 ID。

类型专用 `data`：

| 类型 | 字段 |
| --- | --- |
| visit | `hospital`、`doctor`、`reason`、`conclusion` |
| observation | `value`、`comparator`（`=`/`<`/`>`/`≤`/`≥`）、`unit`、可空参考界限 `reference_low`/`reference_high`、`lab` |
| medication | `dose`、`frequency`、`start_date`、`end_date`、`status`（active/stopped/planned）、`prescriber` |
| symptom | `severity`（0–10 整数）、`status`（ongoing/resolved）、`duration`、`triggers`、布尔 `red_flags` |
| condition | `status`（suspected/confirmed/ruled_out/resolved）；confirmed 要求关联原件 |
| reminder | 布尔 `done`、`category`（followup/check/other） |

主题是自由文字关联，不会合并或推导诊断；方法/单位不自动标准化。`active` 加有效日期只表示按记录当前有效，不保证实际服药。

## 餐单与备份

餐单日期唯一，包含版本、三餐菜谱 ID、每餐 `eaten`/`note`、生成时饮食约束与提示。返回的菜谱份量不是个体营养处方。档案限制改变后，`nutrition_restrictions` 及前端约束比较使旧餐单不再作为推荐；实际饮食仍可以记录。

未来餐单可以生成，但不能对未来日期写入 `eaten:true` 或非空实际饮食备注。修改档案/记录时，客户端必须提交**当前表单呈现时**的版本，而不是另一次后台刷新得到的版本；接口仍由后端最终检查冲突。

导出备份格式版本 2，恢复兼容 1/2。ZIP 仅允许 `manifest.json` 和被清单列出的 `attachments/{sha256}`。清单包含档案、原件元数据（含 `routing` / `routing_version`）、所有记录、餐单、分析草稿及发送依据、实际饮食和演示标记。恢复先完整校验，再在数据库事务中导入；不覆盖已有档案，不恢复 API Key、模型配置或旧操作日志。备份大小范围和完整目录备份流程见 README。

v2 缺少 `analyses`、附件 `routing` / `routing_version` 时拒绝恢复；v1 才使用明确兼容缺省。保存时间接受标准带时区 ISO 文本（`T` 分隔、秒及可选微秒、时区偏移，`Z` 规范为 `+00:00`），避免 Python 可解析而浏览器不可展示的时间。附件读取核对原长度、20 MB 上限和 SHA-256。

## 云分析契约（1.1）

`state` 新增 `departments`、`analyses` 和 `cloud`。`cloud` 包含服务商选项、地址、模型、视觉确认、`revision` 和 `has_key`，永远不回传密钥。`has_key` 表示内存中存在用户输入，不代表服务商验证成功。

任务为 `breakfast` / `document` / `chat`。预览返回冻结的 `text`、`system_prompt`、`source`（ID、文件名、MIME、大小、SHA-256）、`endpoint`、`model`、`approval_id`、`expires_in:600`。配置改变、过期、已使用或 Key 清除使授权失效。原件在发送前再次检查存在性和哈希。最多 8 个未过期预览；一次只能有一个在途模型请求。

饮食约束选项只附上过敏原、偏好、特殊需求、饮食医嘱、适用范围确认和限制原因，不附姓名/联系方式/出生日期；自由医嘱文本须自己脱敏。档案选项按说明前 1000 字符检索最多 12 条，预览完整展示实际摘录、引用及截取限制；不把这个子集称为完整病史。

草稿包含 `id`、`task`、`result`、`provenance`、`document_id`、`intake`、`version`、`created_at`。`provenance` 保存服务商/端点/模型/原件哈希/实际发送上下文；Key、Base64 附件不写进草稿。不是医学证明或不可伪造签名。

`result` 公共字段为 `summary`、`uncertainties`、`questions`。早餐增加 `foods[{name,portion,confidence}]`、`suggestions`；报告增加 `departments[{name,evidence}]`、`excerpts[{title,quote,location,department}]`；问答增加 `suggestions`。模型自评置信程度仅是草稿，不是测量误差或校准概率。

与模型仅使用单次非流式 Chat Completions 请求。输出根对象、字段类型、条目数量、长度和科名均校验；不合格返回错误，不写临床记录。模型故障/网络错误通常 502/503；授权/版本冲突 409；设置缺失或文件能力不支持 422。文件上限 8 MB、输出响应上限 2 MB、套接字操作超时 75 秒；不是总耗时 SLA。
