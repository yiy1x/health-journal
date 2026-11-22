# 追加调研：多模态模型、全身科室档案与舒适界面

检索日期：2026-11-13，Asia/Shanghai。对象是个人本地健康档案，不是面向诊所收费、挂号或处方的 HIS。本文接续[第一轮全景调研](2026-11-13-personal-health-assistant-landscape.md)，重点回答这次提出的三个问题：能否填 API Key 看早餐、报告能否跨科归档、现有 GitHub 项目有哪些体验值得借鉴。

## 结论先行

**这些能力分别已经能做，但“本地存储 + 云端大模型 + 上传后准确建病历 + 个体医疗建议”还不能合并为一个可靠性承诺。**

- 本地/自托管档案、来源关联、时间线、备份与趋势图已有较完整实现；需要在安装复杂度、跨设备能力与安全运维之间取舍。
- 视觉模型识别常见餐食、从报告照片提取文字、建议科室已经是可实现的软件能力；准确份量、隐藏配料、过敏原与药物/诊断推断不是看图就能可靠解决的。
- 比较合理的架构不是“AI 直接改数据库”，而是“原件 → 草稿 → 人工复核 → 结构化记录”。有项目已明确采用这条路线。
- 个人软件的舒适度不应靠伪精确健康评分，而应靠清楚的导航、适度留白、可读的中文、随时查看来源、少重复录入，以及不会突然外发资料。

因此本轮选择**保留轻量本地基础，增加可选 API、餐食分析草稿、报告整理和多科资料目录**，而不是引入整个医院系统或将健康资料默认交给一个聊天机器人。

## 检索与证据范围

直接读取 GitHub 仓库 API 元数据、README、相关源文件及视觉导览文档，并查阅服务商官方 API 文档。星数/更新时间仅用于说明社区规模与维护快照，**不用于证明软件质量、合规或临床有效性**。`pushed_at` 是仓库推送时间，不是稳定版本发布时间。下表时间为 UTC 日期，网页后续会变化。

没有批量安装这些第三方项目，没有拿真实患者资料测试，没有把 README 中的“临床级”“零泄漏”当成经过验证的事实。我们自己的浏览器/接口验收另见 [v1.1 验收](../ACCEPTANCE-v1.1.md)。

| 项目 | 本次 API 星数 / 最近推送 | 阅读中看到的能力 | 判断及适用性 |
| --- | --- | --- | --- |
| [MediKeep](https://github.com/afairgiant/MediKeep) | 558 / 2026-11-12 | 自托管医疗记录、药物管理、仪表盘、Report Builder、备份；README 提供对应页面截图 | 适合借鉴“档案优先、药物集中、就医报告”，不是本地早餐识别的一站式答案 |
| [Health Assistant](https://github.com/health-assistant-io/health-assistant) | 34 / 2026-11-09 | README 标注 v0.9.0 Beta；FHIR、OCR/AI 管线、多租户、健康主题、可自带兼容模型；AI 写入须用户确认 | 与需求最接近的架构参考，但基础设施较重，README 的 clinic-compatible 不等于临床批准 |
| [MedMe · 医我](https://github.com/Chesterguan/medme) | 14 / 2026-11-12 | 中文优先、原件保留、OCR/置信提示、按类型渲染、时间线、DICOM/分享；当前主要交付手机端，桌面无公开安装包 | 适合借鉴中文资料整理和原文核对；不能把其所有平台的 OCR/隐私路径理解为完全一致 |
| [Mealie](https://github.com/mealie-recipes/mealie) | 13,887 / 2026-11-13 | 自托管菜谱、餐单、购物清单与结构化配料；README 展示食物卡片界面 | 适合日常生活闭环和低负担餐单，不是疾病营养处方软件 |
| [Open WebUI](https://github.com/open-webui/open-webui) | 158,544 / 2026-11-13 | 本地/兼容模型连接、通用模型交互、自托管；README 提醒独立项目 | 适合借鉴 endpoint/model/key 的连接层，不把通用聊天记录当健康事实库 |
| [health-coach](https://github.com/H1an1/health-coach) | 66 / 2026-03-22 | Agent skill；餐食图文分析、中文食物资料、Apple Health 导入、报告；建议产品包装营养标签作为食品来源 | 技能集合不是完整医疗档案应用；“临床级”“100%本地/零上传”需看承载 Agent 实际模型路径，未获独立证实 |
| [MamiHealth.AI](https://github.com/yuanxiaochenAC/MamiHealth.AI) | 16 / 2026-02-11 | 照片优先的饮食伙伴、温和陪伴式交互；源码把图像和用户条件发给 Gemini，返回菜名/热量/评分等 | 能借鉴“一餐一次”的入口，不能照搬估算分数或把包装外观当隐藏配料证据 |

### 关键证据 1：AI 应当提出建议，而不是直接写事实

[Health Assistant README](https://github.com/health-assistant-io/health-assistant/blob/main/README.md) 使用 “Proposes, never writes”，明确通过 review card、用户编辑/确认和同一 REST 写入入口完成操作。[视觉导览](https://github.com/health-assistant-io/health-assistant/blob/main/docs/SCREENSHOTS.md) 单独列出 documents、biomarkers、examinations、AI chat / HITL 卡片，不把所有内容都塞进聊天流。

本项目采用相同原则但不复制实现：

1. 原件不可被 AI 覆盖。
2. API 返回仅能保存到 `analyses`，不创建 `records`。
3. 科室建议只能在用户核对后成为 confirmed 关联。
4. 临床摘录候选打开人工表单，不自动填写检查数值、单位或日期。
5. “模型识别到鸡蛋”与“用户确认吃了鸡蛋”分别保存。

### 关键证据 2：早餐照片可用于识别，不宜输出伪精确结论

实际阅读 [MamiHealth.AI 的 Gemini 服务源文件](https://github.com/yuanxiaochenAC/MamiHealth.AI/blob/main/services/geminiService.ts)：`analyzeFoodImage` 将 `inlineData` 图像与 conditions/allergies/goals 组合，要求生成食材、热量、1–10 健康评分及风险标签，并带有按时间推断晚餐/夜宵的规则。这证明多模态接入的可行性，**并不证明评分、热量或风险标签准确**。照片可能是历史照片，外卖外观也不能确定油盐含量。

本项目因此只输出食物候选、无法确认的份量、温和建议和追问；不生成精确克数、营养量、健康分数或疾病概率。实际日期与餐次由用户填写。包装配料、称重与医生医嘱优先于照片猜测。

### 关键证据 3：本地保存不等于从不外发

Health Assistant 的自带模型、MedMe 不同平台/版本的提取路径、Agent skill 的上下文模型，都说明必须区分四件事：原件放在哪里、计算发生在哪里、Key 放在哪里、授权发生在哪一步。

我们的边界是：上传先落本机；点击 AI 整理仍先生成发送预览；再次明确确认才外发。默认不包含个人档案/病史，可分别选择最小化饮食限制和最多 12 条记录摘录。**Key 输入不是全库授权。**

对用户更诚实的标签是“本地档案 · 云端可选”，不是启用在线模型后继续显示“零上传”。API Key 采用进程 RAM 保存，牺牲重启免输入的便利，避免把“加密 Key”和解密密钥放在同一目录造成误解。进程内存/交换区也不是绝对安全区，限制详见 SECURITY。

## UI / UX 的具体借鉴与不采用项

| 维度 | 借鉴对象与模式 | 本项目落地 | 有意不采用 |
| --- | --- | --- | --- |
| 认知负担 | MediKeep 的档案/药物/报告分工 | 左侧固定导航，首页仍以个人档案为主；新增全科室与模型连接 | 把聊天设为唯一主入口；医院收费/挂号式菜单 |
| 整理流 | Health Assistant / MedMe 的原件与候选分离 | 原始资料 → 分类建议/报告草稿 → 核对 → 科室关联/记录 | OCR/LLM 一返回就自动成为已确认病历 |
| 一餐的入口 | MamiHealth 的照片优先与温和语言 | “看懂这一餐”，照片或文字可选；建议与不确定性分栏 | “不健康”“违规”“你得了……”式指责；伪精确评分 |
| 日常闭环 | Mealie 的计划、实际执行与购物 | 保留三餐/换餐/采购清单；AI 实际饮食另行确认后汇总 | 把一张照片推成完整治疗食谱 |
| 连接层 | Open WebUI 的兼容模型配置思路 | provider、Base URL、model、Key 和视觉能力确认 | 浏览器直连服务商、前端 bundle 中藏 Key、任意工具执行 |
| 数据密度 | 结构化记录而非无尽聊天 | 输入/结果双栏，草稿历史，来源折叠区；55 科按 7 组展开并可过滤 | 首屏铺满 55 个图表、空白显示健康正常 |
| 舒适度 | 档案工具的稳定层级与饮食工具的低压力入口 | 墨蓝/松绿、雾白背景、系统中文字体、明确文字状态；窄屏单栏、导航横向滚动 | 复制第三方品牌、外部追踪字体、以彩色红绿代替文字含义 |

这些是对公开资料中交互结构的比较，以及我们自己的设计取舍，**不是对七个产品做过同条件可用性实验后的排名**。未进行正式用户访谈、屏幕阅读器验收或 WCAG 认证。

## 模型协议的官方核对

- [OpenAI 图像输入指南](https://developers.openai.com/api/docs/guides/images-vision)：支持在 Chat Completions 中使用图像 URL / Base64 data URL；文档指出小字、非拉丁文字、计数和医学图像等限制。采用报告文字整理而不是 CT/MRI 像素诊断。
- [OpenAI PDF 指南](https://developers.openai.com/api/docs/guides/pdf-files)：阅读 `file` / `file_data` 的 PDF 内容格式；视觉能力须由所选模型支持。本项目为了大小、成本和错误控制，限制为单份 ≤8 MB，而不是复制服务端最大额度。
- [百炼 OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)：核对中国内地 `https://dashscope.aliyuncs.com/compatible-mode/v1`。不同地区 Key 和 endpoint 不混用；本版内置中国内地入口，其他地区可自定义。
- [硅基流动 Chat Completions](https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions)：核对 `https://api.siliconflow.cn/v1/chat/completions`。模型图像能力和参数兼容不能仅凭 API 名称推定。

接口不是对所有模型的通用保证。没有在源码里硬编码未经账号验证的“最佳最新模型”；用户须填写其服务商真实可用的模型 ID。没有真实凭据时，不冒充调用成功。

## 数据流与科室覆盖

`用户上传 → 本地原件 + SHA-256 → 文件名/TXT关键词待分类 → 用户确认多科关联`

`选原件/文字 → 选择性附档案 → 展示发送快照 → 用户本次授权 → 服务商 → 合格的独立草稿 → 用户核对`

55 个目录覆盖综合与预防（6）、内科与慢病（11）、外科与运动（14）、感官口腔（5）、妇幼生殖（6）、心理康复（6）、检查治疗支持（7）。科室名称随医院不同而变化，目录不声称全国统一、穷尽所有亚专科。已有记录的自定义科名继续保留。

“分发”是多对多的资料关联，不是复制文件，更不是改变报告结论。原件挂到两个科室后，计数有交叉，不能跨科相加。就医分诊和疾病归因仍需专业评估。

## 许可证与复用边界

- MediKeep 的 GitHub API 返回 NOASSERTION，但实际 [LICENSE](https://github.com/afairgiant/MediKeep/blob/main/LICENSE) 文本明确指向 Apache License 2.0；不将 API 未识别误判为“无许可”。
- Health Assistant：Apache-2.0；MedMe、Mealie：AGPL-3.0；health-coach、MamiHealth.AI：MIT（均为此次读取的仓库声明，发布前需再核对具体文件及依赖）。
- Open WebUI 当前 [README / License](https://github.com/open-webui/open-webui#license) 明确包含其自定义许可与品牌保留要求，不能当成无条件 MIT 模板。
- 本次没有复制第三方源码、截图、图标、品牌或医学知识库到产品。只吸收交互和架构模式，新增实现为本项目原创。不能因项目 LICENSE 是 MIT 就推定它引用的食物数据库也可自由使用。

## 本轮可交付与下一阶段

本轮实际交付可配置 API、餐食图文负载、报告草稿、55 科目录/多科关联、逐次授权、安全传输、草稿历史、实际饮食确认、v2 备份及 v1 兼容恢复。软件流程通过合成测试；并非模型医学能力验收。

下一阶段优先级：

1. 用用户自选且已授权的模型，对**脱敏并获准使用**的小样本进行字段级识别评价，记录漏字、数字、单位、否定词、科室错误及人工纠正率；不要只给“看起来不错”的演示。
2. 本地 OCR + 原文位置高亮、逐字段复核，降低付费调用与隐私成本；评估模型许可证和平台覆盖。
3. 支持应用级加密、可恢复密钥与验证备份；先确定密钥丢失策略，再谈同步。
4. 在许可和专业审核到位后引入食物营养数据库；优先包装标签与称重，不以照片推算精确营养。
5. 与真实健康服务衔接时再做 FHIR 映射、专业安全评估、临床验证和监管适用性评估，而不是把 demo 叫作医疗器械。
