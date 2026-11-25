# Apple 健康、Apple Watch 与饮食记录：接入调研和设计结论

核对日期：2026-11-22（Asia/Shanghai）。本轮读取 Apple 官方导出/授权/来源优先级文档，以及 3 个相关 GitHub 项目的 README 与许可文件。未登录用户 Apple ID、未读取真实健康库、未安装参考项目，也不把项目自述当作独立临床验证。

## 1. 结论

**可以接入 Apple Watch 等设备已汇入“健康”的记录，但接入方式必须区分：**

| 路径 | 是否可行 | 条件 | 本项目本轮状态 |
| --- | --- | --- | --- |
| iPhone 健康导出 ZIP/XML → 电脑本地导入 | 可行 | 用户主动导出和传递文件 | 已实现，可在现有 Python/网页架构使用 |
| 原生 iOS HealthKit 读取 | 可行 | 原生 App、HealthKit capability、用途说明、逐类型用户授权、签名和真机验收 | 研究及后续方案；本轮没有假装发布原生 App |
| 浏览器/PWA “用 Apple ID 登录”读取手表数据 | 不能作为 HealthKit 接入方案 | Apple ID 登录与 HealthKit 数据授权不是一回事 | 不提供伪登录入口、不抓 iCloud Cookie |
| 原生 App 定期传给自建同步服务 | 技术上可行 | 配对、端到端加密、撤销/删除传播、权限与后台调度约束 | 未实现，不开放现有电脑服务到 LAN |

“接入心率、步行等”和“好好吃饭放在一起”的合理第一层，是**具有来源、日期和缺失说明的个人回顾**，不是用步数决定补偿多少热量，也不是从饭后心率直接推断某种病。

## 2. Apple 官方资料核查

### 2.1 数据从哪里来

[Apple：管理 iPhone、iPad 或 Apple Watch 上的健康数据](https://support.apple.com/en-us/108779) 说明：iPhone 可计步和记录步行/跑步距离，配对 Apple Watch 可贡献活动、心率等信息，其他 App 或手工录入也可能成为来源。

**影响实现：**“Apple 健康导出”并不等于“全部来自 Apple Watch”。必须保存 sourceName、device、sourceVersion、手工录入标记，不给其他 App 或个人录入的数据贴上手表测量认证。

### 2.2 文件导出

[Apple：在 iPhone 上的“健康”中共享数据](https://support.apple.com/zh-cn/guide/iphone/iph5ede58c3d/ios) 明确支持将健康/健身资料导出为 XML：健康 → 摘要 → 头像/姓名首字母 → 导出所有健康数据。

**影响实现：**让用户选择导出的 ZIP 或解压后的 HealthData 主 XML；不依赖文件一定名为英文 `export.xml`。ZIP 可能含 CDA、训练 GPS 等其它内容，不应全部解压、导入或外发。本轮只识别一个 HealthData 根节点的主 XML，中文名称也可用；没有把 `export_cda.xml` 当成主要样本文件。

### 2.3 原生授权不是登录

[Apple：Authorizing access to health data](https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data) 要求按类型分别申请读/写权限、设置 HealthKit capability 和用途说明、先检查设备 HealthKit 可用性。

Apple 明确保护读权限的私密性：App 不能简单判断用户是否拒绝读取；部分情况下读取不到数据。**不能把 requestAuthorization 成功理解为每种读权限全部获准，也不能把空结果理解为用户没有相应活动或疾病。** 当前文档还描述了受限时间窗口权限，需要原生实现单独处理。

**影响实现：**本网页没有虚构一个“已获得手表授权”的状态；显示“本地文件连接”。缺失留空，不记作 0，不作为健康结论。

### 2.4 来源优先级

同一份 [Apple 管理数据文档](https://support.apple.com/en-us/108779) 说明，健康 App 会按来源优先级整理类似数据，用户可调整顺序。系统并不是把 iPhone、Watch、第三方 App 的同一段步数全部相加。

[HealthKit separateBySource](https://developer.apple.com/documentation/healthkit/hkstatisticsoptions/separatebysource) 可在原生统计查询中按来源计算。

**影响实现：**文件导入看不到用户完整的系统来源优先级状态，不能谎称重建 Apple 内置总量。多来源日值先留空，用户选择一个来源后统计。同来源累计样本发生重叠时，也不自行猜哪条优先；保留明细并提示无法可靠总计。

### 2.5 增量和后台

- [HKAnchoredObjectQuery](https://developer.apple.com/documentation/healthkit/hkanchoredobjectquery)：原生增量读取须处理 anchor 及删除对象，不能只做“每隔几小时把最近一天追加”。
- [HKObserverQuery](https://developer.apple.com/documentation/healthkit/hkobserverquery)：观察变化后再查询内容，不是无限可靠的后台推送服务。
- [Protecting user privacy](https://developer.apple.com/documentation/healthkit/protecting-user-privacy)：HealthKit 的健康数据隐私要求必须纳入产品和发布设计。

**影响实现：**本轮用内容哈希做文件重复导入的幂等与本地批次引用；没有把它称作原生增量同步，不传播 Apple 端删除。真正自动同步是独立工作，不应通过裸开本地端口来替代。

## 3. GitHub 项目的启发

以下只借鉴公开功能/设计思路，未复制源码、截图或私有数据。许可不代表其医疗效果、安全性或兼容性经过本项目验证。

| 项目 | 已读取内容/项目自述 | 本项目吸收的做法 | 不照搬的部分 |
| --- | --- | --- | --- |
| [PulsHealth/pulshealth](https://github.com/PulsHealth/pulshealth) | README、Apache-2.0 许可；iOS 文件导出、自托管数据库、同步协议；明确后台依赖 iOS/权限/Watch 到手机交付 | 清楚区分“导出”“数据库同步”“AI 访问”；先展示类型、时间、来源和数据去向 | 不引入其 PostgreSQL/TimescaleDB/公网服务栈，不把其 App 宣称为本项目内置组件 |
| [RuochenLyu/apple-health-analyst](https://github.com/RuochenLyu/apple-health-analyst) | 中文 README、MIT 许可；本地 ZIP/XML、长期趋势、资料缺口、跨指标观察与推断区分 | 不做伪精确健康评分；识别 HealthData 主 XML 而非固定英文文件名；同屏长期上下文 | 不复制 CTL/ATL/训练负荷估算，不把统计关联写成个人医疗判断，不自动喂完整健康摘要给托管模型 |
| [avechri/apple-health-dashboard](https://github.com/avechri/apple-health-dashboard) | README、MIT 许可；本地解析 XML 到静态看板、活动/睡眠/步数 | 简洁本地看板、柱状日值和可追溯详情 | 不采用 consistency score，不把“privacy-safer”摘要视为可默认公开，不发布用户健康 JSON 到 GitHub Pages |

可复查许可：[PulsHealth LICENSE](https://github.com/PulsHealth/pulshealth/blob/main/LICENSE)、[apple-health-analyst LICENSE](https://github.com/RuochenLyu/apple-health-analyst/blob/main/LICENSE)、[apple-health-dashboard LICENSE](https://github.com/avechri/apple-health-dashboard/blob/main/LICENSE)。发布时应重新核查，不能据此获得 Apple 商标或 HealthKit 分发权限。

## 4. 本轮数据设计

### 4.1 不混进临床指标表

可穿戴样本数量可达数十万，且心率采样不是医院化验。新增独立样本/批次/引用表，保留原值、单位、原始时区、来源、版本、类别及手工标记。原有就诊、检验、饮食、草稿表继续独立。

### 4.2 日期口径先固定再展示

- 日期采用样本结束时间的原始偏移时区，不采用运行电脑当前时区。
- 跨日样本整体归结束日，并显示警告；不臆造均匀活动分布后按比例拆步数。
- 睡眠按每个样本结束日分组后取睡着区间并集；不是严格按“睡眠会话/夜”合并。分期和完整睡眠跨不同结束日时可能与 Apple 展示差异明显，不能拿日值当作临床睡眠时长。
- 夏令时的真实时长通过带偏移时间戳差值计算，而不是简单用钟面时间相减。
- 缺失、冲突和真实零区分；均值只包含有效日值，不补齐缺失天。

### 4.3 饮食关联保持事实

只读取已勾选实际吃过或有实际备注的餐单记录，以及用户自行核对保存的饮食分析备注。未吃的菜谱计划、AI foods 猜测不进入“实际饮食”。

活动能量、静息能量和已记录摄入能量分别展示。**不自动相减，不给“今天还可以吃多少”，不按心率生成治疗餐单。** 体重、睡眠、HRV 等与饮食同日出现，不足以证明因果。

## 5. 视觉设计决策

沿用已有墨蓝导航、松绿强调、浅色面板与系统中文字体，新增“日常健康”，与临床“指标趋势”分开。

1. 首屏交代数据通路和最近记录日期，显示样本数而不是身体评分。
2. 导入预览在统计之前；有效项、重复项、跳过项和来源可核对。
3. 趋势显示日期、指标和来源筛选，三项概览是末日值、有效日数、有效日值均值；不假装全天覆盖。
4. 本地 SVG 柱图标记缺口而不插值连线；数值在可读表格中同样可见。
5. 同日回顾用设备值/口径/实际饮食/原始样本依据四部分，不做颜色“正常/异常”医学评级。
6. 手机宽度使用纵向表单和卡片，长表格在自身容器横向滚动，不让整页溢出。
7. 导出回顾采用明确警告后的 TXT 下载链接，可复用已有手机 TXT 导入和加密存储，不伪装成结构化同步。

## 6. 原生直连后续必须满足的条件

本机检查发现只有 Command Line Tools，没有完整 Xcode 环境；也没有用户授予的 iPhone HealthKit 权限或可用于签名的开发者配置。因此不能负责任地把未经编译/真机验证的 Swift 壳称作已交付实时集成。

真正实施时至少需要：

1. 原生 App 中先选择业务所需类型，再申请只读权限；默认不写 HealthKit。
2. 对无数据、部分权限、受限时间窗口、撤销、锁屏、设备不支持分开处理，不能猜读权限结果。
3. 用 anchored queries 持久化每类型游标，处理新增、更新/删除及重放；统计需保留来源和单位规则。
4. 明确与桌面配对、加密信任、设备撤销、冲突、删除传播和备份范围；不能复用静态页面上的共享 API Key。
5. 后台与离线任务遵守系统调度，不承诺每分钟同步；显示最近成功同步和缺口。
6. 完整 Xcode 编译、签名、真实 iPhone/Watch 的授权/撤销/增量/重复/断网/重启测试，独立隐私审查后再交付。

本轮交付的完整范围是**现有架构内可用的官方文件导入与本地回顾链路**，不是原生自动同步。具体用法、指标、限额与测试见 [APPLE_HEALTH.md](../APPLE_HEALTH.md) 和 [1.4 验收报告](../ACCEPTANCE-v1.4.0.md)。
