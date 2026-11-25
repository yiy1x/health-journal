(function (scope) {
  'use strict';
  const meals = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };
  const symbols = { steps: 'walk', sleep: 'moon', heart_rate: 'heart', distance: 'route', breakfast: 'sun', lunch: 'bowl', dinner: 'moon', snack: 'cup' };
  const paths = {
    walk: '<circle cx="14" cy="4" r="2"/><path d="m7 12 4-5 4 2 3 3m-7-5-1 7 4 3 1 5m-5-8-5 8"/>',
    moon: '<path d="M20 14A8 8 0 0 1 10 4a8.5 8.5 0 1 0 10 10Z"/>',
    heart: '<path d="M20 5a5 5 0 0 0-7 0l-1 1-1-1a5 5 0 0 0-7 7l8 8 8-8a5 5 0 0 0 0-7ZM3 11h5l2 4 3-7 2 3h6"/>',
    route: '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="19" r="2"/><path d="M8 5h8a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h8"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
    bowl: '<path d="M3 10h18a9 9 0 0 1-18 0ZM8 21h8M8 3v3m4-4v4m4-3v3"/>',
    cup: '<path d="M5 8h12v9a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4ZM17 9h2a3 3 0 0 1 0 6h-2M8 2v3m5-3v3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>', camera: '<rect x="3" y="6" width="18" height="15" rx="3"/><path d="m8 6 2-3h4l2 3"/><circle cx="12" cy="13" r="4"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    file: '<path d="M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8m-8 4h6"/>', arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  };
  const state = { dashboard: null, dayData: null, query: null, day: '', choices: {}, loading: false, error: '', job: null, busy: false, sequence: 0, timer: null, entered: false, detail: null, photoURL: null };
  let app;
  function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`; }
  function escape(value) { return app.escape(value); }
  function dayBefore(day, count) { const date = new Date(day + 'T12:00:00Z'); date.setUTCDate(date.getUTCDate() - count); return date.toISOString().slice(0, 10); }
  function validDay(day) { return typeof day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(day) && day >= '1900-01-01' && day <= '2100-12-31' && !Number.isNaN(Date.parse(day + 'T12:00:00Z')) && dayBefore(day, 0) === day; }
  function number(value) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }); }
  function requestedDay() { const hash = typeof location !== 'undefined' ? location.hash : ''; const day = new URLSearchParams(hash.split('?')[1] || '').get('date'); return validDay(day) ? day : app.data().today; }
  function repaint() { if (app.route() === 'wearables') app.render(); }
  function safe(callback) { if (!app.canLeave || app.canLeave(callback)) callback(); }
  function action(label, name, extra = '', style = 'secondary') { return `<button type="button" class="button ${style}" data-wearable="${name}" ${extra}>${label}</button>`; }
  function dayMeals(day) { return (state.dashboard?.meals || []).filter(item => item.day === day); }
  function currentMetric() { return (state.dashboard?.catalog || app.data().wearables?.catalog || []).find(item => item.id === state.query?.metric) || { id: 'steps', name: '步数', unit: '步' }; }

  function chart(days, unit) {
    const values = days.filter(day => day.value !== null).map(day => day.value);
    if (!values.length) return '<div class="daily-chart-empty"><span class="daily-empty-line"></span><p>还没有可显示的数值</p><small>选择来源或导入资料；缺失不会补成 0。</small></div>';
    const maximum = Math.max(...values, 1), step = 680 / days.length;
    return `<div class="daily-chart"><svg viewBox="0 0 720 174" role="img" aria-label="每日${escape(unit)}，缺失不插值；精确日值见展开的记录表"><line class="daily-grid-line" x1="36" y1="15" x2="716" y2="15"/><line class="daily-grid-line" x1="36" y1="148" x2="716" y2="148"/><text x="2" y="19">${number(maximum)}</text><text x="15" y="151">0</text>${days.map((day, index) => { const height = day.value === null ? 2 : day.value / maximum * 133; return `<rect class="daily-bar ${day.value === null ? 'missing' : ''} ${day.day === state.day ? 'is-day' : ''}" x="${36 + index * step + step * 0.18}" y="${148 - height}" width="${step * 0.64}" height="${height}" rx="3"><title>${escape(day.day)}：${number(day.value)} ${escape(unit)}</title></rect>`; }).join('')}</svg><div class="daily-chart-axis"><span>${escape(days[0].day)}</span><span>日值 · 缺失留白</span><span>${escape(days.at(-1).day)}</span></div></div>`;
  }
  function statusView() {
    const job = state.job;
    if (!job || job.state === 'idle') return '';
    const cancel = action(['error', 'cancelled', 'completed'].includes(job.state) ? '关闭本次导入' : '取消本次导入', 'cancel', state.busy ? 'disabled' : '');
    if (job.state !== 'ready') return `<section class="panel wearable-progress" aria-live="polite"><h2>${{ uploading: '正在接收本机文件', parsing: '正在本地解析', error: '此次导入未保存', cancelled: '导入已取消', completed: '已完成本地保存' }[job.state] || '导入状态'}</h2><p>${escape(job.error || (job.result ? `新增 ${job.result.imported} 条；重复 ${job.result.duplicates || 0} 条${job.result.already_imported ? '，该文件与范围已导入' : ''}` : `已检查 ${number(job.progress?.records_seen || 0)} 项，识别 ${number(job.progress?.samples || 0)} 条。解析时可以切页后返回。`))}</p>${cancel}</section>`;
    const report = job.report, first = report.metrics.reduce((value, item) => value < item.first ? value : item.first, '9999-12-31'), last = report.metrics.reduce((value, item) => value > item.last ? value : item.last, '');
    return `<section class="panel wearable-preview"><div class="panel-heading"><div><h2>先选择，再保存</h2><p>${escape(job.filename)} · ${number(report.samples)} 条 · 文件内重复 ${number(report.file_duplicates)} 条</p></div>${app.badge('尚未写入档案', 'amber')}</div><p>请确认这是本人资料。不会覆盖基本档案，不导入姓名、生日、血型、病历或 GPS；不发送给 AI。预览有效 30 分钟。</p><details><summary>跳过项与无效样本</summary><ul>${[...Object.entries(report.unsupported), ...Object.entries(report.invalid)].map(([key, value]) => `<li>${escape(key)}：${number(value)}</li>`).join('') || '<li>未发现跳过项</li>'}</ul></details><form id="wearable-commit-form"><div class="wearable-metric-options">${report.metrics.map(metric => `<label class="check-label"><input name="metrics" type="checkbox" value="${escape(metric.metric)}" checked>${escape(report.catalog.find(item => item.id === metric.metric)?.name || metric.metric)} <small>${number(metric.count)} 条</small></label>`).join('')}</div><div class="wearable-date-fields">${app.inputField('从（结束日）', 'from', first, 'date', 'required')}${app.inputField('至（结束日）', 'to', last, 'date', 'required')}</div><label class="check-label"><input name="confirm" type="checkbox" required>这是我的资料，我确认所选范围保存到本机，桌面数据库未加密</label><p class="form-message" role="alert"></p><div class="form-footer">${cancel}<button class="button primary" type="submit">确认保存选中样本</button></div></form><details><summary>来源清单（${report.sources.length} 个）</summary>${report.sources.map(source => `<p>${escape(source.source_name)} · ${number(source.count)} 条<br><small>${escape(source.device || '未提供设备描述')}</small></p>`).join('')}</details></section>`;
  }
  function calendar(day) {
    const days = Array.from({ length: 7 }, (unused, index) => dayBefore(day, 6 - index)).filter(validDay);
    return `<section class="daily-calendar" aria-label="选择日记日期"><div class="daily-date-control">${action('‹', 'date-previous', 'aria-label="前一天"', 'quiet')}<form id="daily-date-form"><label><span class="sr-only">日记日期</span><input type="date" name="day" value="${escape(day)}" min="1900-01-01" max="${escape(app.data().today)}" required></label><button class="button quiet small" type="submit">查看</button></form>${action('›', 'date-next', `aria-label="后一天" ${day >= app.data().today ? 'disabled' : ''}`, 'quiet')}${action('今天', 'today', '', 'secondary small')}</div><div class="daily-week" role="group" aria-label="最近七日">${days.map(date => `<button type="button" data-wearable="day" data-day="${date}" aria-pressed="${date === day}" aria-label="${date}${dayMeals(date).length ? '，有饮食记录' : ''}" class="${date === day ? 'selected' : ''}"><span>${new Date(date + 'T12:00:00Z').toLocaleDateString('zh-CN', { weekday: 'short', timeZone: 'UTC' })}</span><strong>${date.slice(8)}</strong><i class="${dayMeals(date).length ? 'has-entry' : ''}" aria-hidden="true"></i></button>`).join('')}</div></section>`;
  }
  function mealCard(kind, entries, day) {
    return `<article class="daily-meal-card ${kind}"><div class="daily-meal-heading"><span class="daily-meal-icon">${icon(symbols[kind])}</span><div><h3>${meals[kind]}</h3><small>${entries.length ? `${entries.length} 条实际记录` : '还未记录，不代表没吃'}</small></div>${action(icon('plus'), 'food-new', `data-meal="${kind}" aria-label="记录${meals[kind]}"`, 'quiet')}</div>${entries.map(item => `<div class="daily-food-entry"><div><span class="daily-entry-time">${escape(item.time || '时间未填')}</span><p class="preserve-lines">${escape(item.note)}</p><small>${escape(item.source || '本人实际饮食')}${item.document_id ? ' · 已关联原件' : ''}</small></div><div class="daily-entry-actions">${item.document_id ? action(icon('camera'), 'food-photo', `data-id="${escape(item.document_id)}" aria-label="查看关联原件"`, 'quiet small') : ''}${item.origin === 'journal' ? action('编辑', 'food-edit', `data-id="${escape(item.id)}"`, 'quiet small') : item.origin === 'analysis' ? `<a class="text-link" href="#assistant?task=breakfast&analysis=${escape(item.id)}">原记录</a>` : action('原记录', 'legacy-plan', `data-day="${day}"`, 'quiet small')}</div></div>`).join('') || `<button type="button" class="daily-meal-empty" data-wearable="food-new" data-meal="${kind}">${icon('plus')}<span>记下吃了什么<small>文字即可，照片可选</small></span></button>`}</article>`;
  }
  function metricsView(day) {
    const metrics = state.dayData?.day === day ? state.dayData.metrics : {}, steps = metrics.steps || {};
    return `<aside class="daily-body-column"><section class="daily-activity-card"><div class="daily-section-line"><span>${icon('walk')} 当日步行</span>${app.badge('Apple 健康导入', 'sage')}</div><div class="daily-step-number">${number(steps.value)}<span>步</span></div><p>${state.loading ? '读取本机记录中…' : escape(steps.conflict ? '有多个来源，请先选择，不直接相加。' : steps.warning || (steps.count ? '来自已导入样本，不等于全天覆盖。' : '这天还没有可用步数，空白不是 0。'))}</p>${steps.sources?.length ? `<label class="daily-source-label">步数来源<select id="daily-steps-source" aria-label="当日步数来源"><option value="">单来源时统计；多来源待选择</option>${steps.sources.map(source => `<option value="${source.source}" ${state.choices.steps === source.source ? 'selected' : ''}>${escape(source.source_name + (source.device ? ' · ' + source.device.slice(0, 50) : ''))}</option>`).join('')}</select></label>` : action('导入健康记录', 'select', '', 'secondary wide')}<div class="daily-activity-foot"><span>${steps.count || 0} 条样本</span>${action('查看依据', 'details', `data-day="${day}" data-metric="steps" ${steps.count ? '' : 'disabled'}`, 'quiet small')}</div></section><div class="daily-vitals">${['sleep', 'heart_rate', 'distance'].map(key => { const metric = metrics[key] || {}; return `<button type="button" class="daily-vital" data-wearable="metric-details" data-metric="${key}"><span class="daily-vital-icon ${key}">${icon(symbols[key])}</span><span><span class="daily-vital-name">${{ sleep: '睡眠区间', heart_rate: '心率采样均值', distance: '步行 / 跑步距离' }[key]}</span><strong>${number(metric.value)} <small>${escape({ sleep: '小时', heart_rate: '次/分', distance: 'km' }[key])}</small></strong><small class="daily-vital-note">${metric.conflict ? '多来源待核对' : metric.count ? `${metric.count} 条样本 · 查看口径` : '未记录'}</small></span><span aria-hidden="true">›</span></button>`; }).join('')}</div><section class="daily-local-card">${icon('lock')}<h3>留在自己的电脑里</h3><p>文字存入本地 SQLite，照片存入附件目录。不是浏览器缓存，也不会自动发给模型。</p><p class="daily-security">本地不等于加密；请启用磁盘加密并另存备份。</p><a href="#settings" class="text-link">查看位置与备份 ${icon('arrow')}</a></section></aside>`;
  }
  function reviewView() {
    const metadata = state.dashboard?.catalog || app.data().wearables?.catalog || [], query = state.query || { metric: 'steps', from: dayBefore(state.day || app.data().today, 6), to: state.day || app.data().today, source: '' };
    const metric = currentMetric(), days = state.dashboard?.daily || [], available = days.filter(day => day.value !== null);
    return `<section class="panel daily-trends"><div class="panel-heading"><div><span class="daily-section-kicker">慢慢看变化</span><h2>走过的路，吃过的饭</h2><p>当前 ${escape(metric.name)} · ${available.length}/${days.length || 7} 天有可用数值。只记录，不评分。</p></div>${action('导出回顾', 'export', state.dashboard ? '' : 'disabled', 'secondary small')}</div><form id="wearable-filter-form" class="daily-trend-filters">${app.selectField('指标', 'metric', query.metric, metadata.map(item => [item.id, item.name]))}${app.inputField('开始', 'from', query.from, 'date', 'required')}${app.inputField('结束', 'to', query.to, 'date', 'required')}<button class="button secondary" type="submit">更新</button>${app.selectField('趋势来源', 'source', query.source, [['', '单来源日值；多来源留空'], ...(state.dashboard?.sources || []).map(source => [source.source, source.source_name + (source.device ? ' · ' + source.device.slice(0, 60) : '')])])}<p class="form-message" role="alert"></p></form>${chart(days, metric.unit)}<details class="daily-disclosure"><summary>查看逐日数值与实际饮食</summary><div class="table-scroll"><table><thead><tr><th>日期</th><th>${escape(metric.name)}</th><th>记录口径</th><th>实际饮食</th></tr></thead><tbody>${days.slice().reverse().map(day => `<tr><td>${action(escape(day.day), 'day', `data-day="${day.day}"`, 'quiet small')}</td><td>${number(day.value)} ${escape(metric.unit)}</td><td>${escape(day.warning || `${day.count} 条样本`)}</td><td>${dayMeals(day.day).map(item => `<p>${escape(meals[item.meal] || item.meal)} · ${escape(item.note)}</p>`).join('') || '未记录'}</td></tr>`).join('')}</tbody></table></div></details><p class="daily-footnote">${escape(state.dashboard?.notice || '消费级记录不是诊断。不同来源不直接相加；缺失不按零计算。')}${metric.id === 'sleep' ? '睡眠按样本结束日取并集，不等于按夜统计。' : ''}</p></section>`;
  }
  function managementView() {
    const batches = state.dashboard?.batches || [];
    return `<details class="daily-disclosure daily-management"><summary>${icon('file')} 健康导入与数据管理 <span>${batches.length} 个批次</span></summary><div class="daily-management-body"><p>Apple Watch → iPhone「健康」→ 导出 ZIP/XML → 本机确认。不是实时连接，不索取 Apple ID；保存前可选择指标与日期。</p><div class="daily-inline-actions">${action('导入 Apple 健康', 'select')}${action('查看导入说明', 'help', '', 'quiet')}<a class="text-link" href="#settings">完整本地备份</a></div>${batches.map(batch => `<div class="wearable-batch"><div><strong>${escape(batch.filename)}</strong><small>${escape(batch.created_at)} · ${number(batch.samples)} 条</small></div>${action('移除此批次', 'delete', `data-id="${escape(batch.id)}"`, 'quiet')}</div>`).join('') || '<p class="muted">尚无导入批次。</p>'}<p class="daily-footnote">删除批次不改 Apple 健康或饮食；其他批次引用的样本保留。完整 ZIP 包含日记及设备记录，原件互传不包含结构化记录。</p></div></details>`;
  }
  function view() {
    const day = state.day || requestedDay(), entries = dayMeals(day), latest = app.data().wearables?.latest || '';
    return `<div class="daily-workspace"><header class="daily-page-heading"><div><span class="daily-section-kicker">活动与饮食，在同一天相遇</span><h1>日常手记</h1><p>走了多少，吃了什么，都从真实记录开始。</p></div><div class="daily-inline-actions">${action(icon('plus') + '记一餐', 'food-new', '', 'primary')}${action(icon('file') + '导入健康', 'select')}</div></header>${calendar(day)}<div class="daily-state-line"><span>${icon('lock')} 本机保存 · 不发送给 AI</span><span>${latest ? `健康记录到 ${escape(latest)}` : 'Apple 健康尚未导入'}${latest && latest !== day ? action('查看最近记录日', 'day', `data-day="${latest}"`, 'quiet small') : ''}</span></div>${state.error ? `<div class="alert warning" role="alert">${escape(state.error)} ${action('重新读取', 'reload', '', 'secondary small')}</div>` : ''}${statusView()}<div class="daily-layout"><section class="daily-meals-column"><div class="daily-section-title"><div><h2>好好吃饭</h2><p>${escape(day)} · ${entries.length} 条人工记录</p></div><a class="text-link" href="#meals">需要餐单灵感？ ${icon('arrow')}</a></div><div class="daily-meal-grid">${Object.keys(meals).map(kind => mealCard(kind, entries.filter(item => item.meal === kind), day)).join('')}</div><div class="daily-kind-note"><span>${icon('bowl')}</span><p>记一餐不需要先生成餐单，也不需要 AI。<br><small>照片是依据，文字由你填写；不估算热量，不用步数决定吃多少。</small></p></div></section>${metricsView(day)}</div>${reviewView()}${managementView()}<footer class="daily-footer-note">实际饮食是人工记录的个人自述，设备记录不是诊断。同日变化不等于因果；有不适请及时就医。</footer></div>`;
  }

  async function load(query) {
    const day = state.day || requestedDay(), next = query || state.query || { metric: 'steps', from: dayBefore(day, 6) < '1900-01-01' ? '1900-01-01' : dayBefore(day, 6), to: day, source: state.choices.steps || '' }, sequence = ++state.sequence;
    state.day = day; state.query = { ...next }; state.dashboard = null; state.dayData = null; state.loading = true; state.error = '';
    const dayQuery = { date: day, ...Object.fromEntries(Object.entries(state.choices).map(([key, value]) => [key + '_source', value])) };
    try {
      const [dashboard, dayData] = await Promise.all([app.request('/api/wearables?' + new URLSearchParams(next)), app.request('/api/day?' + new URLSearchParams(dayQuery))]);
      if (sequence === state.sequence) { state.dashboard = dashboard; state.dayData = dayData; }
      if (sequence === state.sequence && !(next.from <= day && day <= next.to)) {
        const single = await app.request('/api/wearables?' + new URLSearchParams({ from: day, to: day, metric: 'steps', source: '' }));
        if (sequence === state.sequence) state.dashboard.meals = [...state.dashboard.meals, ...single.meals];
      }
    } catch (error) { if (sequence === state.sequence) { state.error = error.message; state.dashboard = null; state.dayData = null; } }
    finally { if (sequence === state.sequence) { state.loading = false; repaint(); } }
  }
  async function poll() {
    clearTimeout(state.timer); state.timer = null;
    if (app.route() !== 'wearables') return;
    try { state.job = await app.request('/api/wearables/import'); repaint(); }
    catch (error) { state.error = error.message; repaint(); return; }
    if (['uploading', 'parsing'].includes(state.job.state) && app.route() === 'wearables') state.timer = setTimeout(poll, 1200);
  }
  function enter() {
    const day = requestedDay();
    if (state.entered && state.day === day) return;
    if (state.day !== day) state.query = null;
    state.entered = true; state.day = day; load();
    if (!state.busy && !state.timer) state.timer = setTimeout(poll, 100);
  }
  function chooseDay(day) { if (validDay(day)) safe(() => { state.query = null; if (app.navigate) app.navigate('wearables?date=' + day); else { state.day = day; load(); } }); }
  async function details(day, metric = state.query?.metric || 'steps', offset = 0, source = '') {
    const captured = state.sequence, result = await app.request('/api/wearables/details?' + new URLSearchParams({ day, metric, source, offset: String(offset) }));
    if (app.route() !== 'wearables' || captured !== state.sequence) return;
    state.detail = { day, metric, offset, source };
    app.openModal('原始样本 · 非临床核验', `<div class="modal-body"><p>${escape(day)} · 共 ${result.total} 条，本页 ${result.items.length} 条。</p>${result.items.map(item => `<section class="wearable-detail"><strong>${number(item.value)} ${escape(item.unit)} ${escape(item.category)}</strong><p>导出原值：${escape(item.original_value)} ${escape(item.original_unit)}</p><p>${escape(item.source_name)}${item.manual ? ' · 手工录入' : ''}</p><small>${escape(item.start)}<br>${escape(item.end)}<br>${escape(item.device)} · ${escape(item.source_version)}</small></section>`).join('')}<div class="form-footer">${action('上一页', 'previous', offset ? '' : 'disabled')}${action('下一页', 'next', offset + 50 >= result.total ? 'disabled' : '')}</div></div>`, 'record-modal');
  }
  function metricDetails(key) {
    const metric = state.dayData?.metrics[key]; if (!metric) return;
    app.openModal(escape(metric.name) + ' · 记录口径', `<div class="modal-body"><p>${escape(metric.warning || '这一天尚未记录，不代表正常或为零。')}</p><p>每个指标独立选择来源；选择仅用于本次页面查看，不改变原始数据或 Apple 健康优先级。</p><form id="daily-source-form" data-metric="${key}">${app.selectField('来源', 'source', state.choices[key] || '', [['', '单来源时统计；多来源留空'], ...metric.sources.map(source => [source.source, source.source_name + ' · ' + (source.device || '未标识设备')])])}<p class="form-message" role="alert"></p><button type="submit" class="button primary">应用来源</button></form>${action('查看原始样本', 'details', `data-day="${state.day}" data-metric="${key}" ${metric.count ? '' : 'disabled'}`)}</div>`);
  }
  function foodForm(kind = 'breakfast', existing = null) {
    safe(() => {
      const item = existing || { id: crypto.randomUUID(), date: state.day || requestedDay(), time: '', meal: Object.hasOwn(meals, kind) ? kind : 'breakfast', note: '', document_id: null };
      app.openModal(existing ? '编辑这一餐' : '记下这一餐', `<form id="daily-food-form" data-id="${item.id}" data-version="${existing?.version || ''}"><div class="modal-body"><p class="daily-form-intro">记实际吃过的，不必精确称重。只保存在本机，不会自动调用模型。</p><div class="form-grid">${app.inputField('用餐日期', 'date', item.date, 'date', `required max="${app.data().today}"`)}${app.inputField('时间（可选）', 'time', item.time, 'time')}${app.selectField('餐次', 'meal', item.meal, Object.entries(meals))}<label class="field full-span"><span>吃了什么、份量与配料</span><textarea name="note" rows="4" maxlength="2000" placeholder="例如：一碗粥、一个鸡蛋。按自己知道的写，不确定的可以注明。" required>${escape(item.note)}</textarea></label>${app.selectField('关联已有原件（可选）', 'document_id', item.document_id || '', [['', '不附原件'], ...(app.data().documents || []).map(doc => [doc.id, doc.filename])])}</div><div class="daily-inline-actions">${action(icon('camera') + '拍一张', 'meal-camera')}${action('相册 / 文件', 'meal-album', '', 'quiet')}</div><input id="daily-meal-camera" type="file" accept="image/jpeg,image/png" capture="environment" hidden><input id="daily-meal-album" type="file" accept=".jpg,.jpeg,.png" hidden><p class="daily-footnote">JPG/PNG，最多 20 MiB。照片先留存为本机原件，取消日记也会保留；不自动识别、不去除 EXIF。HEIC 请先导出为 JPG。</p><p id="daily-photo-status" role="status"></p><p class="form-message" role="alert"></p></div><div class="modal-footer split">${existing ? action('删除这条日记', 'food-delete', `data-id="${item.id}" data-version="${item.version}"`, 'quiet danger-text') : '<span class="daily-save-caption">'+icon('lock')+'本机保存</span>'}<div><button type="button" data-action="close-modal" class="button secondary">取消</button><button type="submit" class="button primary">保存这一餐</button></div></div></form>`, 'record-modal');
    });
  }
  async function photoUpload(input) {
    const file = input.files[0], form = input.closest('form'); input.value = '';
    if (!file || !form || state.busy || form.dataset.saving) return;
    if (!/\.(jpg|jpeg|png)$/i.test(file.name) || !file.size || file.size > 20 * 1024 * 1024) { form.querySelector('.form-message').textContent = '请选择 JPG/PNG，最多 20 MiB；HEIC 不能改扩展名代替转换。'; return; }
    const controls = [...form.querySelectorAll('input,textarea,select,button')].filter(control => !control.disabled);
    form.dataset.saving = 'true'; state.busy = true; controls.forEach(control => { control.disabled = true; });
    try {
      const doc = await app.request('/api/documents', { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' }, body: file });
      if (!form.isConnected) return;
      const select = form.querySelector('[name="document_id"]');
      if (![...select.options].some(option => option.value === doc.id)) { const option = document.createElement('option'); option.value = doc.id; option.textContent = doc.filename; select.append(option); }
      select.value = doc.id; form.dataset.dirty = 'true'; form.querySelector('#daily-photo-status').textContent = '照片原件已保存到本机；请再保存这一餐。'; await app.refresh(false);
    } catch (error) { if (form.isConnected) form.querySelector('.form-message').textContent = error.message; }
    finally { delete form.dataset.saving; controls.forEach(control => { control.disabled = false; }); state.busy = false; }
  }
  async function photoView(id) {
    const sequence = state.sequence, doc = (app.data().documents || []).find(item => item.id === id);
    if (!doc) throw new Error('原件信息已变化，请刷新');
    if (!doc.mime.startsWith('image/')) { app.navigate('documents'); return; }
    const blob = await app.request('/api/documents/' + id, { binary: true });
    if (sequence !== state.sequence || app.route() !== 'wearables' || app.modalOpen?.()) return;
    if (state.photoURL) URL.revokeObjectURL(state.photoURL);
    state.photoURL = URL.createObjectURL(blob);
    app.openModal('这一餐的原件', `<div class="modal-body"><img class="daily-photo" src="${state.photoURL}" alt="${escape(doc.filename)}"><p>${escape(doc.filename)} · 本机原件，未经图像识别或医学核验。</p></div>`);
  }
  function exportReview() {
    if (!state.dashboard) return;
    const snapshot = JSON.parse(JSON.stringify(state.dashboard)), metric = snapshot.catalog.find(item => item.id === snapshot.metric);
    app.confirmation('导出未加密的日常回顾？', '包含所示日期的设备日值、来源说明和实际饮食文字。不会导出照片字节；TXT 不是完整备份，请只给可信接收者。', () => {
      const content = ['知己 · 日常手记（静态回顾，非诊断）', `${snapshot.from} 至 ${snapshot.to}；${metric.name} / ${metric.unit}`, `来源：${snapshot.source ? snapshot.sources.find(item => item.source === snapshot.source)?.source_name || snapshot.source : '单来源日值；多来源冲突留空'}`, snapshot.notice, ...snapshot.daily.flatMap(day => [`${day.day}：${number(day.value)} ${metric.unit}；${day.warning}`, ...snapshot.meals.filter(meal => meal.day === day.day).map(meal => `${meals[meal.meal] || meal.meal} ${meal.time || ''}：${meal.note}（${meal.source}）`)])].join('\n');
      const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }));
      app.openModal('回顾已准备好', `<div class="modal-body"><p>未加密，可作为 TXT 导入手机资料版加密保存，不是完整样本同步。</p><a class="button primary" href="${url}" download="日常手记回顾.txt">保存回顾 TXT</a></div>`); setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }
  function help() { app.openModal('Apple 健康 · 本地导入', '<div class="modal-body"><ol><li>iPhone 健康 → 头像 → 导出所有健康数据。</li><li>通过自己控制的方式把 ZIP 传到运行本应用的电脑。</li><li>选择 ZIP 或 HealthData 主 XML，预览并选择指标/日期后保存。</li></ol><p>不是实时连接，不索取 Apple ID，不读取 iCloud。256 MiB 上传、1 GiB 展开、100 万样本上限。原始 ZIP/XML 不永久保存，请自己保留。</p><p>不支持 GPS、临床病历或 ECG 波形。记录按结束日原时区归属；来源冲突和重叠不臆造总数。</p><p>照片与日记在电脑文件系统，不在浏览器缓存；桌面未加密，请启用磁盘加密并另存备份。手机独立资料版的数据在手机浏览器，不会自动同步这里。</p></div>'); }
  function configure(adapter) {
    app = adapter;
    document.addEventListener('click', async event => {
      const target = event.target.closest('[data-wearable]'); if (!target || target.disabled || state.busy) return;
      try {
        const name = target.dataset.wearable;
        if (name === 'select') safe(() => document.querySelector('#apple-health-upload').click());
        if (name === 'help') help();
        if (name === 'reload') { await app.refresh(false); await load(); }
        if (name === 'day') chooseDay(target.dataset.day);
        if (name === 'today') chooseDay(app.data().today);
        if (name === 'date-previous') chooseDay(dayBefore(state.day, 1));
        if (name === 'date-next' && state.day < app.data().today) chooseDay(dayBefore(state.day, -1));
        if (name === 'food-new') foodForm(target.dataset.meal);
        if (name === 'food-edit') { const item = dayMeals(state.day).find(item => item.origin === 'journal' && item.id === target.dataset.id); if (item) foodForm(item.meal, item); }
        if (name === 'food-delete') safe(() => app.confirmation('删除这条实际饮食？', '只删除所选日记，照片原件保留，不改步数或其它用餐记录。已修改的记录会拒绝旧版本删除。', async () => { await app.request('/api/food', { method: 'DELETE', json: { id: target.dataset.id, version: Number(target.dataset.version), confirm: true } }); await load(); app.toast('日记已删除，关联原件保留'); }, '删除日记'));
        if (name === 'food-photo') await photoView(target.dataset.id);
        if (name === 'meal-camera') document.querySelector('#daily-meal-camera').click();
        if (name === 'meal-album') document.querySelector('#daily-meal-album').click();
        if (name === 'legacy-plan') app.openPlan?.(target.dataset.day);
        if (name === 'metric-details') metricDetails(target.dataset.metric);
        if (name === 'details') await details(target.dataset.day, target.dataset.metric, 0, state.choices[target.dataset.metric] || '');
        if (name === 'previous') await details(state.detail.day, state.detail.metric, Math.max(0, state.detail.offset - 50), state.detail.source);
        if (name === 'next') await details(state.detail.day, state.detail.metric, state.detail.offset + 50, state.detail.source);
        if (name === 'cancel') { state.busy = true; await app.request('/api/wearables/import', { method: 'DELETE', json: { id: state.job.id } }); state.job = null; await poll(); }
        if (name === 'delete') app.confirmation('移除此健康导入批次？', '仅影响本地设备样本，其他批次引用的样本保留；饮食记录不变。请先备份。', async () => { await app.request('/api/wearables/batches', { method: 'DELETE', json: { id: target.dataset.id, confirm: true } }); await app.refresh(false); await load(); }, '确认移除');
        if (name === 'export') exportReview();
      } catch (error) { state.error = error.message; app.toast(error.message, true); }
      finally { state.busy = false; repaint(); }
    });
    document.addEventListener('change', async event => {
      const input = event.target;
      if (['daily-meal-camera', 'daily-meal-album'].includes(input.id)) { await photoUpload(input); return; }
      if (input.id === 'daily-steps-source') { const value = input.value; safe(() => { state.choices.steps = value; if (state.query?.metric === 'steps') state.query.source = value; load(); }); return; }
      if (input.id !== 'apple-health-upload') return;
      const file = input.files[0]; input.value = ''; if (!file || state.busy) return;
      state.busy = true; state.error = '';
      try {
        if (!/\.(zip|xml)$/i.test(file.name) || !file.size || file.size > 256 * 1024 * 1024) throw new Error('请选择非空 ZIP/XML，最多 256 MiB');
        state.job = { state: 'uploading', progress: {} }; repaint();
        state.job = await app.request('/api/wearables/import', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name) }, body: file }); await poll();
      } catch (error) { state.error = error.message; state.job = null; }
      finally { state.busy = false; repaint(); }
    });
    document.addEventListener('submit', async event => {
      const form = event.target;
      if (!['wearable-filter-form', 'wearable-commit-form', 'daily-date-form', 'daily-source-form', 'daily-food-form'].includes(form.id)) return;
      event.preventDefault(); if (state.busy || form.dataset.saving) return;
      const data = new FormData(form);
      if (form.id === 'daily-date-form') { delete form.dataset.dirty; chooseDay(data.get('day')); return; }
      const controls = [...form.querySelectorAll('input,textarea,select,button')].filter(control => !control.disabled);
      form.dataset.saving = 'true'; state.busy = true; controls.forEach(control => { control.disabled = true; });
      let committed = false;
      try {
        if (form.id === 'daily-food-form') {
          const saved = await app.request('/api/food', { method: form.dataset.version ? 'PUT' : 'POST', json: { id: form.dataset.id, version: Number(form.dataset.version), date: data.get('date'), time: data.get('time'), meal: data.get('meal'), note: data.get('note'), document_id: data.get('document_id') } });
          committed = true; delete form.dataset.dirty; app.closeSavedModal?.(); app.toast('这一餐已保存到本机，未发送给模型'); state.query = null; state.day = saved.date; app.replaceDay?.(saved.date); await app.refresh(false); await load();
        } else if (form.id === 'daily-source-form') { state.choices[form.dataset.metric] = String(data.get('source') || ''); delete form.dataset.dirty; app.closeSavedModal?.(); await load(); }
        else if (form.id === 'wearable-filter-form') { const query = Object.fromEntries(data); if (query.metric !== state.query?.metric) query.source = ''; await load(query); }
        else { await app.request('/api/wearables/commit', { method: 'POST', json: { id: state.job.id, metrics: data.getAll('metrics'), from: data.get('from'), to: data.get('to'), confirm: data.has('confirm') } }); await app.refresh(false); await poll(); await load(); app.toast('健康样本已保存；今天没有数据时可查看最近记录日'); }
        delete form.dataset.dirty;
      } catch (error) { if (committed) { state.error = '这一餐已保存，但页面刷新失败，请刷新查看，不必重复新增。'; app.toast(state.error, true); } else { const message = form.querySelector('.form-message'); if (message) message.textContent = error.message; else app.toast(error.message, true); } }
      finally { delete form.dataset.saving; controls.forEach(control => { control.disabled = false; }); state.busy = false; repaint(); }
    });
    window.addEventListener('hashchange', () => { if (app.route() !== 'wearables') { clearTimeout(state.timer); state.timer = null; state.entered = false; state.sequence++; state.loading = false; } });
    window.addEventListener('beforeunload', event => { if (state.busy) { event.preventDefault(); event.returnValue = ''; } });
    document.querySelector('#modal')?.addEventListener?.('close', () => { if (state.photoURL) URL.revokeObjectURL(state.photoURL); state.photoURL = null; });
  }
  scope.WearableUI = { configure, view, enter, dayBefore, validDay, number, chart, state, load, foodForm, chooseDay };
})(globalThis);
