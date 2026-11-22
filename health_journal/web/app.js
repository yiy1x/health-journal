const root = document.querySelector('#app');
const modal = document.querySelector('#modal');
const leaveModal = document.querySelector('#leave-modal');
const token = document.querySelector('meta[name="journal-token"]').content;
const state = { data: null, route: 'home', query: '', kind: '', department: '', topic: '', care: 'medication', series: 0, mealDate: '', assistant: null, thinking: false, useModel: false, models: [], confirmation: null, aiTask: 'breakfast', aiText: '', aiDocument: '', aiProfile: false, aiRecords: false, aiBusy: false, aiError: '', analysisId: '', specialty: '', specialtyQuery: '', specialtyGroup: '', specialtiesWithData: false };
state.aiEngine = 'api';
const names = { visit: '就诊', observation: '检验指标', medication: '用药', symptom: '症状', condition: '健康问题', reminder: '随访提醒' };
const routes = [
  ['home', '健康总览', 'home'], ['departments', '全科室档案', 'heart'], ['timeline', '诊疗时间线', 'timeline'], ['documents', '原始资料', 'folder'], ['trends', '指标趋势', 'chart'], ['care', '用药与症状', 'heart'], ['meals', '饮食计划', 'bowl'], ['assistant', '档案助理', 'spark'], ['summary', '就医摘要', 'file'], ['models', '模型连接', 'spark'], ['settings', '设置与备份', 'settings'],
];
const paths = {
  home: '<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',
  timeline: '<path d="M6 4v16M11 5h9M11 12h7M11 19h9"/><circle cx="6" cy="5" r="1.5"/><circle cx="6" cy="12" r="1.5"/><circle cx="6" cy="19" r="1.5"/>',
  folder: '<path d="M3 6h7l2 3h9v11H3z"/><path d="M3 6V4h7l2 2h8v3"/>',
  chart: '<path d="M4 3v17h17M7 14l4-5 4 3 5-7"/>',
  heart: '<path d="M20.5 5.5a5 5 0 0 0-7 0L12 7l-1.5-1.5a5 5 0 0 0-7 7L12 21l8.5-8.5a5 5 0 0 0 0-7Z"/><path d="M3 11h5l2 4 3-7 2 3h6"/>',
  bowl: '<path d="M3 11h18a9 9 0 0 1-18 0ZM8 21h8M8 3v4M12 2v5M16 3v4"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/>',
  file: '<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h6"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v5m10-5v5M3 11h18M7 15h3"/>',
  warning: '<path d="m12 3 10 18H2zM12 9v5M12 17v1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
  pill: '<path d="m8 4-4 4a6 6 0 0 0 8 8l4-4a6 6 0 0 0-8-8ZM7 7l9 9"/>',
  print: '<path d="M7 8V3h10v5M7 17H3V8h18v9h-4M7 14h10v7H7zM17 11h1"/>',
  refresh: '<path d="M20 8A8 8 0 1 0 21 15M20 3v5h-5"/>',
  camera: '<rect x="3" y="7" width="18" height="14" rx="3"/><path d="m7 7 2-4h6l2 4"/><circle cx="12" cy="14" r="4"/>',
};
function icon(name, className = '') { return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`; }
function escape(value) { return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]); }
function fmtDate(value, short = false) { return value ? (short ? value.slice(5).replace('-', '/') : value.replaceAll('-', '.')) : '未记录'; }
function numeric(value) { return String(value); }
function localDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '未记录' : date.toLocaleDateString('zh-CN'); }
function records(kind) { return state.data.records.filter(record => !kind || record.kind === kind); }
function getRecord(id) { return state.data.records.find(record => record.id === id); }
function badge(label, tone = '') { return `<span class="badge ${tone}">${escape(label)}</span>`; }
function pending(record) { return badge(record.verification === 'verified' ? '已核对' : '待核对', record.verification === 'verified' ? 'sage' : 'amber'); }
function button(label, action, extra = '', type = 'secondary', iconName = '') { return `<button type="button" class="button ${type}" data-action="${action}" ${extra}>${iconName ? icon(iconName) : ''}${label}</button>`; }
function sourceLine(record) { const doc = state.data.documents.find(item => item.id === record.document_id); return doc ? `${icon('file')} ${escape(doc.filename)}` : `${icon('file')} ${escape(record.source_label || '手工录入，未附原件')}`; }
function empty(title, description, action = '') { return `<div class="empty-state">${icon('folder')}<h3>${escape(title)}</h3><p>${escape(description)}</p>${action}</div>`; }
function alertBox(message, tone = 'notice') { return `<div class="alert ${tone}">${icon(tone === 'danger' ? 'warning' : 'lock')}<div>${escape(message)}</div></div>`; }
async function request(path, options = {}) {
  const headers = { 'X-Journal-Token': token, ...options.headers };
  if (options.json !== undefined) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.json); delete options.json; }
  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.error || `请求未完成（${response.status}）`); }
  return options.binary ? response.blob() : response.json();
}
let toastTimer;
function toast(message, failure = false) { const element = document.querySelector('#toast'); element.textContent = message; element.className = failure ? 'visible error' : 'visible'; clearTimeout(toastTimer); toastTimer = setTimeout(() => { element.className = ''; }, 5500); }
let refreshSequence = 0;
async function refresh(renderPage = true) { const sequence = ++refreshSequence; const data = await request('/api/state'); if (sequence !== refreshSequence) return; state.data = data; if (!state.mealDate) state.mealDate = state.data.today; if (renderPage) render(); }
function dirtyForms() { return [...document.querySelectorAll('#app form[data-dirty="true"], dialog[open] form[data-dirty="true"]')]; }
function confirmDiscard(forms, callback) {
  if (leaveModal.open) return;
  document.querySelector('#leave-message').textContent = '这些输入尚未写入本地档案。放弃后无法找回，已保存的资料不受影响。';
  state.leaveCallback = () => { for (const form of forms) delete form.dataset.dirty; callback(); };
  leaveModal.showModal();
}
function canLeave(callback = () => {}) {
  if (state.importBusy) { toast('正在导入原件，请稍候'); return false; }
  if (document.querySelector('#app form[data-saving="true"], dialog[open] form[data-saving="true"]')) { toast('正在保存或准备请求，请稍后再切换页面'); return false; }
  const forms = dirtyForms();
  if (forms.length) { confirmDiscard(forms, callback); return false; }
  return true;
}
function routeState(hash, data) {
  const [requested, query = ''] = hash.replace(/^#/, '').split('?');
  const route = routes.some(item => item[0] === requested) ? requested : 'home';
  const params = new URLSearchParams(query);
  const task = ['breakfast', 'document', 'chat', 'local'].includes(params.get('task')) ? params.get('task') : 'breakfast';
  const analysis = (data.analyses || []).find(item => item.id === params.get('analysis'));
  const index = params.get('department');
  const department = /^\d+$/.test(index || '') ? (data.departments || [])[Number(index)]?.name || '' : (data.records || []).find(item => item.id === params.get('custom'))?.department || '';
  const care = ['medication', 'symptom', 'condition'].includes(params.get('tab')) ? params.get('tab') : 'medication';
  return { route, task: analysis?.task || task, analysisId: analysis?.id || '', department, care };
}
function navigate(hash) {
  if (!canLeave(() => navigate(hash))) return;
  const destination = hash.startsWith('#') ? hash : '#' + hash;
  if (location.hash === destination) { if (modal.open) modal.close(); render(); return; }
  location.hash = destination;
}
function selectTask(task) {
  if (state.aiTask !== task) {
    state.taskDrafts ||= {};
    state.taskDrafts[state.aiTask] = { aiText: state.aiText, aiDocument: state.aiDocument };
    Object.assign(state, state.taskDrafts[task] || { aiText: '', aiDocument: '' });
    state.aiProfile = false; state.aiRecords = false; state.aiError = '';
  }
  state.aiTask = task;
}
function selectEngine(engine, go = false) {
  if (!['api', 'codex'].includes(engine) || state.aiBusy || !canLeave(() => selectEngine(engine, go))) return;
  if (modal.open && !closeModal()) return;
  state.aiEngine = engine; state.aiProfile = false; state.aiRecords = false; state.aiError = '';
  if (go) navigate('assistant?task=breakfast'); else render();
}
async function cancelCodex() {
  const approval = state.aiActiveEngine === 'codex' && state.aiApproval || state.data.codex?.operation;
  if (!approval || state.codexCancelBusy) return;
  state.codexCancelBusy = true;
  try { const result = await request('/api/codex/cancel', { method: 'POST', json: { approval_id: approval } }); toast(result.notice); await refresh(false); render(); }
  catch (error) { toast(error.message, true); }
  finally { state.codexCancelBusy = false; }
}
function currentMedication(record) { const data = record.data; return data.status === 'active' && data.start_date <= state.data.today && (!data.end_date || data.end_date >= state.data.today); }
function flag(record) {
  const data = record.data;
  if (record.verification !== 'verified') return ['待核对', 'amber'];
  if (data.comparator !== '=') return ['非精确值', ''];
  if (data.reference_low !== null && data.value < data.reference_low) return ['低于参考范围', 'amber'];
  if (data.reference_high !== null && data.value > data.reference_high) return ['高于参考范围', 'amber'];
  if (data.reference_low === null && data.reference_high === null) return ['未录参考范围', ''];
  return ['在录入界限内', 'sage'];
}
function valueText(record) { return `${record.data.comparator === '=' ? '' : escape(record.data.comparator)}${numeric(record.data.value)} <small>${escape(record.data.unit)}</small>`; }
function observationGroups() {
  const groups = new Map();
  for (const record of records('observation')) { const key = JSON.stringify([record.title, record.data.unit, record.data.lab]); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(record); }
  return [...groups.values()];
}
function chart(group, large = false) {
  const usable = (group || []).filter(item => item.verification === 'verified' && item.data.comparator === '=').sort((first, second) => first.date.localeCompare(second.date));
  if (!group?.length) return empty('还没有检验指标', '上传检查报告或手动录入后，这里会展示可追溯的指标趋势。');
  if (usable.length < 2) return empty('再记录一次，就能看见变化', '同名、同单位、同机构/方法的已核对精确值至少需要两条。');
  const width = 700, height = large ? 300 : 220, left = 53, right = 30, top = 30, bottom = 40;
  const values = usable.map(item => item.data.value);
  const low = values.reduce((minimum, value) => Math.min(minimum, value), Infinity), high = values.reduce((maximum, value) => Math.max(maximum, value), -Infinity), spread = high - low || Math.max(Math.abs(high) * 0.1, 1);
  const minimum = low - spread * 0.35, maximum = high + spread * 0.35;
  if (![minimum, maximum, maximum - minimum].every(Number.isFinite)) return empty('数值量级过大，暂不绘图', '原始录入值仍保留在记录列表中，请先核对单位与数值。');
  const firstTime = Date.parse(usable[0].date), lastTime = Date.parse(usable.at(-1).date);
  const xPosition = (item, index) => left + (lastTime > firstTime ? (Date.parse(item.date) - firstTime) / (lastTime - firstTime) : index / (usable.length - 1)) * (width - left - right);
  const yPosition = value => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  const coordinates = usable.map((item, index) => [xPosition(item, index), yPosition(item.data.value)]);
  const grid = Array.from({ length: 4 }, (value, index) => { const amount = minimum + (maximum - minimum) * (index / 3); const position = yPosition(amount); return `<line x1="${left}" y1="${position}" x2="${width - right}" y2="${position}" class="grid-line"/><text x="${left - 12}" y="${position + 4}" text-anchor="end">${numeric(Number(amount.toPrecision(3)))}</text>`; }).join('');
  const line = coordinates.map((point, index) => `${index ? 'L' : 'M'}${point[0]},${point[1]}`).join(' ');
  const area = `${line} L${coordinates.at(-1)[0]},${height - bottom} L${coordinates[0][0]},${height - bottom}Z`;
  const tickStep = Math.max(1, Math.ceil(usable.length / 6));
  return `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(usable[0].title)}趋势，详细数值见记录列表">${grid}<path d="${area}" class="chart-area"/><path d="${line}" class="chart-line"/>${usable.map((item, index) => `<circle cx="${coordinates[index][0]}" cy="${coordinates[index][1]}" r="4.5" class="chart-point"><title>${escape(item.date)}：${escape(item.data.value)} ${escape(item.data.unit)}</title></circle>${index % tickStep === 0 || index === usable.length - 1 ? `<text x="${coordinates[index][0]}" y="${height - 12}" text-anchor="middle">${fmtDate(item.date, true)}</text>` : ''}`).join('')}</svg>`;
}
function header(title, subtitle, actions = '') { return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`; }
function render() {
  if (!state.data || dirtyForms().length || document.querySelector('#app form[data-saving="true"]')) return;
  const view = routeState(location.hash, state.data);
  state.route = view.route;
  if (view.route === 'assistant') { selectTask(view.task); state.analysisId = view.analysisId; }
  if (view.route === 'departments') state.specialty = view.department;
  if (view.route === 'care') state.care = view.care;
  state.locationHash = location.hash;
  const label = routes.find(item => item[0] === state.route)[1];
  document.title = label + ' · 知己健康手记';
  root.innerHTML = `<aside class="sidebar"><a class="brand" href="#home"><span class="brand-icon">${icon('file')}</span><span><strong>知己</strong><small>健康手记</small></span></a><div class="workspace-label">我的健康空间</div><nav aria-label="主要导航">${routes.map(([id, name, symbol]) => `<a href="#${id}" class="nav-item ${state.route === id ? 'active' : ''}" ${state.route === id ? 'aria-current="page"' : ''}>${icon(symbol)}<span>${name}</span>${id === 'timeline' && records().some(item => item.verification === 'pending' && item.kind !== 'reminder') ? '<span class="nav-dot"></span>' : ''}</a>`).join('')}</nav><div class="sidebar-bottom">${icon('lock')}<div><strong>本地档案 · 云端可选</strong><small>每次外发，先由你确认</small></div></div><div class="sidebar-version">本地版 ${escape(state.data.version)}${state.data.demo ? ' · 合成演示' : ''}</div></aside><div class="workspace"><div class="topbar"><div class="breadcrumb">我的健康空间 <span>/</span> ${label}</div><div class="topbar-right">${state.data.demo ? badge('合成演示档案', 'amber') : ''}<a class="local-indicator" href="#models"><i></i> ${state.data.cloud?.has_key || state.data.codex?.has_key ? '模型已配置 · 按次授权' : '本地模式'}</a><a class="avatar" href="#settings" aria-label="打开个人设置">${escape(state.data.profile.name.slice(0, 1))}</a></div></div><main id="main-content" tabindex="-1">${views[state.route]()}</main><footer class="page-footer"><span>记录事实，保留依据。辅助整理不代替医生。</span><span>${icon('lock')} 档案本地保存，云端分析逐次确认</span></footer></div>`;
  root.innerHTML += `<nav class="mobile-nav" aria-label="手机导航"><a href="#home" ${state.route === 'home' ? 'aria-current="page"' : ''}>${icon('home')}<span>总览</span></a><a href="#documents" ${state.route === 'documents' ? 'aria-current="page"' : ''}>${icon('folder')}<span>资料</span></a>${button(icon('camera') + '<span>导入</span>', 'upload', '', 'mobile-capture')}<a href="#meals" ${state.route === 'meals' ? 'aria-current="page"' : ''}>${icon('bowl')}<span>饮食</span></a>${button(icon('settings') + '<span>更多</span>', 'mobile-more', '', 'mobile-more')}</nav>`;
  const navigation = document.querySelector('.sidebar nav');
  const activeLink = navigation.querySelector('.active');
  if (navigation.scrollWidth > navigation.clientWidth) navigation.scrollLeft = activeLink.offsetLeft - navigation.offsetLeft - (navigation.clientWidth - activeLink.offsetWidth) / 2;
}
function homeView() {
  const groups = observationGroups(), group = groups[0] || [], latest = group[0];
  const reminders = records('reminder').filter(record => !record.data.done).sort((first, second) => first.date.localeCompare(second.date));
  const waiting = records().filter(record => record.verification === 'pending' && record.kind !== 'reminder');
  const recent = records().filter(record => record.kind !== 'observation' && record.kind !== 'reminder').slice(0, 4);
  const date = new Date(state.data.today + 'T12:00:00').toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });
  return `${header(state.data.profile.name ? `你好，${escape(state.data.profile.name)}` : '我的健康档案', `${date}。从一次记录，了解自己的变化。`, button('导入资料', 'upload', '', 'secondary', 'upload') + button('新增记录', 'add', '', 'primary', 'plus'))}
    <section class="overview-banner"><div class="banner-copy"><span class="banner-tag">让健康记录有迹可循</span><h2>每一次变化，<br>都值得被好好记下。</h2><p>把散落的就诊、检查与日常感受放在一起。<br>需要的时候，你总能找到它们的来处。</p><a href="#timeline" class="text-link">查看我的时间线 ${icon('arrow')}</a></div><div class="journal-art" aria-hidden="true"><div class="art-sheet back"></div><div class="art-sheet front"><div class="art-sheet-title"><span class="art-cross">＋</span><span>我的健康手记<small>每一条记录，都有依据</small></span></div><div class="art-timeline"><i></i><span>记录一次就诊</span><i></i><span>留存一份报告</span><i></i><span>看见长期变化</span></div><div class="art-stamp">${icon('lock')} 本地珍藏</div></div><span class="art-leaf leaf-one"></span><span class="art-leaf leaf-two"></span></div></section>
    <section class="stat-strip" aria-label="档案概况">${[[records('visit').length, '次就诊记录', 'timeline'], [records('observation').length, '条检验指标', 'trends'], [state.data.documents.length, '份原始资料', 'documents'], [waiting.length, '条等待核对', 'timeline']].map(([count, title, route]) => `<a href="#${route}"><strong>${count}<small>${title}</small></strong>${icon(route === 'documents' ? 'folder' : route === 'trends' ? 'chart' : 'file')}</a>`).join('')}</section>
    <div class="dashboard-grid"><section class="panel chart-panel"><div class="panel-heading"><div><h2>关注的指标</h2><p>${latest ? escape(latest.title) : '先从一项检查开始'}</p></div><a href="#trends" class="text-link">全部指标 ${icon('arrow')}</a></div>${latest ? `<div class="chart-metric"><strong>${valueText(latest)}</strong>${badge(...flag(latest))}<span>最近记录 ${fmtDate(latest.date)}</span></div>` : ''}${chart(group)}<div class="panel-footnote">${icon('file')} 只连接同单位、同机构/方法的已核对精确值；不作为诊断依据。</div></section><section class="panel reminder-panel"><div class="panel-heading"><h2>接下来要做</h2>${badge(String(reminders.length), 'sage')}</div>${reminders.length ? `<div class="reminder-list">${reminders.slice(0, 4).map(record => `<div class="reminder-item"><button class="round-check" data-action="complete" data-id="${record.id}" aria-label="完成：${escape(record.title)}">${icon('check')}</button><div><button class="plain-title" data-action="detail" data-id="${record.id}">${escape(record.title)}</button><span class="${record.date < state.data.today ? 'warning-text' : ''}">${fmtDate(record.date)}${record.date < state.data.today ? ' · 已到期' : ''}</span></div></div>`).join('')}</div>` : '<p class="soft-empty">还没有待办，按自己的计划添加随访提醒。</p>'}${button('添加随访', 'add', 'data-kind="reminder"', 'quiet wide', 'plus')}<div class="reminder-note">提醒仅在打开本应用时显示，不会后台推送。</div></section></div>
    <div class="dashboard-grid bottom-grid"><section class="panel"><div class="panel-heading"><h2>最近的记录</h2><a href="#timeline" class="text-link">查看全部 ${icon('arrow')}</a></div>${recent.length ? recent.map(compactRecord).join('') : empty('你的故事，从这里开始', '添加就诊或症状记录，慢慢连起自己的健康时间线。', button('记一笔', 'add', '', 'primary', 'plus'))}</section><section class="panel daily-card"><div class="panel-heading"><h2>今天，认真吃饭</h2>${icon('bowl')}</div><div class="daily-illustration">${foodArt('green')}</div><p>把今天的三餐安排好，<br>也给生活留一点从容。</p><a class="button secondary wide" href="#meals">打开今日餐单 ${icon('arrow')}</a><small>一般膳食灵感，不是治疗性食谱</small></section></div>`;
}
function compactRecord(record) { return `<button class="compact-record" data-action="detail" data-id="${record.id}"><span class="record-symbol ${record.kind}">${icon(record.kind === 'symptom' ? 'heart' : 'file')}</span><span class="compact-copy"><strong>${escape(record.title)}</strong><small>${escape(record.department || names[record.kind])}${record.topic ? ' · ' + escape(record.topic) : ''}</small></span><span class="compact-date">${fmtDate(record.date, true)}${pending(record)}</span></button>`; }
function filterRecords() { const query = state.query.toLocaleLowerCase(); return records().filter(record => (!state.kind || record.kind === state.kind) && (!state.department || record.department === state.department) && (!state.topic || record.topic === state.topic) && (!query || [record.title, record.notes, record.department, record.topic, record.source_label, JSON.stringify(record.data)].join(' ').toLocaleLowerCase().includes(query))); }
function options(values, current, first) { return `<option value="">${first}</option>` + values.map(value => `<option value="${escape(value)}" ${current === value ? 'selected' : ''}>${escape(value)}</option>`).join(''); }
function timelineView() {
  const departments = [...new Set(records().map(record => record.department).filter(Boolean))].sort();
  const topics = [...new Set(records().map(record => record.topic).filter(Boolean))].sort();
  return `${header('诊疗时间线', '科室各有不同，健康记录始终属于同一个你。', button('新增记录', 'add', '', 'primary', 'plus'))}<div class="filter-bar"><label class="search-field">${icon('search')}<input id="record-search" type="search" placeholder="搜索记录、医院、主题或备注" aria-label="搜索记录" value="${escape(state.query)}"></label><select id="kind-filter" aria-label="记录类型"><option value="">全部类型</option>${Object.entries(names).map(([value, label]) => `<option value="${value}" ${value === state.kind ? 'selected' : ''}>${label}</option>`).join('')}</select><select id="department-filter" aria-label="科室筛选">${options(departments, state.department, '全部科室')}</select><select id="topic-filter" aria-label="健康主题筛选">${options(topics, state.topic, '全部健康主题')}</select></div><div id="timeline-results">${timelineResults()}</div>`;
}
function timelineResults() {
  const filtered = filterRecords();
  if (!filtered.length) return `<section class="panel">${empty('这里暂时没有记录', '试试其他筛选条件，或添加一条新的就诊、指标或症状。', button('新增记录', 'add', '', 'primary', 'plus'))}</section>`;
  let lastMonth = '';
  return `<div class="results-meta">${filtered.length} 条记录 <span>“已核对”表示你核对了录入内容，不代表医学验证。</span></div><div class="timeline">${filtered.map(record => { const month = record.date.slice(0, 7); const heading = month !== lastMonth ? `<h2 class="month-heading">${month.replace('-', ' 年 ')} 月</h2>` : ''; lastMonth = month; return `${heading}<article class="timeline-entry"><div class="timeline-date"><strong>${record.date.slice(8)}</strong><span>${record.date.slice(5, 7)} 月</span></div><div class="timeline-card"><div class="record-topline">${badge(names[record.kind])}${record.department ? `<span>${escape(record.department)}</span>` : ''}${pending(record)}</div><button class="plain-title record-title" data-action="detail" data-id="${record.id}">${escape(record.title)}</button><p>${recordSnippet(record)}</p><div class="record-bottom"><span class="source-line">${sourceLine(record)}</span>${record.topic ? badge(record.topic, 'blue') : ''}${button('查看', 'detail', `data-id="${record.id}"`, 'quiet small', 'arrow')}</div></div></article>`; }).join('')}</div>`;
}
function recordSnippet(record) {
  const data = record.data;
  if (record.kind === 'observation') return `${valueText(record)} · ${escape(flag(record)[0])}`;
  if (record.kind === 'medication') return `${escape(data.dose)} · ${escape(data.frequency)} · ${currentMedication(record) ? '按记录日期当前有效' : '非当前有效用药'}`;
  if (record.kind === 'symptom') return `自述程度 ${data.severity}/10 · ${data.status === 'ongoing' ? '持续中' : '已缓解'}${data.duration ? ' · ' + escape(data.duration) : ''}`;
  if (record.kind === 'condition') return escape({ suspected: '待查 / 个人转述，不是确诊', confirmed: '报告记载已诊断，以原件为准', ruled_out: '记录为已排除', resolved: '记录为已缓解' }[data.status]);
  if (record.kind === 'reminder') return data.done ? '已完成' : '待完成 · 仅应用内提醒';
  return escape(data.hospital || data.reason || '未录入医院与主诉');
}
function documentsView() {
  return `${header('原始资料', '先把原件留好。每条摘录，都可以找到它的来处。', button('导入资料', 'upload', '', 'primary', 'upload'))}
    <div class="upload-zone" id="upload-zone"><span class="upload-symbol">${icon('upload')}</span><div><h2>将报告拖到这里，或选择文件</h2><p>PDF、PNG、JPG、UTF-8 TXT，单份不超过 20 MB。重复内容自动识别。</p><small>本地不做 OCR；可在下方另行授权 AI 整理图片或报告。检验值仍需人工核对。</small></div>${button('选择文件', 'upload')}</div>
    <section class="panel documents-panel"><div class="panel-heading"><h2>我的资料库</h2><span class="muted">${state.data.documents.length} 份原件</span></div>${state.data.documents.length ? `<div class="table-scroll"><table><thead><tr><th>文件</th><th>大小</th><th>来源关联</th><th>完整性标识</th><th>操作</th></tr></thead><tbody>${state.data.documents.map(doc => `<tr><td><span class="document-name">${icon('file')}<span><strong>${escape(doc.filename)}</strong><small>${doc.mime === 'text/plain' ? '文字资料' : doc.mime === 'application/pdf' ? 'PDF 原件' : '图像原件'} · ${localDate(doc.created_at)}</small></span></span></td><td>${doc.size < 1024 * 1024 ? (doc.size / 1024).toFixed(1) + ' KB' : (doc.size / (1024 * 1024)).toFixed(1) + ' MB'}</td><td>${doc.links} 条记录</td><td><code>${escape(doc.sha256.slice(0, 10))}…</code></td><td><div class="table-actions">${doc.mime === 'text/plain' ? button('查看', 'preview-document', `data-id="${doc.id}"`, 'quiet small') : ''}${button('下载', 'download-document', `data-id="${doc.id}"`, 'quiet small')}${button('摘录', 'extract-document', `data-id="${doc.id}"`, 'quiet small')}${button('移除', 'delete-document', `data-id="${doc.id}"`, 'quiet small danger-text')}</div></td></tr>`).join('')}</tbody></table></div>` : empty('还没有原件', '导入一份报告，或先手工记录。原件不会被 AI 或后续编辑覆盖。')}</section>
    ${alertBox('文件保存在本机，但应用没有提供全库加密。请启用操作系统磁盘加密，并妥善保护导出的备份。')}`;
}
function trendsView() {
  const groups = observationGroups();
  if (state.series >= groups.length) state.series = 0;
  const group = groups[state.series];
  return `${header('指标趋势', '关注长期变化，而不是用一次数字给健康下结论。', button('录入指标', 'add', 'data-kind="observation"', 'primary', 'plus'))}${groups.length ? `<div class="metric-select-row"><label for="series-select">查看指标</label><select id="series-select">${groups.map((items, index) => `<option value="${index}" ${index === state.series ? 'selected' : ''}>${escape(items[0].title)} · ${escape(items[0].data.unit)} · ${escape(items[0].data.lab || '机构/方法未填')}</option>`).join('')}</select></div><section class="panel"><div class="panel-heading"><div><h2>${escape(group[0].title)}</h2><p>${escape(group[0].data.lab || '未记录检测机构/方法，请核对可比性')}</p></div>${badge('不自动换算单位', 'blue')}</div><div class="chart-metric"><strong>${valueText(group[0])}</strong>${badge(...flag(group[0]))}<span>最近一次 ${fmtDate(group[0].date)}</span></div>${chart(group, true)}</section><section class="panel"><div class="panel-heading"><h2>每一次，都有依据</h2><span>${group.length} 条记录</span></div><div class="table-scroll"><table><thead><tr><th>日期</th><th>数值</th><th>原报告参考范围</th><th>核对状态</th><th>原件与详情</th></tr></thead><tbody>${group.map(record => `<tr><td>${fmtDate(record.date)}</td><td class="value-cell">${valueText(record)}</td><td>${record.data.reference_low ?? '未录'} ～ ${record.data.reference_high ?? '未录'}</td><td>${pending(record)}</td><td>${button('查看依据', 'detail', `data-id="${record.id}"`, 'quiet small', 'file')}</td></tr>`).join('')}</tbody></table></div></section>` : `<section class="panel">${empty('为自己留下一条基线', '录入报告中的数值、单位、参考范围和检测机构。同一项目积累两次后，就可以查看趋势。', button('录入第一条指标', 'add', 'data-kind="observation"', 'primary', 'plus'))}</section>`}${alertBox('参考范围不是疾病诊断标准。只有已核对、同名、同单位、同机构/方法的精确值进入折线；方法未填写时仍需人工判断可比性。')}`;
}
function careView() {
  const selected = records(state.care);
  const urgent = records('symptom').some(record => record.data.red_flags && record.data.status === 'ongoing');
  return `${header('用药与症状', '分清正在发生的感受、记录中的医嘱，以及尚待确认的原因。', button('新增' + names[state.care], 'add', `data-kind="${state.care}"`, 'primary', 'plus'))}${urgent ? alertBox(state.data.safety, 'danger') : ''}<div class="tabs" role="tablist" aria-label="档案分类">${[['medication', '用药记录'], ['symptom', '症状日记'], ['condition', '健康问题']].map(([kind, label]) => `<button role="tab" aria-selected="${state.care === kind}" data-action="care-tab" data-kind="${kind}" class="${state.care === kind ? 'selected' : ''}">${label} <span>${records(kind).length}</span></button>`).join('')}</div>${state.care === 'medication' ? alertBox('这里只记录已有处方和实际用药，不提供开药或剂量建议。“当前有效”根据记录状态与起止日期计算，不保证实际服用。') : state.care === 'condition' ? alertBox('“待查 / 个人转述”不会自动升级为诊断。“报告记载已诊断”必须关联原件，点击保存不代表临床确诊。') : alertBox('症状程度由你主观记录，不是疾病严重性评分。严重或突然出现的不适请及时就医，不等待本应用判断。')}<div class="care-grid">${selected.length ? selected.map(record => `<article class="panel care-card"><div class="care-card-top"><span class="record-symbol ${record.kind}">${icon(record.kind === 'medication' ? 'pill' : 'heart')}</span>${pending(record)}</div><h2>${escape(record.title)}</h2><p class="care-description">${recordSnippet(record)}</p>${record.kind === 'symptom' ? `<div class="severity-display" aria-label="自述程度 ${record.data.severity} 分">${Array.from({ length: 10 }, (item, index) => `<i class="${index < record.data.severity ? 'filled' : ''}"></i>`).join('')}</div>` : ''}<div class="care-metadata"><span>${fmtDate(record.date)}</span><span>${escape(record.topic || record.department || '未设主题')}</span></div><p class="source-line">${sourceLine(record)}</p>${button('查看与编辑', 'detail', `data-id="${record.id}"`, 'secondary wide')}</article>`).join('') : `<section class="panel full-span">${empty('还没有' + names[state.care], state.care === 'medication' ? '如果有正在使用的处方药，请按原处方记录名称、剂量、频次和日期。不要填写猜测剂量。' : '用自己的话留下一笔。把事实记清楚，比急着得到结论更重要。', button('新增记录', 'add', `data-kind="${state.care}"`, 'primary', 'plus'))}</section>`}</div>`;
}
function foodArt(color) { return `<svg viewBox="0 0 240 135" class="food-art ${color}" aria-hidden="true"><ellipse cx="120" cy="110" rx="76" ry="10" class="food-shadow"/><ellipse cx="120" cy="67" rx="83" ry="44" class="plate-edge"/><ellipse cx="120" cy="64" rx="73" ry="35" class="plate-inner"/><path d="M47 68q5 42 73 44t73-44" class="bowl-front"/><ellipse cx="98" cy="61" rx="29" ry="22" class="food-rice"/><path d="M131 44q15-21 24-7 21-5 17 12 20 9 3 22-3 16-19 9-17 7-21-7-17-10-4-29" class="food-greens"/><circle cx="148" cy="69" r="13" class="food-accent"/><circle cx="162" cy="53" r="9" class="food-accent"/><path d="m87 52 6-3m9 9 7-3m-22 10 8 2m7-19 5 2" class="food-grain"/></svg>`; }
function planStale(plan) { const profile = state.data.profile; const constraints = plan.constraints; return state.data.nutrition_restrictions.length > 0 || constraints.diet !== profile.diet || JSON.stringify([...constraints.allergies].sort()) !== JSON.stringify([...profile.allergies].sort()); }
function mealsView() {
  const plan = state.data.plans.find(item => item.date === state.mealDate);
  const stale = plan && planStale(plan);
  return `${header('饮食计划', '认真吃饭，也是一种温柔的自我照顾。', `<input type="date" id="meal-date" aria-label="餐单日期" value="${escape(state.mealDate)}">` + button(plan ? '重新安排' : '安排三餐', 'generate-plan', '', 'primary', 'refresh'))}${alertBox(state.data.nutrition_notice)}<div class="diet-summary"><span>${icon('bowl')} ${state.data.profile.diet === 'unspecified' ? '饮食偏好未填写' : state.data.profile.diet === 'vegetarian' ? '蛋奶素偏好' : '均衡搭配偏好'}</span><span>已录过敏原：${escape(state.data.profile.allergies.join('、') || '未记录，请先核对')}</span><a href="#settings" class="text-link">修改饮食设置 ${icon('arrow')}</a></div>${stale ? alertBox('这是之前保存的餐单。当前健康或饮食限制已有变化，不再作为推荐；历史用餐记录仍可保留。请核对设置和食材，必要时咨询营养师。', 'warning') : ''}${plan ? `<div class="meal-grid">${[['breakfast', '早餐'], ['lunch', '午餐'], ['dinner', '晚餐']].map(([meal, label]) => { const entry = plan.meals[meal], recipe = state.data.recipes.find(item => item.id === entry.recipe_id); return `<article class="panel meal-card"><div class="meal-label"><h2>${label}</h2><span>${recipe.minutes} 分钟</span></div><div class="meal-art">${foodArt(recipe.color)}</div><h3>${escape(recipe.name)}</h3><ul class="ingredient-list">${recipe.ingredients.map(item => `<li>${escape(item)}</li>`).join('')}</ul><div class="allergen-line">${recipe.allergens.length ? '含：' + escape(recipe.allergens.join('、')) : '未标注常见过敏原，仍须核对包装'}</div><p class="recipe-method">${escape(recipe.method)}</p><div class="meal-actions">${button('换一道', 'swap-meal', `data-meal="${meal}" ${stale || entry.eaten || entry.note ? 'disabled' : ''}`, 'quiet small', 'refresh')}${button(entry.eaten || entry.note ? '修改实际记录' : '记录吃了什么', 'log-meal', `data-meal="${meal}"`, entry.eaten ? 'sage small' : 'secondary small', entry.eaten ? 'check' : 'plus')}</div>${entry.eaten ? '<div class="eaten-label">已记录用餐</div>' : ''}${entry.note ? `<p class="meal-note">实际：${escape(entry.note)}</p>` : ''}</article>`; }).join('')}</div><section class="panel shopping-panel"><div class="panel-heading"><div><h2>顺手记下采购清单</h2><p>对应当前餐单的食材，数量为菜谱示例，按实际人数调整。</p></div>${button('查看清单', 'shopping', '', 'secondary', 'file')}</div><div class="shopping-chips">${[...new Set(Object.values(plan.meals).flatMap(entry => state.data.recipes.find(item => item.id === entry.recipe_id).ingredients))].map(item => `<span>${escape(item)}</span>`).join('')}</div></section>` : `<section class="panel">${empty('今天吃什么，慢慢安排', '先到设置核对过敏原并确认一般成人膳食适用范围。特殊疾病、孕哺或医学饮食需求不在自动规划范围。', `<a class="button secondary" href="#settings">核对饮食设置</a>${button('安排这一天的三餐', 'generate-plan', '', 'primary', 'bowl')}`)}</section>`}<p class="page-note">菜谱为项目编写的示例家常搭配，并非注册营养师审核的完整膳食方案；未声明营养素精确值，不推算疾病治疗目标。</p>`;
}
function localAssistantView() {
  const answer = state.assistant;
  return `${header('档案助理', '先找到依据，再讨论意义。默认不调用任何模型或云服务。', badge('只读档案，不写诊断', 'sage'))}<div class="assistant-layout"><section class="panel assistant-main"><div class="assistant-intro"><span class="assistant-symbol">${icon('spark')}</span><div><h2>从你的记录中，找回有用的信息</h2><p>本地模式按类型与标题检索真实记录，不提供疾病推断。</p></div></div><div class="question-chips">${['最近的检验指标有哪些？', '我目前记录了哪些用药？', '最近有哪些症状？', '接下来有哪些随访？'].map(question => `<button data-action="ask-example" data-question="${escape(question)}" ${state.thinking ? 'disabled' : ''}>${escape(question)}</button>`).join('')}</div><form id="assistant-form"><label class="sr-only" for="question">想了解什么</label><textarea id="question" name="question" rows="3" maxlength="1000" placeholder="例如：低密度脂蛋白胆固醇最近的记录是什么？" required>${escape(answer?.question || '')}</textarea><div class="assistant-controls"><label class="check-label"><input type="checkbox" id="use-model" ${state.useModel ? 'checked' : ''} ${!state.data.model ? 'disabled' : ''}>使用本机 Ollama 草稿${!state.data.model ? '（需先配置）' : ''}</label><button class="button primary" ${state.thinking ? 'disabled' : ''} type="submit">${icon(state.thinking ? 'clock' : 'spark')}${state.thinking ? '正在整理…' : '查阅我的档案'}</button></div></form><div id="assistant-result" aria-live="polite">${state.thinking ? '<div class="thinking"><span class="loading-dot"></span>只读取本地记录，正在整理来源…</div>' : answer ? `<div class="answer-topline">${badge(answer.mode === 'ollama' ? '本机模型 + 事实摘录' : '本地事实摘录', 'sage')}<span>引用 ${answer.records_used} 条记录</span></div>${answer.model_draft ? `<section class="model-draft"><h3>模型生成草稿 · 未逐句核验</h3><p>${escape(answer.model_notice)}</p><div class="preserve-lines">${escape(answer.model_draft)}</div></section>` : ''}${answer.sections.map(section => `<section class="answer-section"><h3>${escape(section.heading)}</h3><p class="preserve-lines">${escape(section.text)}</p></section>`).join('')}<div class="answer-sources"><h3>这次使用的记录</h3>${answer.sources.length ? answer.sources.map(source => button(`${escape(source.title)} · ${fmtDate(source.date)}`, 'detail', `data-id="${source.id}"`, 'source-button', 'file')).join('') : '<p>没有来源记录，不补造信息。</p>'}</div>` : '<div class="assistant-placeholder"><span>“我上次是什么时候检查的？”</span><p>这些小问题，也值得有一个清楚的答案。</p></div>'}</div></section><aside class="assistant-aside"><section class="panel"><h2>它能做什么</h2><ul class="capability-list"><li>${icon('check')}查找和摘录已有记录</li><li>${icon('check')}保留日期、单位与来源</li><li>${icon('check')}提醒待核对和信息缺口</li></ul><hr><h3>它不会做什么</h3><p>不会确诊、开处方或修改用药，也不会把一次异常或个人怀疑写成疾病。</p><a href="#summary" class="text-link">准备一份就医摘要 ${icon('arrow')}</a></section><div class="safety-note">${icon('warning')}<p>${escape(state.data.safety)}</p></div></aside></div>`;
}
function summaryDetails(record) {
  const data = record.data, parts = [];
  if (record.department) parts.push('科室：' + record.department);
  if (record.topic) parts.push('健康主题：' + record.topic);
  if (record.kind === 'visit') {
    if (data.doctor) parts.push('医生：' + data.doctor);
    if (data.reason) parts.push('主诉：' + data.reason);
    if (data.conclusion) parts.push('报告 / 医嘱原文摘录：' + data.conclusion);
  }
  if (record.kind === 'observation') parts.push('报告参考范围：' + (data.reference_low ?? '未录') + ' ～ ' + (data.reference_high ?? '未录') + ' ' + data.unit, '机构 / 方法：' + (data.lab || '未填写'));
  if (record.kind === 'medication') parts.push('起止：' + data.start_date + ' ～ ' + (data.end_date || '未录结束日期'), '处方来源：' + data.prescriber);
  if (record.kind === 'symptom') {
    if (data.triggers) parts.push('诱因 / 缓解因素：' + data.triggers);
    if (data.red_flags) parts.push('已记录危险表现，请结合当前情况及时就医。');
  }
  if (record.notes) parts.push('补充记录：' + record.notes);
  const doc = state.data.documents.find(item => item.id === record.document_id);
  if (doc) parts.push('关联原件：' + doc.filename);
  return parts.length ? `<p class="preserve-lines">${escape(parts.join('\n'))}</p>` : '';
}
function summaryView() {
  const profile = state.data.profile;
  const latest = observationGroups().map(group => group[0]);
  const medications = records('medication').filter(currentMedication);
  const symptoms = records('symptom').filter(record => record.data.status === 'ongoing');
  const problems = records('condition');
  const visits = records('visit');
  const renderRows = items => items.length ? items.map(record => `<div class="summary-row"><div><strong>${escape(record.title)}</strong><p>${recordSnippet(record)}</p>${summaryDetails(record)}<small>${escape(record.source_label || '未填写来源说明')}${record.document_id ? ' · 已关联原件' : ' · 未附原件'} · ${record.verification === 'verified' ? '用户已核对' : '待核对'}</small></div><span>${fmtDate(record.date)}</span></div>`).join('') : '<p class="muted">尚未记录，不代表不存在。</p>';
  const sections = [['按记录日期当前有效的用药', medications], ['持续中的症状', symptoms], ['健康问题与确认状态', problems], ['各项指标的最近一次记录', latest], ['就诊记录', visits]];
  return `${header('就医摘要', '把重要信息带到诊室，和医生一起核对。', button('打印 / 保存 PDF', 'print', '', 'primary', 'print'))}
    <article class="summary-paper">
      <div class="summary-title"><div><span class="summary-kicker">知己 · 个人健康记录</span><h2>${profile.name ? escape(profile.name) + '的就医摘要' : '就医摘要'}</h2><p>生成日期：${fmtDate(state.data.today)}${state.data.demo ? ' · 完全虚构的合成演示' : ''}</p></div>${icon('file')}</div>
      <div class="summary-warning">此摘要由个人录入资料整理，可能不完整。“已核对”不代表临床验证。诊断与用药以原始文件及医生评估为准。</div>
      <section><h3>基本信息与过敏</h3><div class="summary-basics"><span>出生日期：${profile.birth_date ? fmtDate(profile.birth_date) : '未填写'}</span><span>过敏原：${escape(profile.allergies.join('、') || '未记录（不是“无过敏”）')}</span><span>紧急联系人：${escape(profile.emergency_contact || '未填写')}</span></div>${profile.notes ? `<p class="preserve-lines">${escape(profile.notes)}</p>` : ''}</section>
      <section><h3>已记录的特殊饮食需求</h3><p>${profile.clinical_diet ? '已标记特殊医学饮食 / 孕哺需求，或尚不确定一般膳食是否适用。' : '未标记特殊需求，不代表无需限制。'}</p><p class="preserve-lines">${escape(profile.diet_notes || '未录入医生或营养师的饮食医嘱。')}</p></section>
      ${sections.map(([title, items]) => `<section><h3>${title}</h3>${renderRows(items)}</section>`).join('')}
      <section><h3>待办与复诊问题</h3>${renderRows(records('reminder').filter(record => !record.data.done))}<div class="doctor-questions"><p>希望与医生确认：</p><p>1. 哪些资料需要补充或复查？</p><p>2. 当前记录的症状、用药及饮食安排是否需要调整？</p><p>3. 下一次随访的时间和需要观察的变化是什么？</p></div></section>
      <section><h3>原始资料清单</h3>${state.data.documents.length ? state.data.documents.map(doc => `<p>${escape(doc.filename)} <small>· SHA-256 ${escape(doc.sha256.slice(0, 16))}…</small></p>`).join('') : '<p>未附原件，请带上实际检查报告。</p>'}</section>
      <div class="summary-end">本摘要未包含 AI 生成的推测；请随身携带原始报告。知己 · 本地健康手记</div>
    </article>`;
}
function inputField(label, name, value = '', type = 'text', extra = '', help = '') { return `<label class="field"><span>${label}</span><input type="${type}" name="${name}" value="${escape(value)}" ${extra}>${help ? `<small>${help}</small>` : ''}</label>`; }
function textArea(label, name, value = '', extra = '') { return `<label class="field full-span"><span>${label}</span><textarea name="${name}" rows="3" maxlength="4000" ${extra}>${escape(value)}</textarea></label>`; }
function selectField(label, name, selected, choices, extra = '') { return `<label class="field"><span>${label}</span><select name="${name}" ${extra}>${choices.map(([value, title]) => `<option value="${escape(value)}" ${selected === value ? 'selected' : ''}>${escape(title)}</option>`).join('')}</select></label>`; }
function settingsView() {
  const profile = state.data.profile;
  const others = profile.allergies.filter(item => !state.data.allergens.includes(item));
  return `${header('设置与备份', '资料怎样保存、怎样使用，你始终有决定权。')}
    <div class="settings-layout"><section class="panel"><div class="panel-heading"><h2>我的基本档案</h2>${icon('heart')}</div>
    <form id="profile-form" data-version="${escape(state.data.profile_version || '')}"><div class="form-grid">
      ${inputField('称呼（可选）', 'name', profile.name, 'text', 'maxlength="40"')}
      ${inputField('出生日期（可选）', 'birth_date', profile.birth_date, 'date', `max="${state.data.today}"`)}
      ${selectField('性别（可选）', 'sex', profile.sex, [['unspecified', '不填写'], ['female', '女'], ['male', '男'], ['other', '其他']])}
      ${inputField('紧急联系人（可选）', 'emergency_contact', profile.emergency_contact, 'text', 'maxlength="160"')}
      ${textArea('个人备注 / 家族史（自行记录）', 'notes', profile.notes)}
      <div class="field full-span"><span>已知食物过敏原</span><div class="allergen-options">${state.data.allergens.map(item => `<label><input type="checkbox" name="allergies" value="${item}" ${profile.allergies.includes(item) ? 'checked' : ''}>${item}</label>`).join('')}</div><small>未勾选表示未记录，不保证没有过敏。严重过敏请勿依赖此菜谱筛选。</small></div>
      ${inputField('其他过敏原（顿号分隔）', 'other_allergies', others.join('、'), 'text', 'maxlength="400"', '不在菜谱识别范围的过敏原会暂停自动餐单。')}
      ${selectField('日常饮食偏好', 'diet', profile.diet, [['unspecified', '暂未填写'], ['balanced', '均衡搭配'], ['vegetarian', '蛋奶素（含蛋奶，可按过敏排除）']])}
      ${textArea('医生 / 营养师的饮食医嘱', 'diet_notes', profile.diet_notes)}
      <label class="check-label full-span"><input type="checkbox" name="clinical_diet" ${profile.clinical_diet ? 'checked' : ''}>我有特殊医学饮食需求、处于孕哺期，或不确定是否适用一般膳食</label>
      <label class="check-label full-span acknowledgment"><input type="checkbox" name="diet_acknowledged" ${profile.diet_acknowledged ? 'checked' : ''}>我已核对过敏与饮食需求，仅将餐单用于一般成人家常膳食灵感，不作为治疗方案</label>
    </div><div class="form-footer"><span class="form-message" role="alert"></span><button class="button primary" type="submit">${icon('check')}保存档案设置</button></div></form></section>
    <div class="settings-aside"><section class="panel"><h2>${icon('lock')} 数据与隐私</h2><dl class="privacy-list"><div><dt>存储位置</dt><dd class="data-path">${escape(state.data.data_directory)}</dd></div><div><dt>网络</dt><dd>仅本机访问；云端分析可选，逐次确认后才外发</dd></div><div><dt>文件保护</dt><dd>原件哈希校验；应用未提供全库加密</dd></div></dl><p class="page-note">建议启用 FileVault / BitLocker 等磁盘加密。目录不要放入公共仓库或未加密的云同步空间。</p><a href="#models" class="text-link">管理 API 模型与内存密钥 ${icon('arrow')}</a></section>
    <section class="panel"><h2>备份与恢复</h2><p>导出包含档案、科室关联、AI 草稿、实际饮食和原件的 ZIP，恢复时逐份校验。备份<strong>未加密</strong>，请按敏感医疗资料妥善保管。</p>${button('导出完整备份', 'backup', '', 'secondary wide', 'download')}${button('恢复到空档案', 'restore', '', 'quiet wide', 'upload')}<small>仅支持恢复到全新空目录。API Key、模型配置和操作日志不随便携备份恢复。</small></section>
    <section class="panel"><h2>可选的本机模型</h2><p>Ollama 仅连接固定地址 127.0.0.1:11434。云端模型在“模型连接”单独配置，不开启也能使用本地档案功能。</p><form id="model-form">${inputField('Ollama 模型名称', 'model', state.data.model || '', 'text', 'maxlength="120" placeholder="例如 qwen3:8b"')}${state.models.length ? `<div class="model-list">本机可用：${state.models.map(name => button(escape(name), 'select-model', `data-model="${escape(name)}"`, 'quiet small')).join('')}</div>` : ''}<div class="model-buttons">${button('检测本机服务', 'detect-model', '', 'secondary small')}<button type="submit" class="button primary small">保存</button></div><span class="form-message" role="alert"></span></form><small>请只使用已确认不会转发云端的本机模型。模型草稿可能出错，不会写入临床记录。</small></section></div></div>
    <section class="panel"><div class="panel-heading"><h2>最近操作</h2><span class="muted">只记录操作类型，不记录正文</span></div><div class="audit-list">${state.data.audits.slice(0, 12).map(item => `<div><span>${escape({ create: '新增', update: '修改', delete: '删除', import: '导入', export: '导出', restore: '恢复' }[item.action] || item.action)} ${escape(names[item.entity] || { document: '原件', settings: '设置', backup: '备份', meal_plan: '餐单', ai_draft: 'AI 草稿', document_routes: '科室关联', food_intake: '实际饮食' }[item.entity] || item.entity)}</span><time>${escape(new Date(item.at).toLocaleString('zh-CN', { hour12: false }))}</time></div>`).join('') || '<p class="muted">暂无操作。</p>'}</div></section>`;
}
function taskName(task) { return { breakfast: '看懂这一餐', document: '报告整理', chat: '健康资料问答', local: '本地查阅' }[task]; }
function aiTabs() { return `<div class="task-tabs" role="tablist" aria-label="助理任务">${[['breakfast', 'bowl'], ['document', 'file'], ['chat', 'spark'], ['local', 'lock']].map(([task, symbol]) => `<button type="button" role="tab" aria-selected="${state.aiTask === task}" data-action="ai-task" data-task="${task}" class="${state.aiTask === task ? 'selected' : ''}">${icon(symbol)}${taskName(task)}</button>`).join('')}</div>`; }
function analysisList() {
  const drafts = (state.data.analyses || []).filter(item => item.task === state.aiTask);
  return `<section class="draft-history"><div class="panel-heading"><h2>留在本地的分析</h2><span>${drafts.length} 份</span></div>${drafts.length ? drafts.map(item => `<button class="draft-link ${item.id === state.analysisId ? 'active' : ''}" data-action="open-analysis" data-id="${item.id}"><span>${escape(item.result.summary.slice(0, 44))}</span><small>${escape(new Date(item.created_at).toLocaleDateString('zh-CN'))} · ${item.intake.note ? '已记实际饮食' : 'AI 草稿'}</small></button>`).join('') : '<p class="muted">分析后自动保存在这里。识别结果是草稿，与你核对过的病历分开。</p>'}</section>`;
}
function analysisResult(item) {
  if (!item) return `<div class="analysis-empty"><div class="place-setting">${foodArt('green')}</div><h2>${state.aiTask === 'breakfast' ? '先看看盘子里有什么' : '让资料清楚一些，让判断谨慎一些'}</h2><p>提供一张照片或一段描述，先核对发送内容。<br>识别结果、不确定之处和建议会分开展示。</p><div class="process-line"><span>选择资料</span><span>确认外发</span><span>核对草稿</span></div></div>`;
  const result = item.result;
  const list = (title, items) => items?.length ? `<section class="analysis-section"><h3>${title}</h3><ul>${items.map(text => `<li>${escape(text)}</li>`).join('')}</ul></section>` : '';
  return `<article class="analysis-result"><div class="panel-heading"><div><span class="badge amber">AI 草稿 · 未经医学核验</span><h2>${taskName(item.task)}</h2></div>${button('删除草稿', 'delete-analysis', `data-id="${item.id}"`, 'quiet small danger-text')}</div><p class="analysis-summary preserve-lines">${escape(result.summary)}</p>
    ${result.foods ? `<section class="analysis-section"><h3>可能识别到的食物</h3>${result.foods.length ? result.foods.map(food => `<div class="food-observation"><span>${icon('bowl')}<strong>${escape(food.name)}</strong><small>${escape(food.portion)}</small></span>${badge({ low: '待确认', medium: '中等把握', high: '较高把握' }[food.confidence])}</div>`).join('') : '<p>未识别出可确认的食物。请补充描述或更清晰的照片。</p>'}</section>` : ''}
    ${list('可以考虑的小调整', result.suggestions)}${list('这些还不能确定', result.uncertainties)}${list('再补充一点信息', result.questions)}
    ${item.task === 'document' ? `<section class="analysis-section"><h3>建议归入的科室</h3>${result.departments.map(link => `<p><strong>${escape(link.name)}</strong>：${escape(link.evidence)}</p>`).join('') || '<p>没有明确依据，保持待分类。</p>'}${item.document_id ? button('核对科室关联', 'ai-route', `data-id="${item.id}"`, 'secondary', 'folder') : ''}</section><section class="analysis-section"><h3>原文摘录候选</h3><p class="muted">不是已确认事实。逐条对照原件，再手动录入；不会自动生成诊断、数值或用药。</p>${result.excerpts.map((entry, index) => `<div class="excerpt"><strong>${escape(entry.title)}</strong><blockquote>${escape(entry.quote)}</blockquote><small>${escape(entry.location)} · ${escape(entry.department)} · 位置与摘录都需核对</small>${button('核对并录入', 'review-excerpt', `data-id="${item.id}" data-index="${index}"`, 'quiet small', 'plus')}</div>`).join('')}</section>` : ''}
    ${item.task === 'breakfast' ? `<section class="intake-result"><h3>实际吃了什么，由你确认</h3><p>${item.intake.note ? escape(item.intake.date + ' · ' + item.intake.note) : '模型猜测不会自动变成饮食事实。核对食物、份量和实际日期后，单独留下自己的记录。'}</p>${button(item.intake.note ? '编辑实际饮食' : '记录实际饮食', 'actual-intake', `data-id="${item.id}"`, 'primary', 'check')}</section>` : ''}
    <details class="provenance"><summary>查看发送依据与模型信息</summary><p>${escape(item.provenance.provider)} · ${escape(item.provenance.model)}</p><p class="data-path">${escape(item.provenance.endpoint)}</p><p>原件：${escape(item.provenance.source?.filename || '未附原件，仅文字')}。${item.provenance.source ? 'SHA-256 ' + escape(item.provenance.source.sha256) : ''}</p><pre>${escape(item.provenance.submitted_text)}</pre></details>
    <p class="page-note">照片不能确认过敏原、油盐糖或准确营养量。建议不是处方，医疗问题请结合医生评估。</p></article>`;
}
function assistantView() {
  if (state.aiTask === 'local') return aiTabs() + localAssistantView();
  const usingCodex = state.aiEngine === 'codex';
  const config = (usingCodex ? state.data.codex : state.data.cloud) || {};
  const item = (state.data.analyses || []).find(item => item.id === state.analysisId && item.task === state.aiTask);
  const selected = state.data.documents.find(doc => doc.id === state.aiDocument);
  const placeholders = { breakfast: '例如：这是今天的早餐，豆浆一杯、鸡蛋一个、包子两个。豆浆是否加糖我不确定。', document: '可粘贴已脱敏的报告文字；或选中原件，让模型提出科室和摘录建议。', chat: '例如：帮我整理这次检查中需要向医生询问的问题。' };
  return `${header('档案助理', '从这一餐，到每一份报告。先看清事实，再决定下一步。', `<a class="button secondary" href="#models">${icon('settings')}模型连接</a>`)}${aiTabs()}
    <div class="engine-picker" role="group" aria-label="选择分析连接">${[['api', 'API Key'], ['codex', 'ChatGPT 账号 · Codex']].map(([engine, label]) => button(label, 'ai-engine', `data-engine="${engine}" aria-pressed="${state.aiEngine === engine}" ${state.aiBusy ? 'disabled' : ''}`, state.aiEngine === engine ? 'primary' : 'secondary')).join('')}</div>
    <div class="ai-workspace"><div class="ai-input-column"><section class="panel compose-panel"><div class="panel-heading"><h2>${taskName(state.aiTask)}</h2>${badge(usingCodex ? (config.has_key ? 'ChatGPT 已连接' : '尚未连接 ChatGPT') : (config.has_key ? '已配置 API' : '尚未配置 API'), config.has_key ? 'sage' : 'amber')}</div>
      ${!config.has_key ? `<div class="setup-note">先在<a href="#models">模型连接</a>${usingCodex ? '连接本机 Codex、用 ChatGPT 登录并选择模型。无需 API Key；不等于离线或无限免费。' : '填写服务商、模型名与 API Key。没有密钥也可使用“本地查阅”。'}</div>` : `<div class="provider-caption">${escape(config.model)}<small>${escape(config.base_url)}</small></div>`}
      <form id="cloud-analysis-form"><label class="field"><span>${state.aiTask === 'breakfast' ? '描述你的这一餐' : '问题或补充说明'}</span><textarea name="text" rows="5" maxlength="12000" placeholder="${placeholders[state.aiTask]}">${escape(state.aiText)}</textarea></label>
      <div class="attachment-picker">${icon(state.aiTask === 'breakfast' ? 'bowl' : 'file')}<div><strong>${selected ? escape(selected.filename) : state.aiTask === 'breakfast' ? '加一张早餐照片' : '添加报告照片或原件'}</strong><small>先保存本机，不会自动发送到服务商</small></div>${button('选择文件', 'ai-upload', '', 'secondary small')}</div>
      ${selectField('或使用本地已有资料', 'document_id', state.aiDocument, [['', '不附文件，仅发送文字'], ...state.data.documents.map(doc => [doc.id, doc.filename])])}
      <div class="consent-options"><label class="check-label"><input type="checkbox" name="include_profile" ${state.aiProfile ? 'checked' : ''}>附上我的饮食约束（过敏、偏好、医嘱及适用限制；不含姓名或联系方式）</label><label class="check-label"><input type="checkbox" name="include_records" ${state.aiRecords ? 'checked' : ''}>附上相关档案摘录（最多 12 条，可能包含就诊等敏感信息）</label></div>
      <p class="form-message" role="alert">${escape(state.aiError)}</p><button type="submit" class="button primary wide" ${!config.has_key || state.aiBusy ? 'disabled' : ''}>${icon('spark')}${state.aiBusy ? '正在分析，请勿重复发送…' : '预览并确认发送'}</button><p class="send-footnote">下一步将展示接收方与具体内容。可能收费，默认不发送你的完整病史。</p></form></section>${analysisList()}</div>
      <section class="panel analysis-canvas" aria-live="polite">${state.aiBusy ? `<div class="analysis-empty"><span class="loading-dot"></span><h2>模型正在阅读本次授权内容</h2><p>不自动重试、不执行模型指令。可以切换页面，结果完成后保存在本地。</p>${state.aiActiveEngine === 'codex' ? button('取消本次 Codex 分析', 'codex-cancel') + '<p>最长等待 150 秒；取消不能撤回外发内容或额度。</p>' : ''}</div>` : analysisResult(item)}</section></div><div class="safety-note">${icon('warning')}<p>${escape(state.data.safety)}</p></div>`;
}
function safeCodexLoginURL(value) {
  if (typeof value !== 'string' || /[\s\\]/.test(value)) return '';
  try { const parsed = new URL(value); return parsed.protocol === 'https:' && ['auth.openai.com', 'chatgpt.com'].includes(parsed.hostname) && !parsed.username && !parsed.password && !parsed.hash && (!parsed.port || parsed.port === '443') ? value : ''; } catch { return ''; }
}
function codexConnectionView() {
  const config = state.data.codex || {}, disabled = state.codexControlBusy || config.busy ? 'disabled' : '';
  const loginURL = safeCodexLoginURL(config.login?.url);
  return `<section class="panel codex-connection"><div class="panel-heading"><div><h2>使用 ChatGPT 账号，不必填写 API Key</h2><p>电脑上的独立 Codex 连接。资料仍在本地，每次分析另行确认。</p></div>${badge(config.authenticated ? '已登录 ChatGPT' : config.connected ? 'Codex 已连接' : '尚未连接', config.authenticated ? 'sage' : 'amber')}</div>
    <p>请先从 OpenAI 官方渠道安装 Codex CLI。此连接不读取你原有的 Codex 登录、插件或聊天记录。<a class="text-link" href="https://developers.openai.com/codex/cli/" target="_blank" rel="noopener noreferrer">官方安装说明</a></p>
    <div class="codex-actions">${button(config.connected ? '重新连接本机 Codex' : '连接本机 Codex', 'codex-control', `data-control="connect" ${disabled}`, 'secondary')}${config.connected && !config.authenticated && !config.login ? button('使用 ChatGPT 登录', 'codex-control', `data-control="login" ${disabled}`, 'primary') : ''}${config.connected ? button(config.login ? '登录后刷新状态' : '刷新账号与模型', 'codex-control', `data-control="refresh" ${disabled}`) : ''}${config.login ? button('取消登录', 'codex-control', `data-control="cancel-login" ${disabled}`, 'quiet') : ''}${config.authenticated ? button('退出此连接的账号', 'codex-control', `data-control="logout" ${disabled}`, 'quiet') : ''}${config.connected ? button('断开连接', 'codex-control', `data-control="disconnect" ${disabled}`, 'quiet') : ''}${config.busy ? button('取消本次 Codex 分析', 'codex-cancel') : ''}</div>
    ${loginURL ? `<div class="codex-login"><strong>请在官方页面完成登录</strong><p>本应用不会索取密码、验证码或 Token。登录完成后回到这里刷新状态。</p><a class="button primary" href="${escape(loginURL)}" target="_blank" rel="noopener noreferrer">打开 OpenAI 官方登录页</a></div>` : ''}
    ${config.authenticated ? `<p>当前账号：${escape(config.account?.email || '未提供邮箱')} · 套餐：${escape(config.account?.plan || '未知')}。额度和模型以官方账号权限为准。</p><form id="codex-config-form" data-revision="${escape(config.revision)}">${selectField('Codex 可用模型（最多显示 100 项）', 'model', config.model, [['', '请选择模型'], ...(config.models || []).map(item => [item.model, item.name + (item.vision ? ' · 支持图片' : ' · 文字')])])}<label class="check-label"><input type="checkbox" name="vision" ${config.vision ? 'checked' : ''}>启用此模型的图片分析（须由 Codex 报告支持）</label><p class="form-message" role="alert"></p><div class="form-footer"><button type="submit" class="button primary" ${disabled}>保存 Codex 模型</button>${button('使用此连接分析', 'use-codex', config.has_key ? '' : 'disabled')}</div></form>` : ''}
    <p class="page-note">支持文字、JPG/PNG（单份 8 MB）；不直传 PDF。登录凭证由 Codex 保存在本档案目录的 .codex-connection/auth，未由应用加密，不进入 ZIP 或原件互传；请启用系统磁盘加密。断开不等于退出账号。此功能不开放电脑远程访问，也不是手机自动同步。</p><p id="codex-message" class="form-message" role="status">${escape(state.codexError || '')}${state.codexControlBusy ? '正在处理本机连接，请稍候…' : ''}</p></section>`;
}
async function codexControl(action) {
  if (state.codexControlBusy || !canLeave(() => codexControl(action))) return;
  state.codexControlBusy = true; state.codexError = ''; render();
  try { await request('/api/codex/' + action, { method: 'POST', json: { confirm: true } }); await refresh(false); }
  catch (error) { state.codexError = error.message; toast(error.message, true); await refresh(false).catch(() => {}); }
  finally { state.codexControlBusy = false; render(); }
}
function modelsView() {
  const config = state.data.cloud || { providers: [], provider: 'openai', model: '', base_url: '', has_key: false };
  return `${header('模型连接', '本地资料库不变。模型服务由你选择，发送范围由你决定。')}${codexConnectionView()}<div class="connection-layout"><section class="panel connection-form"><div class="panel-heading"><h2>API Key 连接（可选）</h2>${badge(config.has_key ? '密钥在本次内存中' : '未连接密钥', config.has_key ? 'sage' : 'amber')}</div><form id="cloud-config-form" data-revision="${escape(config.revision || '')}">
    ${selectField('服务商', 'provider', config.provider, config.providers.map(item => [item.id, item.name]), 'id="cloud-provider"')}
    ${inputField('API Base URL', 'base_url', config.base_url, 'url', `required id="cloud-base" ${config.provider !== 'custom' ? 'readonly' : ''}`, '兼容 Chat Completions 的 HTTPS 接口，通常以 /v1 结尾；仅允许公网 443 端口。')}
    ${inputField('模型名称', 'model', config.model, 'text', 'required maxlength="120" placeholder="填写服务商提供的具体模型 ID"', '早餐照片和报告图片需要视觉模型；纯文字模型只能分析文字。')}
    ${inputField('API Key', 'api_key', '', 'password', `maxlength="512" autocomplete="off" spellcheck="false" placeholder="${config.has_key ? '留空保留当前密钥；更换服务商需重新输入' : '仅保存到服务端内存，重启后需重新填写'}"`)}
    <label class="check-label"><input type="checkbox" name="vision" ${config.vision ? 'checked' : ''}>我确认此模型支持图片输入</label><p class="form-message" role="alert"></p><div class="form-footer">${button('清除内存密钥', 'clear-cloud-key', config.has_key ? '' : 'disabled', 'quiet')}<button type="submit" class="button primary">保存连接设置</button></div></form></section>
    <aside class="connection-notes"><section class="privacy-promise"><span class="assistant-symbol">${icon('lock')}</span><h2>一把钥匙，不是一份全库授权</h2><p>保存密钥不发起模型请求。每一次分析都先展示外发文字、附件和服务商地址，再由你确认。</p><ul><li>Key 不写入 SQLite、日志、浏览器存储或备份。</li><li>重启服务后 Key 消失；模型名和地址可保留。</li><li>拒绝 API 重定向、内网地址与自动重试。</li><li>换服务商会清空旧密钥，避免误发。</li></ul></section><section class="panel"><h3>文件能力说明</h3><p>图片：JPEG / PNG，单次最多 8 MB。PDF：仅 OpenAI 的视觉模型直传；其他兼容服务可用报告页面图片或文字。</p><p>附件原样发送，未自动去除 EXIF、姓名或二维码。请先自行脱敏。服务商是否留存数据由其政策决定。</p></section><a class="button secondary wide" href="#assistant">去分析一餐或整理报告 ${icon('arrow')}</a></aside></div>`;
}
function specialtyData(name) {
  const docs = state.data.documents.filter(doc => (doc.routing?.links || []).some(link => link.name === name));
  const ids = new Set(docs.map(doc => doc.id));
  return { docs, items: records().filter(record => record.department === name || ids.has(record.document_id)) };
}
function departmentCatalog() {
  const list = [...(state.data.departments || [])];
  for (const name of [...new Set(records().map(item => item.department).filter(Boolean))]) if (!list.some(item => item.name === name)) list.push({ name, group: '你的其他科室', description: '沿用既有记录的科室名称', keywords: [] });
  return list;
}
function specialtyFolders() {
  const query = state.specialtyQuery.toLowerCase();
  const list = departmentCatalog().filter(item => (!state.specialtyGroup || item.group === state.specialtyGroup) && (!query || [item.name, item.description, ...(item.keywords || [])].join(' ').toLowerCase().includes(query))).filter(item => !state.specialtiesWithData || specialtyData(item.name).items.length || specialtyData(item.name).docs.length);
  const groups = [...new Set(list.map(item => item.group))];
  return groups.length ? groups.map(group => `<section class="specialty-section"><h2>${escape(group)}</h2><div class="specialty-grid">${list.filter(item => item.group === group).map(item => { const data = specialtyData(item.name); return `<button class="specialty-folder ${data.docs.length || data.items.length ? 'has-data' : ''}" data-action="open-specialty" data-name="${escape(item.name)}"><span class="folder-tab"></span><span class="specialty-name">${escape(item.name)}${icon('arrow')}</span><span class="specialty-description">${escape(item.description)}</span><span class="folder-count">${data.items.length} 条记录 · ${data.docs.length} 份资料${data.docs.some(doc => doc.routing.status === 'pending') ? ' · 待确认' : ''}</span></button>`; }).join('')}</div></section>`).join('') : empty('没有匹配的科室', '试试科室名称、身体部位，或关闭“仅看有资料”。');
}
function departmentsView() {
  const unresolved = state.data.documents.filter(doc => !doc.routing?.links.length || doc.routing.status !== 'confirmed');
  if (state.specialty) {
    const data = specialtyData(state.specialty);
    return `${header(escape(state.specialty), '同一原件可关联多个科室；展示跨科资料，不复制或更改原始事实。', button('全部科室', 'close-specialty', '', 'secondary', 'folder'))}<div class="specialty-detail"><section class="panel"><div class="panel-heading"><h2>科室记录</h2>${button('新增记录', 'specialty-add', '', 'primary', 'plus')}</div>${data.items.length ? data.items.map(item => `<div class="specialty-record">${badge(names[item.kind], 'blue')}<button data-action="detail" data-id="${item.id}">${escape(item.title)}</button><small>${fmtDate(item.date)} · ${escape(item.department || '由原件关联')}</small></div>`).join('') : empty('尚无这科的结构化记录', '导入原件后，核对 AI 摘录或手动记录。空档案不代表检查正常。')}</section><section class="panel"><h2>关联原件</h2>${data.docs.map(doc => routingCard(doc)).join('') || '<p class="muted">上传报告后可自动得到关键词分类建议，也可手动关联。</p>'}</section></div>`;
  }
  return `${header('全科室档案', '从头到脚，各有所属。跨科资料，仍是一份完整的你。', button('导入资料', 'upload', '', 'primary', 'upload'))}<div class="specialty-overview"><div><span class="atlas-symbol">${icon('heart')}</span><h2>为全身健康留好位置</h2><p>${(state.data.departments || []).length} 个常见专科与检查科室。覆盖综合、内外科、感官、妇幼、心理与康复；不同医院科名可能不同，保留自定义科室。</p></div><button class="inbox-count" data-action="open-inbox"><strong>${unresolved.length}</strong><span>份资料待分类 / 核对 ${icon('arrow')}</span></button></div><div class="specialty-tools"><label class="search-field">${icon('search')}<input id="specialty-search" type="search" aria-label="搜索科室或身体部位" placeholder="搜索科室、身体部位或检查名称" value="${escape(state.specialtyQuery)}"></label><label class="check-label"><input id="specialty-has-data" type="checkbox" ${state.specialtiesWithData ? 'checked' : ''}>仅看有资料</label></div><div class="specialty-groups">${['', ...new Set(departmentCatalog().map(item => item.group))].map(group => `<button class="${state.specialtyGroup === group ? 'selected' : ''}" data-action="specialty-group" data-group="${escape(group)}">${escape(group || '全部科室')}</button>`).join('')}</div><div id="specialty-results">${specialtyFolders()}</div><p class="page-note">此目录用于资料整理，不是全国统一的科室全集或就医分诊建议。关键词/模型分类不代表你患有该科疾病。</p>`;
}
function routingCard(doc) { return `<div class="routing-card"><div><strong>${escape(doc.filename)}</strong><div class="routing-tags">${(doc.routing?.links || []).map(link => badge(link.name, 'blue')).join('') || badge('待分类')}${badge(doc.routing?.status === 'confirmed' ? '已确认关联' : '分类建议待确认', doc.routing?.status === 'confirmed' ? 'sage' : 'amber')}</div></div><div class="routing-actions">${button('核对科室', 'route-document', `data-id="${doc.id}"`, 'secondary small')}${button('AI 整理', 'analyze-document', `data-id="${doc.id}"`, 'quiet small', 'spark')}</div></div>`; }
function documentWorkspaceView() { return documentsView() + `<section class="panel"><div class="panel-heading"><div><h2>报告分科与整理</h2><p>上传只保存在本机；文字/文件名先做关键词分类。需要视觉理解时，另行确认 AI 外发。</p></div><a href="#departments" class="text-link">全部科室 ${icon('arrow')}</a></div>${state.data.documents.map(routingCard).join('') || '<p class="muted">上传后，各份原件的分类建议会出现在这里。</p>'}</section>`; }
function mealWorkspaceView() { return `<div class="meal-ai-entry"><div>${icon('bowl')}<span><strong>已经吃了？看看这一餐</strong><small>照片或文字 → 食物识别 → 核对后记入实际饮食</small></span></div>${button('分析我的早餐', 'start-breakfast', '', 'primary', 'spark')}</div>` + mealsView() + `<section class="panel"><h2>已核对的实际饮食</h2>${(state.data.analyses || []).filter(item => item.task === 'breakfast' && item.intake.note).map(item => `<div class="specialty-record"><span>${fmtDate(item.intake.date)}</span><button data-action="open-food-entry" data-id="${item.id}">${escape(item.intake.note)}</button></div>`).join('') || '<p class="muted">分析草稿不会自动入账。在助理中填写实际吃了什么，才会显示在这里。</p>'}</section>`; }
function routeModal(doc, proposed = null) {
  const links = proposed || doc.routing?.links || [];
  openModal('核对科室关联', `<form id="routing-form" data-id="${doc.id}" data-version="${doc.routing_version || 1}" data-method="${proposed ? 'ai-reviewed' : 'manual'}"><div class="modal-body"><p><strong>${escape(doc.filename)}</strong></p><p class="muted">最多关联 12 个科室。只是资料归属，不会新增诊断。取消全部勾选会保留为未分科资料。</p>${links.map(item => `<p class="routing-evidence"><strong>${escape(item.name)}</strong>：${escape(item.evidence)}</p>`).join('')}<div class="department-checks">${(state.data.departments || []).map(item => `<label class="check-label"><input type="checkbox" name="departments" value="${escape(item.name)}" ${links.some(link => link.name === item.name) ? 'checked' : ''}>${escape(item.name)}</label>`).join('')}</div><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消', 'close-modal')}<button type="submit" class="button primary">确认科室关联</button></div></form>`, 'record-modal');
}
async function previewCloud(form, data) {
  state.aiText = String(data.get('text') || ''); state.aiDocument = String(data.get('document_id') || ''); state.aiProfile = data.has('include_profile'); state.aiRecords = data.has('include_records');
  const engine = state.aiEngine, task = state.aiTask;
  const prepared = await request((engine === 'codex' ? '/api/codex' : '/api/ai') + '/prepare', { method: 'POST', json: { task, text: state.aiText, document_id: state.aiDocument, include_profile: state.aiProfile, include_records: state.aiRecords } });
  if (!form.isConnected || state.route !== 'assistant' || state.aiEngine !== engine || state.aiTask !== task) return;
  openModal('确认本次发送给模型的内容', `<form id="cloud-consent-form" data-engine="${engine}" data-task="${task}" data-approval="${escape(prepared.approval_id)}"><div class="modal-body"><div class="alert warning">${icon('warning')}<div>${escape(prepared.notice)}</div></div><dl class="privacy-list"><div><dt>接收方</dt><dd class="data-path">${escape(prepared.endpoint)}</dd></div><div><dt>模型</dt><dd>${escape(prepared.model)}</dd></div><div><dt>原始附件</dt><dd>${prepared.source ? escape(prepared.source.filename) + ' · ' + (prepared.source.size / 1024).toFixed(1) + ' KB · 将原样发送' : '无'}</dd></div></dl><h3>将发送的文字</h3><pre class="consent-preview">${escape(prepared.text)}</pre><details class="provenance"><summary>系统提示词</summary><pre>${escape(prepared.system_prompt)}</pre></details><label class="check-label acknowledgment"><input type="checkbox" required name="consent">我确认上述接收方和发送内容，已自行处理隐私信息，并理解可能产生费用或消耗账号额度</label><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消，不发送', 'close-modal')}<button type="submit" class="button primary">确认发送并分析</button></div></form>`, 'record-modal');
}
async function runCloud(approval, engine = 'api', task = state.aiTask) {
  if (!['api', 'codex'].includes(engine)) { toast('连接类型已失效，请重新预览', true); return; }
  if (state.aiBusy) return;
  state.aiBusy = true; state.aiActiveEngine = engine; state.aiApproval = approval; state.aiError = ''; modal.close(); render();
  try { const item = await request((engine === 'codex' ? '/api/codex' : '/api/ai') + '/run', { method: 'POST', json: { approval_id: approval, confirm: true } }); await refresh(false); if (state.route === 'assistant' && state.aiTask === task && state.aiEngine === engine && !dirtyForms().length) { history.replaceState(null, '', '#assistant?task=' + task + '&analysis=' + item.id); } toast('分析草稿已保存，未修改任何临床记录'); }
  catch (error) { state.aiError = error.message; toast(error.message, true); }
  finally { state.aiBusy = false; state.aiApproval = ''; if (engine === 'codex') await refresh(false).catch(() => {}); if (state.route === 'assistant' || state.route === 'models') render(); }
}
const views = { home: homeView, timeline: timelineView, documents: documentWorkspaceView, trends: trendsView, care: careView, meals: mealWorkspaceView, assistant: assistantView, summary: summaryView, settings: settingsView, departments: departmentsView, models: modelsView };

function closeModal() {
  if (state.importBusy) { toast('正在导入原件，请稍候'); return false; }
  if (modal.querySelector('form[data-saving="true"]')) { toast('正在保存，请稍后关闭'); return false; }
  const form = modal.querySelector('form[data-dirty="true"]');
  if (form) { confirmDiscard([form], closeModal); return false; }
  modal.close(); state.confirmation = null; state.failedImports = [];
  return true;
}
function openModal(title, content, className = '') { if (state.importBusy || modal.open && (modal.querySelector('form[data-saving="true"]') || modal.querySelector('form[data-dirty="true"]'))) { toast('请先保存或关闭当前对话框'); return false; } if (modal.open) { modal.close(); state.confirmation = null; } modal.className = className; modal.innerHTML = `<div class="modal-heading"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="关闭对话框">${icon('close')}</button></div>${content}`; modal.showModal(); return true; }
function confirmation(title, message, callback, label = '确认') { if (openModal(title, `<div class="modal-body"><p class="preserve-lines">${escape(message)}</p></div><div class="modal-footer">${button('取消', 'close-modal')}${button(escape(label), 'confirm', '', 'primary')}</div>`, 'confirm-modal')) state.confirmation = callback; }
function recordFields(kind, data = {}) {
  if (kind === 'visit') return inputField('医院 / 机构', 'hospital', data.hospital, 'text', 'maxlength="120"') + inputField('医生', 'doctor', data.doctor, 'text', 'maxlength="80"') + textArea('主诉 / 此次就诊原因', 'reason', data.reason) + textArea('报告或医嘱原文摘录（勿填 AI 推测）', 'conclusion', data.conclusion);
  if (kind === 'observation') return inputField('检验值 *', 'value', data.value ?? '', 'number', 'required step="any"') + selectField('原始比较符', 'comparator', data.comparator || '=', [['=', '精确值 ='], ['<', '小于 <'], ['>', '大于 >'], ['≤', '小于等于 ≤'], ['≥', '大于等于 ≥']]) + inputField('单位 *', 'unit', data.unit || '', 'text', 'required maxlength="32" placeholder="例如 mmol/L"') + inputField('检测机构 / 方法', 'lab', data.lab, 'text', 'maxlength="160"', '不同方法不要写成同一个名称。') + inputField('报告参考下限（可空）', 'reference_low', data.reference_low ?? '', 'number', 'step="any"') + inputField('报告参考上限（可空）', 'reference_high', data.reference_high ?? '', 'number', 'step="any"');
  if (kind === 'medication') return inputField('原处方剂量（含单位）*', 'dose', data.dose, 'text', 'required maxlength="120" placeholder="按原处方抄录，不要猜测"') + inputField('原处方频次 *', 'frequency', data.frequency, 'text', 'required maxlength="120"') + inputField('开始日期 *', 'start_date', data.start_date || state.data.today, 'date', 'required') + inputField('结束日期（可空）', 'end_date', data.end_date || '', 'date') + selectField('记录状态', 'status', data.status || 'active', [['active', '按记录正在使用'], ['stopped', '已停止'], ['planned', '计划使用（非当前）']]) + inputField('处方来源 *', 'prescriber', data.prescriber, 'text', 'required maxlength="240"');
  if (kind === 'symptom') return inputField('自述程度（0–10）', 'severity', data.severity ?? 3, 'number', 'min="0" max="10" step="1" required', '主观不适程度，不是疾病风险评分。') + selectField('当前状态', 'status', data.status || 'ongoing', [['ongoing', '持续中'], ['resolved', '已缓解']]) + inputField('持续时长 / 频率', 'duration', data.duration, 'text', 'maxlength="160"') + inputField('诱因 / 缓解因素', 'triggers', data.triggers, 'text', 'maxlength="1000"') + `<label class="check-label full-span alert warning"><input type="checkbox" name="red_flags" ${data.red_flags ? 'checked' : ''}>同时有严重胸痛、明显呼吸困难、意识异常等危险表现（请立即就医，不等待记录）</label>`;
  if (kind === 'condition') return selectField('确认状态', 'status', data.status || 'suspected', [['suspected', '待查 / 个人转述（不是确诊）'], ['confirmed', '报告记载已诊断（须附原件）'], ['ruled_out', '记录为已排除'], ['resolved', '记录为已缓解']]);
  return selectField('提醒类型', 'category', data.category || 'followup', [['followup', '随访 / 复诊'], ['check', '检查安排'], ['other', '其他事项']]) + `<label class="check-label"><input type="checkbox" name="done" ${data.done ? 'checked' : ''}>已经完成</label>`;
}
function recordForm(kind = 'visit', existing = null, documentId = '') {
  const record = existing || { kind, title: '', date: state.data.today, department: '', topic: '', source_label: '', verification: 'pending', document_id: documentId, data: {}, notes: '' };
  openModal(existing ? '编辑' + names[record.kind] : '新增健康记录', `<form id="record-form" data-id="${existing?.id || ''}"><div class="modal-body"><div class="form-grid">${existing ? `<input type="hidden" name="kind" value="${record.kind}">` : selectField('记录类型', 'kind', record.kind, Object.entries(names), 'id="kind-switch"')}${inputField('记录日期 *', 'date', record.date, 'date', `required ${record.kind !== 'reminder' ? `max="${state.data.today}"` : ''}`)}${inputField(record.kind === 'observation' ? '指标原名 *' : record.kind === 'medication' ? '药物名称 *' : '标题 *', 'title', record.title, 'text', 'required maxlength="120"')}${inputField('科室', 'department', record.department, 'text', 'maxlength="80" placeholder="例如：全科、口腔科"')}${inputField('健康主题（跨科关联）', 'topic', record.topic, 'text', 'maxlength="100" placeholder="例如：年度体检、口腔护理"')}<div id="specific-fields" class="form-grid full-span">${recordFields(record.kind, record.data)}</div><div class="form-section-title full-span">来源与核对</div>${selectField('关联原始资料', 'document_id', record.document_id || '', [['', '未关联原件'], ...state.data.documents.map(doc => [doc.id, doc.filename])])}${inputField('来源说明', 'source_label', record.source_label, 'text', 'maxlength="240" placeholder="如个人自述、某次报告的第 2 页"')}${textArea('补充记录（不自动视为诊断）', 'notes', record.notes)}<label class="check-label full-span acknowledgment"><input type="checkbox" name="verified" ${record.verification === 'verified' ? 'checked' : ''}>我已将录入内容与原件或实际测量核对（仅录入核对，不是医学验证）</label></div><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消', 'close-modal')}<button type="submit" class="button primary">${icon('check')}保存记录</button></div></form>`, 'record-modal');
  modal.querySelector('#record-form').dataset.version = existing?.version || '';
  const departmentInput = modal.querySelector('[name="department"]');
  departmentInput.setAttribute('list', 'department-names');
  departmentInput.insertAdjacentHTML('afterend', `<datalist id="department-names">${(state.data.departments || []).map(item => `<option value="${escape(item.name)}"></option>`).join('')}</datalist>`);
}
function detail(id) {
  const record = getRecord(id);
  if (!record) { toast('这条记录已经不存在，请刷新', true); return; }
  const labels = { hospital: '医院', doctor: '医生', reason: '主诉', conclusion: '报告 / 医嘱摘录', value: '检验值', comparator: '比较符', unit: '单位', reference_low: '参考下限', reference_high: '参考上限', lab: '机构 / 方法', dose: '原处方剂量', frequency: '原处方频次', start_date: '开始日期', end_date: '结束日期', prescriber: '处方来源', severity: '自述程度 / 10', duration: '持续情况', triggers: '诱因 / 缓解因素' };
  const doc = state.data.documents.find(item => item.id === record.document_id);
  openModal(escape(record.title), `<div class="modal-body"><div class="detail-tags">${badge(names[record.kind], 'blue')}${pending(record)}${record.topic ? badge(record.topic) : ''}</div><p class="detail-summary">${recordSnippet(record)}</p><dl class="detail-list"><div><dt>记录日期</dt><dd>${fmtDate(record.date)}</dd></div><div><dt>科室</dt><dd>${escape(record.department || '未填写')}</dd></div>${Object.entries(record.data).filter(([key, value]) => labels[key] && value !== '' && value !== null).map(([key, value]) => `<div><dt>${labels[key]}</dt><dd class="preserve-lines">${escape(value)}</dd></div>`).join('')}<div><dt>来源说明</dt><dd>${escape(record.source_label || '手工录入，未说明来源')}</dd></div>${record.notes ? `<div><dt>补充记录</dt><dd class="preserve-lines">${escape(record.notes)}</dd></div>` : ''}</dl>${doc ? `<div class="source-detail">${icon('file')}<div><strong>${escape(doc.filename)}</strong><small>每次下载均校验 SHA-256，原件不被编辑覆盖</small></div>${button('下载原件', 'download-document', `data-id="${doc.id}"`, 'secondary small')}</div>` : alertBox('这条记录未附原件，请保留其他来源并补齐资料。')}<p class="page-note">记录版本 ${record.version} · 最近保存 ${escape(new Date(record.updated_at).toLocaleString('zh-CN', { hour12: false }))}</p></div><div class="modal-footer split">${button('删除记录', 'delete-record', `data-id="${record.id}"`, 'quiet danger-text')}${button('编辑记录', 'edit-record', `data-id="${record.id}"`, 'primary')}</div>`);
}
async function download(path, filename) { const blob = await request(path, { binary: true }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000); }
function mobileMenu() {
  if (!canLeave(mobileMenu)) return;
  render();
  openModal('全部功能', `<div class="modal-body more-navigation">${routes.map(([route, label, symbol]) => `<a href="#${route}">${icon(symbol)}${label}</a>`).join('')}</div>`);
}
function importMenu() {
  if (!canLeave(importMenu)) return;
  render();
  openModal('把资料留好', `<div class="modal-body"><p>选择一种方式。原件先保存在运行服务的电脑，不会自动发送给模型。</p><div class="import-options">${button(icon('camera') + '<strong>拍一张</strong><small>报告 / 处方 / 一餐</small>', 'pick-camera')}${button(icon('folder') + '<strong>从相册选</strong><small>JPG / PNG</small>', 'pick-album')}${button(icon('file') + '<strong>选文件</strong><small>PDF / 图片 / TXT</small>', 'pick-files')}${button(icon('plus') + '<strong>粘贴文字</strong><small>保存为文字原件</small>', 'paste-text')}</div><p class="page-note">单份 20 MB，每批最多 50 份。HEIC / HEIF 请先导出 JPG 并保留原图；不自动转换、裁剪或去除照片定位信息。</p><hr><h3>手机与电脑之间</h3><p>只手动互传原始资料（含 TXT 随记），不自动同步病历、科室确认、餐单或密钥。</p><div class="import-options">${button('导入手机资料包', 'transfer-import')}${button('导出给手机（未加密）', 'transfer-export')}</div><p><a class="text-link" href="/phone/" target="_blank" rel="noopener">在新窗口预览手机本地档案</a></p><small>手机实际使用需要单独部署 HTTPS 静态版；不能用手机访问电脑的 127.0.0.1。两个档案不会自动连通。</small></div>`);
}
async function uploadFiles(files) {
  if (!files.length || state.importBusy) return;
  if (files.length > 50) { toast('每次最多选择 50 份，请分批导入', true); return; }
  if (!openModal('导入进度', '<div class="modal-body"><p>每份独立保存。失败项可重试，已成功的不会回滚。</p><ul id="import-progress" class="import-progress" aria-live="polite"></ul></div><div class="modal-footer">' + button('关闭', 'close-modal') + '</div>')) return;
  state.importBusy = true;
  const progress = [], failed = [];
  let imported = 0, duplicates = 0;
  const update = () => { document.querySelector('#import-progress').innerHTML = progress.map(item => `<li><strong>${escape(item.name)}</strong><span>${escape(item.status)}</span></li>`).join(''); };
  try {
    for (const file of files) {
      const entry = { name: file.name, status: '正在保存…' }; progress.push(entry); update();
      try {
        if (!file.size || file.size > 20 * 1024 * 1024) throw new Error('为空或超过 20 MB');
        if (!/\.(pdf|png|jpe?g|txt)$/i.test(file.name)) throw new Error('仅支持 PDF / JPG / PNG / TXT；HEIC 请先导出为 JPG');
        const result = await request('/api/documents', { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' }, body: file });
        result.duplicate ? duplicates++ : imported++; entry.status = result.duplicate ? '内容已存在，未重复保存' : '已保存到电脑';
      } catch (error) { entry.status = '未保存：' + error.message; failed.push(file); }
      update();
    }
    state.failedImports = failed;
    if (failed.length) modal.querySelector('.modal-footer').insertAdjacentHTML('afterbegin', button('重试未保存项', 'retry-import'));
    await refresh();
    toast(`导入 ${imported} 份，重复 ${duplicates} 份，未保存 ${failed.length} 份`, failed.length > 0);
  } catch (error) { toast(error.message, true); }
  finally { state.importBusy = false; }
}
async function ask(question) { state.thinking = true; state.assistant = { question }; render(); try { state.assistant = await request('/api/assistant', { method: 'POST', json: { question, use_model: state.useModel } }); } catch (error) { state.assistant = null; toast(error.message, true); } finally { state.thinking = false; if (state.route === 'assistant') render(); } }
async function saveMeal(meal, changes, day = state.mealDate) { const plan = state.data.plans.find(item => item.date === day); await request('/api/plans/' + day, { method: 'PUT', json: { meal, revision: plan.revision, ...changes } }); await refresh(); }

document.addEventListener('click', async event => {
  if (event.target.closest('.skip-link')) { event.preventDefault(); document.querySelector('#main-content')?.focus(); document.querySelector('#main-content')?.scrollIntoView(); return; }
  const link = event.target.closest('a[href^="#"]');
  if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(link.getAttribute('href')); return; }
  const target = event.target.closest('[data-action]');
  if (!target || target.disabled) return;
  const action = target.dataset.action, id = target.dataset.id;
  if (state.importBusy) { toast('正在导入，请稍候'); return; }
  try {
    if (action === 'ai-task') navigate('assistant?task=' + target.dataset.task);
    else if (action === 'ai-engine') selectEngine(target.dataset.engine);
    else if (action === 'use-codex') selectEngine('codex', true);
    else if (action === 'codex-control') await codexControl(target.dataset.control);
    else if (action === 'codex-cancel') await cancelCodex();
    else if (action === 'start-breakfast') navigate('assistant?task=breakfast');
    else if (action === 'ai-upload') document.querySelector('#ai-upload').click();
    else if (action === 'clear-cloud-key') { await request('/api/ai/key', { method: 'DELETE' }); await refresh(); toast('内存密钥和未发送授权已清除；正在进行的请求无法撤回'); }
    else if (action === 'open-analysis' || action === 'open-food-entry') { const item = state.data.analyses.find(item => item.id === id); if (item) navigate('assistant?task=' + item.task + '&analysis=' + id); }
    else if (action === 'delete-analysis') { const item = state.data.analyses.find(item => item.id === id); confirmation('删除分析草稿？', '这会删除此草稿及关联的实际饮食备注，不会删除原件或正式病历。已发送到服务商的数据无法在此撤回。', async () => { await request('/api/analyses/' + id, { method: 'DELETE', json: { version: item.version } }); state.analysisId = ''; await refresh(); toast('草稿已删除'); }, '删除本地草稿'); }
    else if (action === 'actual-intake') { const item = state.data.analyses.find(item => item.id === id); openModal('核对实际饮食', `<form id="actual-intake-form" data-id="${id}" data-version="${item.version}"><div class="modal-body"><p>请自行填写实际发生的饮食，不预填模型识别结果。AI 草稿与本条自述始终分开。</p><div class="form-grid">${inputField('实际用餐日期', 'date', item.intake.date || state.data.today, 'date', `required max="${state.data.today}"`)}${selectField('餐次', 'meal', item.intake.meal || 'breakfast', [['breakfast', '早餐'], ['lunch', '午餐'], ['dinner', '晚餐'], ['snack', '加餐']])}${textArea('实际吃了什么、份量与配料', 'note', item.intake.note || '', 'required')}</div><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消', 'close-modal')}<button type="submit" class="button primary">保存实际饮食</button></div></form>`); modal.querySelector('[name="note"]').maxLength = 2000; }
    else if (action === 'open-specialty') { const index = state.data.departments.findIndex(item => item.name === target.dataset.name); const record = records().find(item => item.department === target.dataset.name); navigate('departments?' + (index >= 0 ? 'department=' + index : 'custom=' + encodeURIComponent(record?.id || ''))); }
    else if (action === 'close-specialty') navigate('departments');
    else if (action === 'specialty-group') { state.specialtyGroup = target.dataset.group; render(); }
    else if (action === 'specialty-add') { recordForm(); modal.querySelector('[name="department"]').value = state.specialty; }
    else if (action === 'open-inbox') { openModal('待分类与待核对资料', `<div class="modal-body">${state.data.documents.filter(doc => !doc.routing?.links.length || doc.routing.status !== 'confirmed').map(routingCard).join('') || '<p>没有待分类资料。</p>'}</div>`, 'record-modal'); }
    else if (action === 'route-document') routeModal(state.data.documents.find(doc => doc.id === id));
    else if (action === 'ai-route') { const item = state.data.analyses.find(item => item.id === id); routeModal(state.data.documents.find(doc => doc.id === item.document_id), item.result.departments); }
    else if (action === 'analyze-document') { const proceed = () => { selectTask('document'); state.aiDocument = id; state.aiText = ''; modal.close(); navigate('assistant?task=document'); }; if (canLeave(proceed)) proceed(); }
    else if (action === 'review-excerpt') { const item = state.data.analyses.find(item => item.id === id), entry = item.result.excerpts[Number(target.dataset.index)]; recordForm('observation', null, item.document_id || ''); modal.querySelector('[name="title"]').value = entry.title; modal.querySelector('[name="department"]').value = entry.department; modal.querySelector('[name="date"]').value = ''; modal.querySelector('[name="source_label"]').value = ('AI 摘录候选，须对照原件：' + entry.location).slice(0, 240); modal.querySelector('[name="notes"]').value = '待核对原文：' + entry.quote; }
    else if (action === 'close-modal') closeModal();
    else if (action === 'confirm') { const callback = state.confirmation; state.confirmation = null; modal.close(); if (callback) await callback(); }
    else if (action === 'add') recordForm(target.dataset.kind || 'visit');
    else if (action === 'detail') detail(id);
    else if (action === 'edit-record') recordForm(getRecord(id).kind, getRecord(id));
    else if (action === 'delete-record') { const record = getRecord(id); confirmation('删除这条记录？', `将删除“${record.title}”。关联原件不会删除。此操作不能撤销，建议先备份。`, async () => { await request('/api/records/' + id, { method: 'DELETE', json: { version: record.version } }); await refresh(); toast('记录已删除，原件保留'); }, '删除记录'); }
    else if (action === 'complete') { const record = getRecord(id); await request('/api/records/' + id, { method: 'PUT', json: { ...record, data: { ...record.data, done: true } } }); await refresh(); toast('已标记完成'); }
    else if (action === 'upload') importMenu();
    else if (action === 'mobile-more') mobileMenu();
    else if (action === 'pick-camera') document.querySelector('#camera-upload').click();
    else if (action === 'pick-album') document.querySelector('#album-upload').click();
    else if (action === 'pick-files') document.querySelector('#file-upload').click();
    else if (action === 'retry-import') await uploadFiles(state.failedImports || []);
    else if (action === 'paste-text') openModal('保存文字原件', `<form id="text-import-form"><div class="modal-body">${inputField('原件名称', 'filename', '', 'text', 'required maxlength="150"', '无需加 .txt 后缀')}${textArea('粘贴报告文字或写下个人记录', 'content', '', 'required')}<p>只存为 UTF-8 原件，不自动录入已核实病历。</p><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消', 'close-modal')}<button type="submit" class="button primary">保存文字原件</button></div></form>`);
    else if (action === 'transfer-import') document.querySelector('#transfer-upload').click();
    else if (action === 'transfer-export') confirmation('导出未加密的原件互传包？', '包含全部原始文件，不包含病历、餐单、科室确认或 Key。请在手机资料版“备份互传”导入。下载副本未加密，不要公开分享或上传 GitHub。', () => download('/api/transfer', '知己资料.hj-transfer.json'), '导出原件资料包');
    else if (action === 'extract-document') recordForm('observation', null, id);
    else if (action === 'download-document') { const doc = state.data.documents.find(item => item.id === id); await download('/api/documents/' + id, doc.filename); toast('原件已校验，下载已开始'); }
    else if (action === 'preview-document') { const doc = state.data.documents.find(item => item.id === id); const blob = await request('/api/documents/' + id, { binary: true }); const content = await blob.text(); if (!target.isConnected || modal.open) return; openModal(escape(doc.filename), `<div class="modal-body"><p class="page-note">原始文字，仅展示，不自动转换为已核实记录。</p><pre class="document-preview">${escape(content.slice(0, 150000))}</pre>${content.length > 150000 ? '<p>预览已截断，下载可查看完整文件。</p>' : ''}</div><div class="modal-footer">${button('摘录到记录', 'extract-document', `data-id="${id}"`, 'primary')}</div>`); }
    else if (action === 'delete-document') { const doc = state.data.documents.find(item => item.id === id); confirmation('移除原始资料？', `将移除“${doc.filename}”。如仍有关联记录，系统会拒绝删除。原件移除后只能从备份恢复。`, async () => { await request('/api/documents/' + id, { method: 'DELETE' }); await refresh(); toast('原始资料已移除'); }, '移除原件'); }
    else if (action === 'care-tab') navigate('care?tab=' + target.dataset.kind);
    else if (action === 'generate-plan') { target.disabled = true; await request('/api/plans', { method: 'POST', json: { date: state.mealDate } }); await refresh(); toast('餐单已保存，请再次核对配料'); }
    else if (action === 'swap-meal') { await saveMeal(target.dataset.meal, { swap: true }); toast('已替换，实际饮食记录未改变'); }
    else if (action === 'log-meal') { const meal = target.dataset.meal, plan = state.data.plans.find(item => item.date === state.mealDate), entry = plan.meals[meal]; openModal('记录实际饮食', `<form id="meal-log-form" data-meal="${meal}" data-date="${plan.date}" data-revision="${plan.revision}"><div class="modal-body">${textArea('实际吃了什么 / 份量 / 与计划的不同', 'note', entry.note)}<label class="check-label"><input type="checkbox" name="eaten" ${entry.eaten ? 'checked' : ''}>已用餐</label><p class="form-message" role="alert"></p></div><div class="modal-footer">${button('取消', 'close-modal')}<button class="button primary" type="submit">保存实际记录</button></div></form>`); modal.querySelector('[name="note"]').maxLength = 1000; }
    else if (action === 'shopping') { const plan = state.data.plans.find(item => item.date === state.mealDate); const ingredients = [...new Set(Object.values(plan.meals).flatMap(entry => state.data.recipes.find(item => item.id === entry.recipe_id).ingredients))]; openModal('这一天的采购清单', `<div class="modal-body"><p class="page-note">${fmtDate(state.mealDate)} · 份量为示例，调味料及包装配料另行核对。</p><div class="shopping-checks">${ingredients.map(item => `<label class="check-label"><input type="checkbox">${escape(item)}</label>`).join('')}</div><small>清单勾选仅本次查看有效，不改变餐单或用餐记录。</small></div>`); }
    else if (action === 'ask-example') { if (canLeave(() => ask(target.dataset.question))) await ask(target.dataset.question); }
    else if (action === 'print') window.print();
    else if (action === 'backup') confirmation('导出完整备份', 'ZIP 中包含个人资料、全部记录和原始附件，未加密。请只保存到自己控制的安全位置，不要上传 GitHub 或发送给无关人员。', async () => { await download('/api/backup', '健康手记备份-' + state.data.today + '.zip'); await refresh(); toast('完整备份下载已开始'); }, '导出到本机');
    else if (action === 'restore') document.querySelector('#restore-upload').click();
    else if (action === 'detect-model') { target.disabled = true; target.textContent = '检测中…'; const result = await request('/api/models'); state.models = result.models; render(); toast(result.models.length ? `找到 ${result.models.length} 个本机模型` : '服务已连接，尚未安装模型'); }
    else if (action === 'select-model') { const form = document.querySelector('#model-form'); form.querySelector('input[name="model"]').value = target.dataset.model; form.dataset.dirty = 'true'; }
  } catch (error) { toast(error.message, true); } finally { if (target.isConnected) { target.disabled = false; if (action === 'detect-model') target.textContent = '检测本机服务'; } }
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!['record-form', 'profile-form', 'assistant-form', 'model-form', 'meal-log-form', 'cloud-config-form', 'codex-config-form', 'cloud-analysis-form', 'cloud-consent-form', 'routing-form', 'actual-intake-form', 'text-import-form'].includes(form.id)) return;
  event.preventDefault();
  if (form.dataset.saving === 'true' || state.importBusy) return;
  const data = new FormData(form), message = form.querySelector('.form-message');
  const controls = [...form.querySelectorAll('input, textarea, select, button')].filter(control => !control.disabled);
  controls.forEach(control => { control.disabled = true; });
  form.dataset.saving = 'true';
  let succeeded = false;
  if (message) message.textContent = '';
  try {
    if (form.id === 'text-import-form') { const filename = String(data.get('filename')).trim().replace(/\.txt$/i, '') + '.txt'; const content = String(data.get('content')); if (!content.trim()) throw new Error('请填写文字内容'); await request('/api/documents', { method: 'POST', headers: { 'X-Filename': encodeURIComponent(filename), 'Content-Type': 'application/octet-stream' }, body: new Blob([content], { type: 'text/plain' }) }); modal.close(); await refresh(); toast('文字原件已保存在电脑'); }
    else if (form.id === 'cloud-config-form') { await request('/api/ai/config', { method: 'PUT', json: { provider: data.get('provider'), base_url: data.get('base_url'), model: data.get('model'), api_key: data.get('api_key'), vision: data.has('vision'), revision: form.dataset.revision } }); form.querySelector('[name="api_key"]').value = ''; await refresh(); toast('连接配置已保存，尚未外发任何资料；Key 仅在本次内存中'); }
    else if (form.id === 'cloud-analysis-form') await previewCloud(form, data);
    else if (form.id === 'codex-config-form') { await request('/api/codex/config', { method: 'PUT', json: { model: data.get('model'), vision: data.has('vision'), revision: form.dataset.revision } }); await refresh(false); toast('Codex 模型已保存，尚未发送健康资料'); }
    else if (form.id === 'cloud-consent-form') { if (data.has('consent')) await runCloud(form.dataset.approval, form.dataset.engine, form.dataset.task); }
    else if (form.id === 'routing-form') { await request('/api/documents/' + form.dataset.id + '/routing', { method: 'PUT', json: { version: Number(form.dataset.version), method: form.dataset.method, links: data.getAll('departments').map(name => ({ name, evidence: '用户核对原件后选择' })), status: 'confirmed' } }); modal.close(); await refresh(); toast('科室关联已确认；同一原件不会重复复制'); }
    else if (form.id === 'actual-intake-form') { await request('/api/analyses/' + form.dataset.id, { method: 'PUT', json: { date: data.get('date'), meal: data.get('meal'), note: data.get('note'), version: Number(form.dataset.version) } }); modal.close(); await refresh(); toast('已保存你核对过的实际饮食，AI 草稿仍单独保留'); }
    else if (form.id === 'record-form') {
      const kind = data.get('kind'), id = form.dataset.id;
      const payload = Object.fromEntries(data);
      for (const key of ['kind', 'title', 'date', 'department', 'topic', 'notes', 'source_label', 'document_id', 'verified']) delete payload[key];
      if (kind === 'symptom') payload.red_flags = data.has('red_flags');
      if (kind === 'reminder') payload.done = data.has('done');
      const record = { kind, title: data.get('title'), date: data.get('date'), department: data.get('department'), topic: data.get('topic'), notes: data.get('notes'), source_label: data.get('source_label'), document_id: data.get('document_id'), verification: data.has('verified') ? 'verified' : 'pending', data: payload, ...(id ? { version: Number(form.dataset.version) } : {}) };
      await request('/api/records' + (id ? '/' + id : ''), { method: id ? 'PUT' : 'POST', json: record }); modal.close(); await refresh(); toast('记录已保存，原件未被更改');
    } else if (form.id === 'profile-form') {
      const profile = { ...Object.fromEntries(data), allergies: [...data.getAll('allergies'), ...String(data.get('other_allergies') || '').split(/[、,，;；\n]/).map(item => item.trim()).filter(Boolean)], clinical_diet: data.has('clinical_diet'), diet_acknowledged: data.has('diet_acknowledged') };
      delete profile.other_allergies;
      await request('/api/profile', { method: 'PUT', json: { ...profile, _version: form.dataset.version } }); await refresh(); toast('档案设置已保存；旧餐单会重新检查适用性');
    } else if (form.id === 'assistant-form') await ask(data.get('question'));
    else if (form.id === 'model-form') { await request('/api/model', { method: 'PUT', json: { model: data.get('model') } }); await refresh(); toast('本机模型配置已保存，未发送任何医疗资料'); }
    else if (form.id === 'meal-log-form') { await saveMeal(form.dataset.meal, { revision: Number(form.dataset.revision), note: data.get('note'), eaten: data.has('eaten') }, form.dataset.date); modal.close(); toast('实际饮食记录已保存'); }
    succeeded = true;
  } catch (error) { if (message?.isConnected) message.textContent = error.message; else toast(error.message, true); }
  finally { delete form.dataset.saving; controls.forEach(control => { control.disabled = false; }); if (succeeded) { delete form.dataset.dirty; if (form.id !== 'cloud-analysis-form') render(); } }
});
document.addEventListener('input', event => { const form = event.target.closest('form'); if (form && !['cloud-consent-form', 'cloud-analysis-form'].includes(form.id)) form.dataset.dirty = 'true'; });
document.addEventListener('input', event => { if (event.target.id === 'record-search') { state.query = event.target.value; document.querySelector('#timeline-results').innerHTML = timelineResults(); } if (event.target.id === 'specialty-search') { state.specialtyQuery = event.target.value; document.querySelector('#specialty-results').innerHTML = specialtyFolders(); } if (event.target.closest('#cloud-analysis-form')) { const data = new FormData(event.target.closest('form')); state.aiText = String(data.get('text') || ''); state.aiDocument = String(data.get('document_id') || ''); state.aiProfile = data.has('include_profile'); state.aiRecords = data.has('include_records'); } });
document.addEventListener('change', async event => {
  const target = event.target;
  if (target.id === 'cloud-provider') { const preset = state.data.cloud.providers.find(item => item.id === target.value), base = document.querySelector('#cloud-base'); base.readOnly = target.value !== 'custom'; base.value = preset.base_url; document.querySelector('#cloud-config-form [name="api_key"]').value = ''; }
  if (target.id === 'specialty-has-data') { state.specialtiesWithData = target.checked; document.querySelector('#specialty-results').innerHTML = specialtyFolders(); }
  if (target.id === 'ai-upload') { const file = target.files[0]; target.value = ''; if (file) { try { if (file.size > 8 * 1024 * 1024) throw new Error('待分析附件最多 8 MB，请截取必要部分'); const doc = await request('/api/documents', { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' }, body: file }); state.aiDocument = doc.id; await refresh(); toast('资料已保存在本机，尚未发送给模型'); } catch (error) { toast(error.message, true); } } }
  if (target.id === 'kind-filter') state.kind = target.value;
  if (target.id === 'department-filter') state.department = target.value;
  if (target.id === 'topic-filter') state.topic = target.value;
  if (['kind-filter', 'department-filter', 'topic-filter'].includes(target.id)) document.querySelector('#timeline-results').innerHTML = timelineResults();
  if (target.id === 'series-select') { state.series = Number(target.value); render(); }
  if (target.id === 'meal-date') { state.mealDate = target.value || state.data.today; render(); }
  if (target.id === 'use-model') state.useModel = target.checked;
  if (target.id === 'kind-switch') { document.querySelector('#specific-fields').innerHTML = recordFields(target.value); const date = modal.querySelector('[name="date"]'); target.value === 'reminder' ? date.removeAttribute('max') : date.setAttribute('max', state.data.today); modal.querySelector('[name="title"]').previousElementSibling.textContent = target.value === 'observation' ? '指标原名 *' : target.value === 'medication' ? '药物名称 *' : '标题 *'; }
  if (['file-upload', 'camera-upload', 'album-upload'].includes(target.id)) { const files = [...target.files]; target.value = ''; await uploadFiles(files); }
  if (target.id === 'transfer-upload') { const file = target.files[0]; target.value = ''; if (file) { if (file.size > 58 * 1024 * 1024) { toast('资料包超过 58 MB', true); return; } confirmation('只新增原件，不覆盖其他资料', '这不是完整病历同步。资料包会先整体校验，再在一个事务中新增原件；重复内容保留电脑原有名称与分类。不会传播删除。', async () => { state.importBusy = true; try { const result = await request('/api/transfer', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Confirm-Transfer': 'append-originals' }, body: file }); await refresh(); toast(`新增 ${result.imported} 份，跳过重复 ${result.duplicates} 份`); } finally { state.importBusy = false; } }, '校验并新增原件'); } }
  if (target.id === 'restore-upload') { const file = target.files[0]; target.value = ''; if (file) confirmation('恢复完整备份到空档案', '系统将检查文件结构、原件哈希和记录引用。仅允许恢复到全新空档案，不会覆盖已有资料。请确认备份来自可信的个人副本。', async () => { const result = await request('/api/restore', { method: 'POST', headers: { 'Content-Type': 'application/zip', 'X-Confirm-Restore': 'empty-vault' }, body: file }); await refresh(); toast(`已恢复 ${result.records} 条记录、${result.documents} 份原件`); }, '校验并恢复'); }
});
document.addEventListener('dragover', event => { const zone = event.target.closest('#upload-zone'); if (zone) { event.preventDefault(); zone.classList.add('dragging'); } });
document.addEventListener('dragleave', event => event.target.closest('#upload-zone')?.classList.remove('dragging'));
document.addEventListener('drop', async event => { const zone = event.target.closest('#upload-zone'); if (zone) { event.preventDefault(); zone.classList.remove('dragging'); await uploadFiles([...event.dataTransfer.files]); } });
window.addEventListener('hashchange', () => { const destination = location.hash; if (!canLeave(() => navigate(destination))) { history.replaceState(null, '', state.locationHash || '#home'); return; } if (modal.open) modal.close(); render(); window.scrollTo(0, 0); document.querySelector('#main-content')?.focus({ preventScroll: true }); });
window.addEventListener('beforeunload', event => { if (dirtyForms().length || document.querySelector('#app form[data-saving="true"], dialog[open] form[data-saving="true"]') || state.aiBusy || state.importBusy) { event.preventDefault(); event.returnValue = ''; } });
modal.addEventListener('cancel', event => { event.preventDefault(); closeModal(); });
modal.addEventListener('click', event => { if (event.target === modal) { const bounds = modal.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeModal(); } });
document.querySelector('#leave-cancel').addEventListener('click', () => { leaveModal.close(); state.leaveCallback = null; });
document.querySelector('#leave-confirm').addEventListener('click', () => { const callback = state.leaveCallback; state.leaveCallback = null; leaveModal.close(); if (callback) callback(); });
leaveModal.addEventListener('cancel', () => { state.leaveCallback = null; });
refresh().catch(error => { root.innerHTML = `<div class="loading-screen"><h1>暂时无法打开档案</h1><p>${escape(error.message)}</p><p>确认本地服务仍在运行，然后刷新页面。不要删除资料目录。</p></div>`; });
