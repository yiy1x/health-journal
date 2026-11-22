'use strict';
const core = PhoneVaultCore, storage = PhoneVaultDB;
const app = document.querySelector('#app'), sheet = document.querySelector('#sheet');
const state = { row: null, key: null, salt: null, documents: [], catalog: [], route: 'capture', busy: false, query: '', department: '', queue: [], pending: null, dirty: false, offlineReady: false, lastActive: Date.now() };
const glyphs = { camera: '<rect x="3" y="7" width="18" height="14" rx="3"/><path d="m7 7 2-4h6l2 4"/><circle cx="12" cy="14" r="4"/>', files: '<path d="M4 4h7l3 4h6v13H4zM8 13h8M8 17h5"/>', lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>', note: '<path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h5"/>', album: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="2"/><path d="m3 18 6-6 4 4 4-5 4 5"/>', close: '<path d="m6 6 12 12M6 18 18 6"/>', sync: '<path d="M4 8h15l-4-4M20 16H5l4 4"/>', check: '<path d="m5 12 4 4L19 6"/>' };
function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyphs[name] || glyphs.files}</svg>`; }
function escape(value) { return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]); }
function today() { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
function bytesLabel(size) { return size < 1048576 ? (size / 1024).toFixed(1) + ' KB' : (size / 1048576).toFixed(1) + ' MB'; }
function sizeOf(item) { return item.content.length / 4 * 3 - (item.content.endsWith('==') ? 2 : item.content.endsWith('=') ? 1 : 0); }
function button(label, action, type = '', extra = '') { return `<button type="button" class="${type}" data-action="${action}" ${extra}>${label}</button>`; }
let noticeTimer, activityTimer, sheetURLs = [];
function notice(message) { const element = document.querySelector('#notice'); element.textContent = message; element.className = 'visible'; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { element.className = ''; element.textContent = ''; }, 9000); }
function render() {
  if (!state.key) { lockedView(); return; }
  const route = ['capture', 'library', 'backup'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'capture';
  state.route = route;
  const title = { capture: '随手记下，安心留好', library: '随身资料夹', backup: '备份与互传' }[route];
  app.innerHTML = `<header class="masthead"><a href="#capture" class="brand"><span>知己</span><small>随身手记</small></a>${button(icon('lock') + '<span>锁定</span>', 'lock', 'quiet')}</header><main id="main" tabindex="-1"><div class="local-line"><span class="dot"></span> 此浏览器加密保存 · 不自动上传</div><h1>${title}</h1>${route === 'capture' ? captureView() : route === 'library' ? libraryView() : backupView()}</main><nav class="bottom-nav" aria-label="主要导航">${[['capture', '记一笔', 'camera'], ['library', '资料夹', 'files'], ['backup', '备份互传', 'sync']].map(([path, label, symbol]) => `<a href="#${path}" ${route === path ? 'aria-current="page"' : ''}>${icon(symbol)}<span>${label}</span></a>`).join('')}</nav>`;
  document.title = title + ' · 知己';
}
function lockedView() {
  const existing = Boolean(state.row);
  app.innerHTML = `<main id="main" class="locked"><div class="lock-brand">${icon('note')}</div><p class="wordmark">知己 · 随身手记</p><h1>${existing ? '打开你的资料夹' : '把手记留在自己手里'}</h1><p>${existing ? '输入本设备档案密码。密码和解密密钥只在当前页面内存中。' : '拍一张报告，记一顿早餐。先设置一个长密码，原件与文字会加密保存在此浏览器。'}</p><form id="unlock-form"><label>档案密码<input type="password" name="password" minlength="12" maxlength="256" autocomplete="${existing ? 'current-password' : 'new-password'}" required></label>${existing ? '' : '<label>再次输入密码<input type="password" name="repeat" minlength="12" maxlength="256" autocomplete="new-password" required></label><label class="checkbox"><input type="checkbox" name="acknowledge" required>我知道忘记密码无法找回；清理浏览器可能丢失资料，需要另存备份。</label>'}<p class="error" role="alert"></p><button type="submit" class="primary wide">${existing ? '解锁本地档案' : '创建手机档案'}</button></form><div class="quiet-note">不会创建云端账号。请用 Safari 或 Chrome 普通模式，不要把本应用当作医疗急救、诊断或唯一备份。首次打开需要网络，离线可用状态见备份页。</div><p class="version">手机资料版 1.2.1 · 开发预览</p></main>`;
}
function captureView() {
  return `<p class="intro">先留住原件，整理可以慢慢来。</p><button class="capture-main" data-action="camera">${icon('camera')}<strong>拍一张</strong><span>报告、处方，或今天的一餐</span></button><div class="import-choices">${button(icon('album') + '<strong>从相册选</strong><span>已有照片</span>', 'album')}${button(icon('files') + '<strong>选文件</strong><span>PDF / 图片 / TXT</span>', 'files')}${button(icon('note') + '<strong>写几句</strong><span>症状 / 饮食 / 随记</span>', 'note')}</div><p class="hint">拍摄后先预览，再保存。多页报告可连续拍摄，原图各存一份；不自动裁剪、识字或诊断。</p><section class="section-head"><h2>最近留存</h2><a href="#library">全部 ${state.documents.length} 份</a></section>${state.documents.length ? cards(state.documents.slice(-3).reverse()) : '<div class="empty"><span class="paper-line"></span><h3>这里会慢慢装满你的记录</h3><p>不必一次整理完。先拍下手边的一份报告。</p></div>'}<p class="safety">突发胸痛、严重呼吸困难等紧急情况，请立即联系当地急救（中国大陆 120），不要等待本应用判断。</p>`;
}
function cards(documents) {
  return `<div class="document-list">${documents.map(item => { const departments = core.suggest(item, state.catalog); return `<button class="document-row" data-action="view" data-id="${item.sha256}"><span class="file-mark">${icon(item.mime.startsWith('image/') ? 'album' : 'note')}</span><span class="document-copy"><strong>${escape(item.filename)}</strong><small>${bytesLabel(sizeOf(item))} · ${departments.length ? escape(departments.slice(0, 2).join(' / ')) + '（待核对）' : '未分类'}</small></span><span aria-hidden="true">›</span></button>`; }).join('')}</div>`;
}
function libraryResults() {
  const query = state.query.trim().toLowerCase();
  const documents = state.documents.filter(item => (!query || (item.filename + (item.mime === 'text/plain' ? new TextDecoder().decode(core.unbase64(item.content, core.MAX_FILE)) : '')).toLowerCase().includes(query)) && (!state.department || core.suggest(item, state.catalog).includes(state.department))).slice().reverse();
  return documents.length ? cards(documents) : '<div class="empty"><h3>还没有匹配的资料</h3><p>试试其他文件名，或回到“记一笔”添加。</p></div>';
}
function libraryView() {
  return `<p class="intro">原件不改写，文字不自动变成诊断。</p><label>搜索文件名 / 文字内容<input id="search" type="search" value="${escape(state.query)}" placeholder="例如：体检、早餐、牙齿"></label><label>科室关键词分类<select id="department"><option value="">全部资料</option>${state.catalog.map(item => `<option ${state.department === item.name ? 'selected' : ''}>${escape(item.name)}</option>`).join('')}</select></label><p class="hint">55 科目录按文件名及文字关键词建议，图片尚未识字；可能漏分或错分，不是分诊。写随记时可注明科室。</p><div id="results">${libraryResults()}</div>`;
}
function backupView() {
  const total = state.documents.reduce((sum, item) => sum + sizeOf(item), 0);
  return `<p class="intro">每台设备自己保存。你决定何时带走、何时合并。</p><section class="storage-summary"><span>${icon('lock')}</span><div><h2>这份档案在当前浏览器里</h2><p>${state.documents.length} 份原件 · ${bytesLabel(total)} / 40 MB</p><small id="offline-state">${state.offlineReady ? '离线页面已缓存；建议断网试开一次' : '离线页面尚未确认就绪，请保持联网'}</small></div></section><section class="backup-section"><h2>先留一份加密备份</h2><p>用于手机换机或手机之间手动合并。导入时校验全部原件，只新增、不覆盖，不传播删除。</p>${button('导出加密备份', 'backup', 'primary wide')}${button('导入 / 合并加密备份', 'sealed', 'wide')}<p class="hint">备份使用导出设备的档案密码。换机前请先实际试解密；密码丢失没有找回入口。</p></section><section class="backup-section"><h2>手机 ↔ 电脑：原件互传</h2><p>电脑端“原始资料 → 导入资料”中也有互传入口。只传照片、PDF、TXT（含手机随记），不传桌面病历、餐单、科室确认状态或 API Key。</p>${button('导出给电脑（未加密）', 'export-transfer', 'wide')}${button('导入电脑资料包', 'exchange', 'wide')}<p class="hint">这不是自动同步。互传文件有明文健康资料，请通过自己控制的方式传递；导入后原件按 SHA-256 去重。同名不同内容两份都保留。</p></section><section class="backup-section"><h2>别把本地当作永不丢失</h2><p>清理站点数据、卸载浏览器、系统回收空间或切换网址，可能让资料不可见或丢失。安装到主屏幕也不能代替备份。</p>${button('请求浏览器保留本地存储', 'persist', 'wide')}<p id="persist-state" class="hint" role="status"></p><details><summary>手机安装与模型分析</summary><p>手机请打开由自己或可信维护者部署的 HTTPS 静态站点，然后通过浏览器菜单“添加到主屏幕”。电脑的 127.0.0.1 不是手机地址。不要把电脑服务开放到公网。</p><p>本版手机端不连接模型、不保存 API Key。可将必要原件互传到桌面，再逐次授权分析。没有后台同步、家庭共享或手机临床指标编辑功能。</p></details></section><p class="version">资料版 1.2.1 · 5 分钟无操作后锁定；锁屏不等于清除系统内存。</p>`;
}
function showSheet(title, body) {
  closeSheet(true);
  sheet.innerHTML = `<div class="sheet-head"><h2 id="sheet-title">${escape(title)}</h2>${button(icon('close'), 'close', 'quiet', 'aria-label="关闭"')}</div>${body}`;
  sheet.showModal();
}
function closeSheet(force = false) {
  if (!force && state.busy) { notice('正在保存，请稍候'); return; }
  if (!force && state.dirty) {
    let warning = sheet.querySelector('#discard-warning');
    if (!warning) { warning = document.createElement('div'); warning.id = 'discard-warning'; warning.className = 'discard-warning'; warning.innerHTML = `<p>输入未保存。要放弃这次随记吗？</p>${button('继续编辑', 'keep')}${button('放弃输入', 'discard', 'danger')}`; sheet.append(warning); }
    warning.querySelector('button').focus(); return;
  }
  sheet.close(); sheet.innerHTML = ''; state.dirty = false; state.pending = null; state.queue = [];
  sheetURLs.forEach(url => URL.revokeObjectURL(url)); sheetURLs = [];
}
function lock() {
  if (state.busy) { notice('正在处理，请完成后锁定'); return; }
  closeSheet(true); state.key = null; state.salt = null; state.documents = []; state.query = ''; state.department = '';
  clearTimeout(noticeTimer); document.querySelector('#notice').textContent = ''; document.querySelector('#notice').className = '';
  render();
}
async function busy(task) {
  if (state.busy) return;
  state.busy = true;
  const controls = [...document.querySelectorAll('button, input, select, textarea')].filter(control => !control.disabled);
  controls.forEach(control => { control.disabled = true; });
  app.setAttribute('aria-busy', 'true');
  try { await task(); }
  catch (error) { const message = sheet.querySelector('.error') || app.querySelector('.error'); if (message) message.textContent = error.message; notice(error.message); }
  finally { state.busy = false; controls.forEach(control => { control.disabled = false; }); app.removeAttribute('aria-busy'); state.lastActive = Date.now(); }
}
async function save(documents) {
  const envelope = await core.seal(documents, state.key, state.salt);
  const revision = await storage.write(envelope, state.row?.revision || null);
  state.row = { revision, envelope }; state.documents = documents;
}
function download(blob, name, encrypted = false) {
  showSheet('文件已准备好', `<p>${encrypted ? '这是加密副本，需要导出设备的档案密码才能打开。' : '这是未加密副本，文件系统、接收方及其备份可能保留内容。'}</p><p>点击保存文件。请确认浏览器或系统“文件”中已保存成功，再关闭此窗口；仅看到本提示不代表备份完成。</p><a id="save-file" class="download-link" download="${escape(name)}">保存文件</a><p class="hint">如内置浏览器不支持下载，请换用 Safari / Chrome 独立浏览器。不要清理当前站点数据。</p>`);
  const url = URL.createObjectURL(blob); sheetURLs.push(url); document.querySelector('#save-file').href = url;
}
function confirmation(title, text, action) { showSheet(title, `<p>${escape(text)}</p><div class="sheet-actions">${button('取消', 'close')}${button('我已了解，继续', action, 'primary')}</div>`); }
function prepareFiles(files) {
  if (!files.length) return;
  if (files.length > 50) { notice('每次最多选择 50 份，请分批导入'); return; }
  showSheet(files.length === 1 ? '留好这份原件' : `留好这 ${files.length} 份原件`, `<p>只保存在当前设备，不发给模型。不处理 HEIC，不去除照片定位信息；请先核对敏感内容。</p><div id="photo-preview"></div><ul class="queue" id="queue"></ul><p class="error" role="alert"></p><div class="sheet-actions">${button('取消', 'close')}${button('保存到手机', 'save-files', 'primary')}</div>`);
  state.queue = files.map(file => ({ file, status: '等待保存', done: false }));
  updateQueue();
  if (files.length === 1 && ['image/jpeg', 'image/png'].includes(files[0].type) && files[0].size <= core.MAX_FILE) {
    const url = URL.createObjectURL(files[0]); sheetURLs.push(url);
    document.querySelector('#photo-preview').innerHTML = `<img class="preview" src="${url}" alt="待保存照片预览">`;
  }
}
function updateQueue() { const list = document.querySelector('#queue'); if (list) list.innerHTML = state.queue.map(item => `<li><strong>${escape(item.file.name)}</strong><span>${escape(item.status)}</span></li>`).join(''); }
async function saveFiles() {
  for (const entry of state.queue.filter(item => !item.done)) {
    entry.status = '正在加密保存…'; updateQueue();
    try {
      if (entry.file.size > core.MAX_FILE) throw new Error('超过 20 MB，请选择较小原件');
      const name = entry.file.name.trim().replace(/[\u0000-\u001f\u007f-\u009f\ufeff/\\<>:"|?*]/g, '_').replace(/^\.+/, '_');
      const item = await core.makeDocument(name, new Uint8Array(await entry.file.arrayBuffer()));
      const merged = core.merge(state.documents, [item]);
      if (merged.added) await save(merged.documents);
      entry.status = merged.added ? '已加密保存' : '内容已存在，未重复保存'; entry.done = true;
    } catch (error) { entry.status = '未保存：' + error.message; }
    updateQueue();
  }
  const remaining = state.queue.filter(item => !item.done).length;
  sheet.querySelector('[data-action="save-files"]').textContent = remaining ? '重试未保存项' : '全部处理完成';
  sheet.querySelector('[data-action="save-files"]').dataset.action = remaining ? 'save-files' : 'close';
  render(); notice(remaining ? `有 ${remaining} 份未保存，详情见列表；其余已留存` : '资料已留在本地，未上传云端');
}
function noteForm() {
  showSheet('写下此刻的情况', `<form id="note-form"><label>标题<input name="title" maxlength="100" required placeholder="例如：今天的早餐、牙科复查"></label><div class="form-pair"><label>记录日期<input name="date" type="date" value="${today()}" min="1900-01-01" max="${today()}" required></label><label>类别<select name="kind"><option>日常随记</option><option>实际饮食</option><option>症状自述</option><option>就诊转述</option></select></label></div><label>科室（可不选）<select name="department"><option value="">暂不分类</option>${state.catalog.map(item => `<option>${escape(item.name)}</option>`).join('')}</select></label><label>想记下什么<textarea name="content" rows="6" maxlength="12000" required placeholder="吃了什么、何时不舒服、报告上怎么写……请区分自己的感受与医生的原话。"></textarea></label><p class="hint">以 UTF-8 文字原件留存，不是已核实病历。不会推断患病概率、给出处方或治疗饮食。</p><p class="error" role="alert"></p><button class="primary wide" type="submit">保存这次随记</button></form>`);
}
function viewDocument(id) {
  const item = state.documents.find(document => document.sha256 === id);
  if (!item) return;
  showSheet(item.filename, `<p class="hint">原件 ${bytesLabel(sizeOf(item))} · SHA-256 校验标识</p><code class="digest">${item.sha256}</code><div id="document-preview"></div><p class="hint">内容是个人保存的原始材料，不代表已核实、确诊或医学影像判读。</p><div class="sheet-actions">${button('下载原件（未加密）', 'download', '', `data-id="${id}"`)}${button('仅从本设备移除', 'delete', 'danger', `data-id="${id}"`)}</div>`);
  if (item.mime === 'text/plain') document.querySelector('#document-preview').innerHTML = `<pre>${escape(new TextDecoder().decode(core.unbase64(item.content, core.MAX_FILE)).slice(0, 100000))}</pre>${sizeOf(item) > 100000 ? '<p class="hint">长文字预览可能截断，请下载完整原件。</p>' : ''}`;
  else if (item.mime.startsWith('image/')) { const url = URL.createObjectURL(new Blob([core.unbase64(item.content, core.MAX_FILE)], { type: item.mime })); sheetURLs.push(url); document.querySelector('#document-preview').innerHTML = `<img class="preview" src="${url}" alt="已保存原件预览">`; }
  else document.querySelector('#document-preview').innerHTML = '<p>PDF 为安全起见不嵌入网页执行。请下载后用系统 PDF 阅读器打开。</p>';
}
async function prepareTransfer(file) {
  if (file.size > core.MAX_TRANSFER) throw new Error('互传文件超过 58 MB');
  const incoming = await core.validate(JSON.parse(await file.text()));
  const result = core.merge(state.documents, incoming);
  confirmation('核对后再合并', `将新增 ${result.added} 份；重复 ${result.duplicates} 份，其中 ${result.renamed} 份名称不同但内容相同（保留本地名称）。不会覆盖原件或传播删除。`, 'merge-transfer');
  state.pending = incoming;
}
document.addEventListener('click', event => {
  const anchor = event.target.closest('a[href^="#"]');
  if (anchor && state.busy) { event.preventDefault(); notice('正在处理，请稍候'); return; }
  const target = event.target.closest('[data-action]');
  if (!target || target.disabled || state.busy) return;
  const action = target.dataset.action, id = target.dataset.id;
  if (['camera', 'album', 'files', 'exchange', 'sealed'].includes(action)) { document.querySelector('#' + action).click(); return; }
  if (action === 'close') { closeSheet(); return; }
  if (action === 'keep') { document.querySelector('#discard-warning')?.remove(); sheet.querySelector('textarea')?.focus(); return; }
  if (action === 'discard') { closeSheet(true); return; }
  if (action === 'lock') { lock(); return; }
  if (action === 'note') { noteForm(); return; }
  if (action === 'view') { viewDocument(id); return; }
  if (action === 'export-transfer') { confirmation('导出未加密的资料包？', '包含全部原始文件和文字，下载文件不受本应用密码保护。只通过可信渠道传递；不要提交 GitHub、公开网盘或聊天群。', 'confirm-transfer'); return; }
  if (action === 'download') { confirmation('导出未加密的原件？', '文件和照片定位等元数据会进入系统下载位置，本应用密码不保护这份副本。请自行保管。', 'confirm-download'); state.pending = id; return; }
  if (action === 'delete') { confirmation('仅从本设备移除？', '操作不能撤销；其他设备、已导出的副本和相册不会删除。再次导入旧备份会带回这份文件。', 'confirm-delete'); state.pending = id; return; }
  busy(async () => {
    if (action === 'save-files') await saveFiles();
    else if (action === 'backup') { const envelope = await core.seal(state.documents, state.key, state.salt); download(new Blob([JSON.stringify(envelope)], { type: 'application/json' }), '知己加密备份-' + today() + '.hjvault', true); }
    else if (action === 'confirm-transfer') download(new Blob([JSON.stringify(core.pack(state.documents))], { type: 'application/json' }), '知己资料.hj-transfer.json');
    else if (action === 'merge-transfer') { const merged = core.merge(state.documents, state.pending); if (merged.added) await save(merged.documents); closeSheet(true); render(); notice(`已新增 ${merged.added} 份，重复 ${merged.duplicates} 份，原资料未覆盖`); }
    else if (action === 'confirm-download') { const item = state.documents.find(document => document.sha256 === state.pending); if (!item) throw new Error('原件已不存在'); download(new Blob([core.unbase64(item.content, core.MAX_FILE)], { type: item.mime }), item.filename); }
    else if (action === 'confirm-delete') { await save(state.documents.filter(item => item.sha256 !== state.pending)); closeSheet(true); render(); notice('已从此浏览器移除；其他设备和备份不受影响'); }
    else if (action === 'persist') { const result = await navigator.storage?.persist?.(); document.querySelector('#persist-state').textContent = result ? '浏览器已同意持久存储；用户清理或设备丢失仍会丢数据，仍需备份。' : '浏览器未同意或不支持此请求。请务必另存加密备份。'; }
  });
});
document.addEventListener('submit', event => {
  event.preventDefault();
  const form = event.target;
  if (state.busy) return;
  const data = new FormData(form);
  busy(async () => {
    if (form.id === 'unlock-form') {
      const password = String(data.get('password'));
      let renamed = 0;
      core.passwordCheck(password);
      state.row = await storage.read();
      if (state.row) { const opened = await core.open(state.row.envelope, password); state.key = opened.key; state.salt = opened.salt; state.documents = opened.documents; renamed = opened.renamed || 0; }
      else {
        if (data.get('repeat') !== password || !data.has('acknowledge')) throw new Error('两次密码必须一致，并确认备份提示');
        const salt = crypto.getRandomValues(new Uint8Array(16)), key = await core.derive(password, salt);
        const envelope = await core.seal([], key, salt), revision = await storage.write(envelope, null);
        state.row = { revision, envelope }; state.key = key; state.salt = salt; state.documents = [];
      }
      form.reset(); render(); notice(renamed ? `已解锁；兼容整理 ${renamed} 个旧版文件名，原件字节未改变。请另存新版备份` : '已解锁当前设备档案');
    } else if (form.id === 'note-form') {
      const date = String(data.get('date')), title = String(data.get('title')).trim(), content = String(data.get('content')).trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < '1900-01-01' || date > today() || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date || !title || !content || content.length > 12000 || /\0|[\uD800-\uDFFF]/u.test(title + content)) throw new Error('请填写有效标题、日期和文字；不记录未来已发生的情况');
      const department = String(data.get('department'));
      const text = `${title}\n记录日期：${date}\n类别：${data.get('kind')}\n科室：${department || '未选择'}\n来源：个人自述 / 转述，未经临床核实；不代表诊断\n\n${content}\n`;
      const name = `${date}-${title.replace(/[\u0000-\u001f\u007f-\u009f\ufeff/\\<>:"|?*]/g, '_').slice(0, 100)}.txt`;
      const item = await core.makeDocument(name, new TextEncoder().encode(text));
      const merged = core.merge(state.documents, [item]); if (merged.added) await save(merged.documents);
      closeSheet(true); render(); notice(merged.added ? '随记已加密保存在手机' : '相同随记已存在，未重复保存');
    } else if (form.id === 'restore-form') {
      const opened = await core.open(state.pending, String(data.get('password')));
      form.reset();
      const merged = core.merge(state.documents, opened.documents);
      confirmation('合并备份，不覆盖本地', `备份校验成功。将新增 ${merged.added} 份，跳过重复 ${merged.duplicates} 份；${merged.renamed} 份内容相同但名称不同，保留本地名称。兼容整理 ${opened.renamed || 0} 个旧版文件名，原件字节未改变。删除不会传播，本机仍使用当前密码。`, 'merge-transfer');
      state.pending = opened.documents;
    }
  });
});
document.addEventListener('change', event => {
  const input = event.target;
  if (input.id === 'department') { state.department = input.value; document.querySelector('#results').innerHTML = libraryResults(); return; }
  if (input.type !== 'file') return;
  const files = [...input.files]; input.value = '';
  if (!files.length || state.busy || !state.key) return;
  if (['camera', 'album', 'files'].includes(input.id)) { prepareFiles(files); return; }
  busy(async () => {
    if (input.id === 'exchange') await prepareTransfer(files[0]);
    else if (input.id === 'sealed') {
      if (files[0].size > core.MAX_SEALED) throw new Error('加密文件超过 80 MB');
      const envelope = JSON.parse(await files[0].text());
      showSheet('输入备份文件的密码', '<p>导入后仍使用此设备当前密码。不会覆盖已有原件。</p><form id="restore-form"><label>备份密码<input name="password" type="password" minlength="12" maxlength="256" autocomplete="off" required></label><p class="error" role="alert"></p><button class="primary wide" type="submit">解密并预览合并数量</button></form>'); state.pending = envelope;
    }
  });
});
document.addEventListener('input', event => { if (event.target.id === 'search') { state.query = event.target.value; document.querySelector('#results').innerHTML = libraryResults(); } if (event.target.closest('#note-form')) state.dirty = true; });
sheet.addEventListener('cancel', event => { event.preventDefault(); closeSheet(); });
window.addEventListener('hashchange', () => { if (!state.key) return; if (state.busy || sheet.open) { history.replaceState(null, '', '#' + state.route); notice('请先完成或关闭当前操作'); return; } render(); window.scrollTo(0, 0); document.querySelector('#main')?.focus({ preventScroll: true }); });
window.addEventListener('beforeunload', event => { if (state.busy || state.dirty || state.pending || state.queue.some(item => !item.done)) { event.preventDefault(); event.returnValue = ''; } });
for (const event of ['pointerdown', 'keydown', 'input']) document.addEventListener(event, () => { state.lastActive = Date.now(); }, { passive: true });
function checkLock() { if (state.key && !state.busy && Date.now() - state.lastActive >= 5 * 60000) lock(); }
document.addEventListener('visibilitychange', checkLock);
window.addEventListener('pageshow', checkLock);
activityTimer = setInterval(checkLock, 15000);
async function start() {
  if (!window.isSecureContext || !crypto.subtle || !window.indexedDB) throw new Error('需要可信 HTTPS 来源、Web Crypto 和 IndexedDB；不要使用无痕模式。电脑本机预览可用 localhost。');
  state.row = await storage.read();
  const response = await fetch('./catalog.json', { cache: 'no-cache' });
  if (!response.ok) throw new Error('科室目录加载失败，请联网重试');
  const catalog = await response.json();
  if (!Array.isArray(catalog) || catalog.length !== 55 || catalog.some(item => typeof item.name !== 'string' || !Array.isArray(item.keywords))) throw new Error('科室目录格式无效');
  state.catalog = catalog;
  render();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js', { scope: './', updateViaCache: 'none' }).then(() => navigator.serviceWorker.ready).then(() => { state.offlineReady = true; const element = document.querySelector('#offline-state'); if (element) element.textContent = '离线页面已缓存；建议断网试开一次'; }).catch(() => { notice('离线页面缓存未成功，资料仍在本地；请保持联网并备份'); });
  }
}
start().catch(error => { app.innerHTML = `<main id="main"><h1>暂时无法打开手机档案</h1><p>${escape(error.message)}</p><p>不要清理站点数据。请确认 HTTPS、浏览器存储权限和剩余空间后重新打开。</p></main>`; });
