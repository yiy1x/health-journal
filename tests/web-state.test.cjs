const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/app.js'), 'utf8');
const fixture = {
  today: '2026-11-13', version: '1.1.1', records: [], documents: [], plans: [], analyses: [], departments: [],
  profile_version: 'initial-version', profile: { name: '合成', birth_date: '', sex: 'unspecified', allergies: [], diet: 'balanced', clinical_diet: false, diet_notes: '', diet_acknowledged: true, emergency_contact: '', notes: '' },
  allergens: [], nutrition_restrictions: [], recipes: [], audits: [], model: '', demo: false,
  nutrition_notice: '合成', safety: '合成测试', data_directory: '/synthetic',
};

function harness() {
  const listeners = {}, windowListeners = {}, modalListeners = {}, requests = [];
  const root = { innerHTML: '' }, toast = {}, dirty = [];
  let saving = null;
  const modal = { open: false, innerHTML: '', querySelector: () => null, close() { this.open = false; }, showModal() { this.open = true; }, addEventListener(name, callback) { modalListeners[name] = callback; } };
  const leaveListeners = {};
  const leaveModal = { ...modal, addEventListener(name, callback) { leaveListeners[name] = callback; } };
  const location = { hash: '#home' };
  const context = vm.createContext({
    URL, URLSearchParams, console, location,
    history: { replaceState(data, title, hash) { location.hash = hash; } },
    setTimeout: () => 1, clearTimeout() {},
    document: {
      querySelector(selector) {
        if (selector === '#app') return root;
        if (selector === '#modal') return modal;
        if (selector === '#leave-modal') return leaveModal;
        if (selector === '#leave-message') return {};
        if (selector === '#leave-cancel' || selector === '#leave-confirm') return { addEventListener(name, callback) { leaveListeners[selector] = callback; } };
        if (selector.includes('meta[')) return { content: 'synthetic' };
        if (selector === '#toast') return toast;
        if (selector.includes('data-saving')) return saving;
        if (selector === '.sidebar nav') return { querySelector: () => ({}), scrollWidth: 0, clientWidth: 1 };
        return null;
      },
      querySelectorAll: () => dirty.filter(form => form.dataset.dirty === 'true'),
      addEventListener(name, callback) { (listeners[name] ||= []).push(callback); },
    },
    window: { addEventListener(name, callback) { windowListeners[name] = callback; }, scrollTo() {} },
    FormData: class extends URLSearchParams { constructor(form) { super(form.controls.some(control => control.disabled) ? [] : form.fields); } },
    fetch: (url, options) => new Promise(resolve => { requests.push({ url, options, resolve: body => resolve({ ok: true, json: async () => body }) }); }),
  });
  const run = expression => vm.runInContext(expression, context);
  vm.runInContext(source, context);
  run(`state.data=${JSON.stringify(fixture)}`);
  requests.shift();
  return { run, context, root, modal, leaveModal, leaveListeners, listeners, windowListeners, modalListeners, requests, dirty, location, saving(value) { saving = value; } };
}

function form(id, fields, dataset = {}) {
  const message = { isConnected: true, textContent: '' };
  const controls = [{ disabled: false }, { disabled: false }];
  return { id, fields, controls, dataset, isConnected: true, querySelector: () => message, querySelectorAll: () => controls };
}

const tick = () => new Promise(resolve => setImmediate(resolve));

test('Codex engine switching resets sharing and closes old consent', () => {
  const app = harness();
  app.modal.open = true;
  app.run(`state.aiProfile=true;state.aiRecords=true;state.aiText='保留文字';selectEngine('codex')`);
  assert.equal(app.run('state.aiEngine'), 'codex');
  assert.equal(app.run('state.aiProfile || state.aiRecords'), false);
  assert.equal(app.run('state.aiText'), '保留文字');
  assert.equal(app.modal.open, false);
  app.run(`state.aiBusy=true;selectEngine('api')`);
  assert.equal(app.run('state.aiEngine'), 'codex');
});

test('Codex engine switching preserves dirty settings until confirmed', () => {
  const app = harness();
  app.dirty.push(form('cloud-config-form', [], { dirty: 'true' }));
  app.run(`selectEngine('codex',true)`);
  assert.equal(app.run('state.aiEngine'), 'api');
  app.leaveListeners['#leave-cancel']();
  assert.equal(app.location.hash, '#home');
});

test('Codex preview freezes provider and task in consent dialog', async () => {
  const app = harness(), analysis = form('cloud-analysis-form', [['text', '合成']]);
  app.run(`state.route='assistant';state.aiEngine='codex'`);
  const pending = app.listeners.submit[0]({ target: analysis, preventDefault() {} });
  assert.equal(app.requests[0].url, '/api/codex/prepare');
  app.requests[0].resolve({ approval_id: 'synthetic', text: '合成', notice: '合成', model: '合成' });
  await pending;
  assert.ok(app.modal.innerHTML.includes('data-engine="codex"'));
  assert.ok(app.modal.innerHTML.includes('data-task="breakfast"'));
});

test('Codex consent submission cannot be rerouted by current engine', async () => {
  const app = harness(), consent = form('cloud-consent-form', [['consent', 'on']], { approval: 'synthetic', engine: 'codex', task: 'document' });
  const pending = app.listeners.submit[0]({ target: consent, preventDefault() {} });
  assert.equal(app.requests[0].url, '/api/codex/run');
  app.requests[0].resolve({ id: 'synthetic' }); await tick();
  app.requests[1].resolve(fixture); await tick();
  app.requests[2].resolve(fixture); await pending;
  assert.equal(app.location.hash, '#home');
  assert.equal(app.run('state.aiBusy'), false);
});

test('Codex configuration uses rendered revision and does not carry keys', async () => {
  const app = harness(), config = form('codex-config-form', [['model', 'synthetic']], { revision: 'rendered' });
  const pending = app.listeners.submit[0]({ target: config, preventDefault() {} });
  assert.equal(app.requests[0].url, '/api/codex/config');
  assert.deepEqual(JSON.parse(app.requests[0].options.body), { model: 'synthetic', vision: false, revision: 'rendered' });
  app.requests[0].resolve({}); await tick(); app.requests[1].resolve(fixture); await pending;
  assert.equal(config.dataset.saving, undefined);
});

test('Codex cancellation can recover active operation after browser reload', async () => {
  const app = harness();
  app.run(`state.data.codex={operation:'in-flight'};`);
  const pending = app.run('cancelCodex()');
  assert.equal(app.requests[0].url, '/api/codex/cancel');
  assert.equal(JSON.parse(app.requests[0].options.body).approval_id, 'in-flight');
  const duplicate = app.run('cancelCodex()'); await duplicate;
  assert.equal(app.requests.length, 1);
  app.requests[0].resolve({notice:'合成'}); await tick(); app.requests[1].resolve(fixture); await pending;
  assert.equal(app.run('state.codexCancelBusy'), false);
});

test('Codex login links reject nonofficial origins and escape account display', () => {
  const app = harness();
  for (const value of ['http://auth.openai.com/', 'https://auth.openai.com.evil.test/', 'https://user@auth.openai.com/', 'https://auth.openai.com/#hash', 'javascript:alert(1)']) {
    assert.equal(app.run(`safeCodexLoginURL(${JSON.stringify(value)})`), '');
  }
  assert.equal(app.run(`safeCodexLoginURL('https://auth.openai.com/authorize')`), 'https://auth.openai.com/authorize');
  app.run(`state.data.codex={authenticated:true,models:[],account:{email:'<script>secret</script>'}}`);
  assert.ok(!app.run('codexConnectionView()').includes('<script>secret'));
});

test('known routes, invalid hashes and missing state safely resolve', () => {
  const app = harness();
  for (const route of ['home', 'departments', 'timeline', 'documents', 'trends', 'care', 'meals', 'assistant', 'summary', 'models', 'settings']) {
    assert.equal(app.run(`routeState('#${route}', state.data).route`), route);
  }
  for (const hash of ['#nonsense', '#%E0%A4%A', '#<script>', '#', '#__proto__']) {
    assert.equal(app.run(`routeState(${JSON.stringify(hash)}, state.data).route`), 'home');
  }
  app.run('state.data=null; render()');
  assert.equal(app.root.innerHTML, '');
});

test('subroutes preserve tasks, care tabs, department and history details', () => {
  const app = harness();
  app.run(`state.data.departments=[{name:'全科'}];state.data.records=[{id:'opaque-record-id',department:'自定义科室'}];state.data.analyses=[{id:'opaque-analysis-id',task:'document'}]`);
  assert.equal(app.run(`routeState('#assistant?task=chat',state.data).task`), 'chat');
  assert.equal(app.run(`routeState('#assistant?analysis=opaque-analysis-id',state.data).task`), 'document');
  assert.equal(app.run(`routeState('#care?tab=condition',state.data).care`), 'condition');
  assert.equal(app.run(`routeState('#care?tab=bad',state.data).care`), 'medication');
  assert.equal(app.run(`routeState('#departments?department=0',state.data).department`), '全科');
  assert.equal(app.run(`routeState('#departments?department=999',state.data).department`), '');
  assert.equal(app.run(`routeState('#departments?custom=opaque-record-id',state.data).department`), '自定义科室');
  assert.equal(app.run(`routeState('#assistant?analysis=deleted-id',state.data).analysisId`), '');
});

test('unsaved form blocks render and rejected navigation leaves input intact', () => {
  const app = harness(), profile = form('profile-form', [], { dirty: 'true' });
  app.root.innerHTML = 'synthetic unsaved form';
  app.dirty.push(profile);
  app.run(`render(); navigate('#timeline')`);
  assert.equal(app.leaveModal.open, true);
  app.leaveListeners['#leave-cancel']();
  assert.equal(app.location.hash, '#home');
  assert.equal(app.root.innerHTML, 'synthetic unsaved form');
  assert.equal(profile.dataset.dirty, 'true');
  app.run(`navigate('#timeline')`); app.leaveListeners['#leave-confirm']();
  assert.equal(app.location.hash, '#timeline');
  assert.equal(profile.dataset.dirty, undefined);
});

test('saving form blocks navigation without discarding dirty status', () => {
  const app = harness(), profile = form('profile-form', [], { dirty: 'true', saving: 'true' });
  app.saving(profile); app.dirty.push(profile);
  app.run(`navigate('#timeline')`);
  assert.equal(app.location.hash, '#home');
  assert.equal(profile.dataset.dirty, 'true');
});

test('mobile menu and import discard repaint saved values before opening a sheet', () => {
  for (const open of ['mobileMenu', 'importMenu']) {
    const app = harness(), profile = form('profile-form', [], { dirty: 'true' });
    app.root.innerHTML = 'synthetic-unsaved-value';
    app.dirty.push(profile);
    app.run(`${open}()`);
    assert.equal(app.leaveModal.open, true);
    assert.equal(app.root.innerHTML, 'synthetic-unsaved-value');
    app.leaveListeners['#leave-confirm']();
    assert.equal(app.modal.open, true);
    assert.ok(!app.root.innerHTML.includes('synthetic-unsaved-value'));
    assert.equal(profile.dataset.dirty, undefined);
  }
});

test('browser back cancellation restores route without rendering away input', () => {
  const app = harness();
  app.run(`state.locationHash='#settings'`);
  app.dirty.push(form('profile-form', [], { dirty: 'true' }));
  app.location.hash = '#home';
  app.windowListeners.hashchange();
  assert.equal(app.location.hash, '#settings');
});

test('accepted browser back uses captured destination and clears only dirty flags', () => {
  const app = harness();
  app.run(`state.locationHash='#settings'`);
  const profile = form('profile-form', [['name', '合成']], { dirty: 'true', version: 'old' });
  app.dirty.push(profile); app.location.hash = '#home';
  app.windowListeners.hashchange();
  app.leaveListeners['#leave-confirm']();
  assert.equal(app.location.hash, '#home');
  assert.equal(profile.dataset.version, 'old');
  assert.equal(profile.dataset.dirty, undefined);
});

test('page leave confirmation is in-app and does not use blocking window.confirm', () => {
  assert.ok(!source.includes('window.confirm'));
  const html = fs.readFileSync(path.join(__dirname, '../health_journal/web/index.html'), 'utf8');
  for (const id of ['leave-modal', 'leave-title', 'leave-message', 'leave-cancel', 'leave-confirm']) assert.ok(html.includes(`id="${id}"`));
});

test('escape and close preserve unconfirmed dialog input', () => {
  const app = harness(), record = form('record-form', [], { dirty: 'true' });
  app.modal.open = true;
  app.modal.querySelector = selector => selector.includes('data-dirty') && record.dataset.dirty === 'true' ? record : null;
  let prevented = false;
  app.modalListeners.cancel({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(app.modal.open, true);
  app.leaveListeners['#leave-confirm'](); assert.equal(app.modal.open, false);
});

test('replacing a dialog retains its new confirmation callback', () => {
  const app = harness(); app.modal.open = true;
  app.run(`confirmation('synthetic', 'test', () => 'retained')`);
  assert.equal(app.run('state.confirmation()'), 'retained');
});

test('out-of-order state responses cannot overwrite a newer snapshot', async () => {
  const app = harness();
  const older = app.run('refresh(false)'), newer = app.run('refresh(false)');
  app.requests[1].resolve({ ...fixture, profile_version: 'newer' }); await newer;
  app.requests[0].resolve({ ...fixture, profile_version: 'older' }); await older;
  assert.equal(app.run('state.data.profile_version'), 'newer');
});

test('profile submission uses rendered version even after background refresh', async () => {
  const app = harness(), profile = form('profile-form', [['name', '合成未保存']], { version: 'original-form-version', dirty: 'true' });
  app.context.testForm = profile;
  app.run(`state.data.profile_version='new-background-version'`);
  const pending = app.listeners.submit[0]({ target: profile, preventDefault() {} });
  assert.equal(JSON.parse(app.requests[0].options.body)._version, 'original-form-version');
  assert.ok(profile.controls.every(control => control.disabled));
  const repeated = app.listeners.submit[0]({ target: profile, preventDefault() {} }); await repeated;
  assert.equal(app.requests.length, 1);
  app.requests[0].resolve({}); await tick();
  app.requests[1].resolve(fixture); await pending;
  assert.equal(profile.dataset.dirty, undefined);
  assert.ok(profile.controls.every(control => !control.disabled));
});

test('consent preview uses captured fields before controls are disabled', async () => {
  const app = harness(), analysis = form('cloud-analysis-form', [['text', '合成早餐原文'], ['document_id', 'synthetic-doc'], ['include_profile', 'on']]);
  app.run(`state.route='assistant'`);
  const pending = app.listeners.submit[0]({ target: analysis, preventDefault() {} });
  const sent = JSON.parse(app.requests[0].options.body);
  assert.equal(sent.text, '合成早餐原文'); assert.equal(sent.document_id, 'synthetic-doc');
  assert.equal(sent.include_profile, true); assert.equal(sent.include_records, false);
  app.requests[0].resolve({ approval_id: 'synthetic-approval', source: null, endpoint: 'https://example.com', model: 'synthetic', notice: '合成', text: '合成早餐原文', system_prompt: '合成' });
  await pending;
  assert.equal(app.modal.open, true); assert.ok(app.modal.innerHTML.includes('合成早餐原文'));
});

test('late preview does not open over a different page', async () => {
  const app = harness(), analysis = form('cloud-analysis-form', [['text', '合成']]);
  app.context.testForm = analysis;
  const pending = app.run(`previewCloud(testForm,new URLSearchParams(testForm.fields))`);
  analysis.isConnected = false; app.run(`state.route='settings'`);
  app.requests[0].resolve({}); await pending;
  assert.equal(app.modal.open, false);
});

test('late cloud completion cannot replace a dirty settings page or its form version', async () => {
  const app = harness();
  app.location.hash = '#assistant?task=breakfast';
  const pending = app.run(`runCloud('synthetic-approval')`);
  const profile = form('profile-form', [['name', '合成未保存']], { dirty: 'true', version: 'original-form-version' });
  app.dirty.push(profile); app.location.hash = '#settings';
  app.run(`state.route='settings'`); app.root.innerHTML = 'synthetic unsaved settings';
  app.requests[0].resolve({ id: 'synthetic-analysis-id' }); await tick();
  app.requests[1].resolve({ ...fixture, profile_version: 'new-background-version' }); await pending;
  assert.equal(app.location.hash, '#settings');
  assert.equal(app.root.innerHTML, 'synthetic unsaved settings');
  assert.equal(profile.dataset.version, 'original-form-version');
  assert.equal(profile.dataset.dirty, 'true');
  assert.equal(app.run('state.aiBusy'), false);
});

test('task switching keeps only in-memory drafts and resets sharing opt-ins', () => {
  const app = harness();
  app.run(`state.aiText='合成早餐草稿';state.aiProfile=true;selectTask('document');state.aiText='合成报告草稿';selectTask('breakfast')`);
  assert.equal(app.run('state.aiText'), '合成早餐草稿');
  assert.equal(app.run('state.aiProfile'), false);
  app.run(`selectTask('document')`);
  assert.equal(app.run('state.aiText'), '合成报告草稿');
  assert.ok(!/localStorage|sessionStorage/.test(source));
});

test('beforeunload warns about unsaved input and in-flight cloud requests', () => {
  const app = harness();
  let prevented = false;
  app.run('state.aiBusy=true');
  app.windowListeners.beforeunload({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
});

test('uploaded timestamps use local calendar, not sliced UTC date', () => {
  const app = harness();
  assert.equal(app.run(`localDate('2026-11-12T20:30:00+00:00')`), new Date('2026-11-12T20:30:00+00:00').toLocaleDateString('zh-CN'));
  assert.ok(!source.includes('doc.created_at.slice(0, 10)'));
});

test('deleted entities and invalid series index fail cleanly without throwing', async () => {
  const app = harness();
  app.run(`state.series=-5;state.data.records=[{id:'obs',kind:'observation',title:'血红蛋白',date:'2026-11-01',department:'',topic:'',notes:'',source_label:'',document_id:null,verification:'verified',version:1,updated_at:'2026-11-01T00:00:00Z',data:{value:130,comparator:'=',unit:'g/L',lab:'',reference_low:null,reference_high:null}}]`);
  assert.ok(app.run('trendsView()').includes('血红蛋白'));
  assert.equal(app.run('state.series'), 0);
  const toast = app.run('document.querySelector("#toast")');
  for (const [action, extra] of [['edit-record', {}], ['delete-analysis', {}], ['download-document', {}], ['swap-meal', { meal: 'breakfast' }]]) {
    const target = { disabled: false, isConnected: false, dataset: { action, id: 'missing-id', ...extra }, closest: selector => selector === '[data-action]' ? target : null };
    await app.listeners.click[0]({ target });
    assert.equal(toast.className, 'visible error');
    assert.equal(app.requests.length, 0);
  }
});
