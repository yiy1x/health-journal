const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const core = require('../health_journal/web/phone/core.js');

const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/phone.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const sample = (name = '合成.txt', text = 'synthetic') => core.makeDocument(name, new TextEncoder().encode(text));

async function harness() {
  const listeners = {}, windowListeners = {}, sheetListeners = {}, revoked = [], writes = [];
  const elements = new Map();
  const error = { textContent: '' }, controls = [{ disabled: false }, { disabled: true }];
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, { innerHTML: '', textContent: '', dataset: {}, focus() {}, setAttribute() {}, removeAttribute() {} });
    return elements.get(selector);
  }
  const root = element('#app'), sheet = element('#sheet'), location = { hash: '#capture' };
  Object.assign(sheet, { open: false, close() { this.open = false; }, showModal() { this.open = true; }, querySelector(selector) { return selector === '.error' ? error : element(selector); }, addEventListener(name, callback) { sheetListeners[name] = callback; } });
  root.querySelector = selector => selector === '.error' ? error : null;
  let row = null, writeFailure = false, sealFailure = false, sealWait = null, opened = null;
  const storage = {
    async read() { return row; },
    async write(envelope, revision) {
      writes.push({ envelope, revision });
      if (writeFailure) throw new Error('synthetic write failure');
      if (revision !== (row?.revision || null)) throw new Error('另一窗口已经更新档案');
      row = { revision: 'revision-' + writes.length, envelope };
      return row.revision;
    },
  };
  const context = vm.createContext({
    console, TextEncoder, TextDecoder, Uint8Array, Blob, crypto, Date,
    PhoneVaultCore: { ...core, async seal(documents) { if (sealWait) await sealWait; if (sealFailure) throw new Error('synthetic seal failure'); return { ciphertext: JSON.stringify(documents) }; }, async open() { if (!opened) throw new Error('synthetic wrong password'); return opened; } },
    PhoneVaultDB: storage, location,
    URL: { createObjectURL: () => 'blob:synthetic-' + (revoked.length + 1), revokeObjectURL: url => revoked.push(url) },
    history: { replaceState(data, title, hash) { location.hash = hash; } },
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1,
    navigator: {},
    fetch: async () => ({ ok: true, json: async () => Array.from({ length: 55 }, (_, index) => ({ name: '科室' + index, keywords: ['synthetic'] })) }),
    document: {
      querySelector: element, querySelectorAll: () => controls,
      addEventListener(name, callback) { (listeners[name] ||= []).push(callback); },
    },
    window: { isSecureContext: true, indexedDB: {}, scrollTo() {}, addEventListener(name, callback) { windowListeners[name] = callback; } },
    FormData: class extends Map { constructor(form) { super(form.fields); } },
  });
  const run = expression => vm.runInContext(expression, context);
  vm.runInContext(source, context);
  await tick();
  run("state.key={type:'synthetic'}; state.salt=new Uint8Array(16); render()");
  return { run, root, sheet, error, controls, location, revoked, writes, element, windowListeners, sheetListeners,
    emit(name, event) { for (const listener of listeners[name] || []) listener(event); },
    failWrite(value) { writeFailure = value; }, failSeal(value) { sealFailure = value; },
    waitSeal(value) { sealWait = value; }, setOpened(value) { opened = value; },
    setRow(value) { row = value; }, row() { return row; },
  };
}

function form(id, fields) {
  return { id, fields: Object.entries(fields), resets: 0, reset() { this.resets++; } };
}
function noteFields(extra = {}) {
  const date = new Date();
  return { title: '合成随记', date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`, kind: '日常随记', department: '', content: 'synthetic content', ...extra };
}
function submit(app, target) { app.emit('submit', { target, preventDefault() {} }); }
function click(app, action) { app.emit('click', { target: { closest(selector) { return selector === '[data-action]' ? { dataset: { action }, disabled: false } : null; } } }); }

test('phone routes render all three pages and safely fall back on invalid hashes', async () => {
  const app = await harness();
  for (const [hash, title] of [['#capture', '随手记下'], ['#library', '随身资料夹'], ['#backup', '备份与互传'], ['#__proto__', '随手记下']]) {
    app.location.hash = hash; app.run('render()');
    assert.ok(app.root.innerHTML.includes(title));
  }
});
test('phone hash back navigation preserves an open note or in-flight operation', async () => {
  const app = await harness();
  app.run('noteForm(); state.dirty=true');
  app.location.hash = '#library'; app.windowListeners.hashchange();
  assert.equal(app.location.hash, '#capture');
  assert.equal(app.run('state.dirty'), true);
  app.run('closeSheet(true); state.busy=true');
  app.location.hash = '#backup'; app.windowListeners.hashchange();
  assert.equal(app.location.hash, '#capture');
});
test('phone busy is non-reentrant and restores only previously enabled controls', async () => {
  const app = await harness();
  app.run('var release; var calls=0; var operation=busy(()=>new Promise(resolve=>{release=resolve;calls++}))');
  assert.ok(app.controls.every(control => control.disabled));
  await app.run('busy(async()=>{calls++})');
  assert.equal(app.run('calls'), 1);
  app.run('release()'); await app.run('operation');
  assert.equal(app.controls[0].disabled, false);
  assert.equal(app.controls[1].disabled, true);
});
test('phone persistence failure leaves prior snapshot, revision and note untouched', async () => {
  const app = await harness(), document = await sample();
  app.run(`state.documents=${JSON.stringify([document])}; noteForm(); state.dirty=true`);
  app.failWrite(true);
  submit(app, form('note-form', noteFields())); await tick(); await tick();
  assert.equal(app.run('state.documents.length'), 1);
  assert.equal(app.run('state.row'), null);
  assert.equal(app.run('state.dirty'), true);
  assert.equal(app.sheet.open, true);
  assert.match(app.error.textContent, /write failure/);
  assert.equal(app.run('state.busy'), false);
});
test('phone encryption failure never writes plaintext or changes the saved snapshot', async () => {
  const app = await harness(); app.failSeal(true);
  await assert.rejects(app.run('save([])'), /seal failure/);
  assert.equal(app.writes.length, 0);
  assert.equal(app.run('state.row'), null);
});
test('phone saved note is idempotent and retains source disclaimer', async () => {
  const app = await harness(), fields = noteFields({ title: '合成早餐🥣' });
  submit(app, form('note-form', fields)); await tick(); await tick();
  assert.equal(app.run('state.documents.length'), 1);
  assert.match(new TextDecoder().decode(core.unbase64(app.run('state.documents[0].content'), core.MAX_FILE)), /未经临床核实/);
  submit(app, form('note-form', fields)); await tick(); await tick();
  assert.equal(app.run('state.documents.length'), 1);
  assert.equal(app.writes.length, 1);
});
test('phone invalid dates, future notes and malformed Unicode cannot be stored', async () => {
  for (const extra of [{ date: '2026-02-30' }, { date: '9999-01-01' }, { content: '\ud800' }, { title: '   ' }]) {
    const app = await harness();
    submit(app, form('note-form', noteFields(extra))); await tick();
    assert.equal(app.writes.length, 0);
    assert.match(app.error.textContent, /有效标题/);
  }
});
test('phone duplicate submit during encryption produces exactly one transaction', async () => {
  const app = await harness();
  let release; app.waitSeal(new Promise(resolve => { release = resolve; }));
  submit(app, form('note-form', noteFields())); await tick();
  submit(app, form('note-form', noteFields()));
  release(); await tick(); await tick();
  assert.equal(app.writes.length, 1);
});
test('phone partial batch failure retries only unsuccessful items', async () => {
  const app = await harness();
  app.run(`var reads=0; var fileFails=true; prepareFiles([{name:'one.txt',size:3,arrayBuffer:async()=>new TextEncoder().encode('one')},{name:'two.txt',size:3,arrayBuffer:async()=>{reads++;if(fileFails)throw new Error('synthetic read failure');return new TextEncoder().encode('two')}}])`);
  await app.run('saveFiles()');
  assert.equal(app.run('state.documents.length'), 1);
  assert.equal(app.run('state.queue[0].done'), true);
  assert.match(app.run('state.queue[1].status'), /未保存/);
  app.run('fileFails=false'); await app.run('saveFiles()');
  assert.equal(app.run('state.documents.length'), 2);
  assert.equal(app.writes.length, 2);
  assert.equal(app.run('reads'), 2);
});
test('phone oversize files and oversized batches never read file bytes', async () => {
  const app = await harness();
  app.run("prepareFiles([{name:'big.txt',size:core.MAX_FILE+1,arrayBuffer:()=>{throw new Error('must not read')}}])");
  await app.run('saveFiles()');
  assert.match(app.run('state.queue[0].status'), /超过 20 MB/);
  app.run('closeSheet(true); prepareFiles(Array(51).fill({}))');
  assert.equal(app.sheet.open, false);
  assert.equal(app.writes.length, 0);
});
test('phone lock clears documents, searches, pending work, previews and download URLs', async () => {
  const app = await harness();
  app.run("download(new Blob(['synthetic']), 'test.txt'); state.query='private'; state.department='private'; state.documents=[{}]; state.pending=[{}]; state.queue=[{}]; lock()");
  for (const expression of ['state.key', 'state.salt', 'state.pending']) assert.equal(app.run(expression), null);
  assert.equal(app.run('state.documents.length+state.queue.length'), 0);
  assert.equal(app.run('state.query+state.department'), '');
  assert.equal(app.sheet.innerHTML, '');
  assert.equal(app.revoked.length, 1);
});
test('phone inactivity locks on resume, but cannot interrupt a pending save', async () => {
  const app = await harness();
  app.run('state.lastActive=Date.now()-300001; state.busy=true; checkLock()');
  assert.notEqual(app.run('state.key'), null);
  app.run('state.busy=false'); app.windowListeners.pageshow();
  assert.equal(app.run('state.key'), null);
});
test('phone late file selection after lock is discarded and the input is cleared', async () => {
  const app = await harness(); app.run('lock()');
  const input = { id: 'files', type: 'file', files: [{}], value: 'synthetic' };
  app.emit('change', { target: input });
  assert.equal(input.value, '');
  assert.equal(app.sheet.open, false);
  assert.equal(app.run('state.queue.length'), 0);
});
test('phone backup merge requires preview then confirmation and keeps local encryption key', async () => {
  const app = await harness(), document = await sample();
  app.setOpened({ documents: [document], key: 'foreign-key', salt: 'foreign-salt' });
  app.run("state.pending={ciphertext:'synthetic'}");
  submit(app, form('restore-form', { password: 'synthetic-only' })); await tick();
  assert.equal(app.writes.length, 0);
  assert.match(app.sheet.innerHTML, /将新增 1 份/);
  click(app, 'merge-transfer'); await tick(); await tick();
  assert.equal(app.run('state.documents.length'), 1);
  assert.equal(app.run('state.key.type'), 'synthetic');
  assert.equal(app.run('state.pending'), null);
});
test('phone wrong backup password keeps pending envelope available for retry', async () => {
  const app = await harness();
  app.run("state.pending={ciphertext:'keep'}");
  const target = form('restore-form', { password: 'synthetic-wrong' });
  submit(app, target); await tick();
  assert.equal(app.run('state.pending.ciphertext'), 'keep');
  assert.equal(target.resets, 0);
  assert.equal(app.writes.length, 0);
});
test('phone transfer integrity failure leaves local data and pending confirmation unchanged', async () => {
  const app = await harness();
  await assert.rejects(app.run("prepareTransfer({size:10,text:async()=>JSON.stringify({format:'health-journal-transfer',version:2,documents:[]})})"));
  assert.equal(app.writes.length, 0);
  assert.equal(app.run('state.pending'), null);
});
test('phone cross-window revision conflict cannot commit a stale merge', async () => {
  const app = await harness(), document = await sample();
  app.setRow({ revision: 'other-window', envelope: { ciphertext: 'keep' } });
  app.run(`state.pending=${JSON.stringify([document])}`);
  click(app, 'merge-transfer'); await tick(); await tick();
  assert.equal(app.run('state.documents.length'), 0);
  assert.equal(app.run('state.pending.length'), 1);
  assert.equal(app.row().envelope.ciphertext, 'keep');
  assert.match(app.error.textContent, /另一窗口/);
});
test('phone export requires a visible download link and revokes it when closed', async () => {
  const app = await harness();
  click(app, 'backup'); await tick();
  assert.match(app.sheet.innerHTML, /保存文件/);
  assert.match(app.element('#save-file').href, /^blob:/);
  app.run('closeSheet(true)');
  assert.equal(app.revoked.length, 1);
});
test('phone beforeunload protects selected originals and pending merges as well as notes', async () => {
  const app = await harness();
  for (const condition of ['state.dirty=true', 'state.busy=true', 'state.queue=[{done:false}]', 'state.pending=[{}]']) {
    app.run('state.dirty=false;state.busy=false;state.queue=[];state.pending=null');
    app.run(condition);
    let prevented = false;
    app.windowListeners.beforeunload({ preventDefault() { prevented = true; } });
    assert.equal(prevented, true, condition);
  }
});
test('phone completed import queue no longer triggers an unload warning', async () => {
  const app = await harness(); app.run('state.queue=[{done:true}]');
  app.windowListeners.beforeunload({ preventDefault() { assert.fail('completed work is not dirty'); } });
});
test('phone text preview treats imported HTML as inert text', async () => {
  const app = await harness(), document = await sample('synthetic.txt', '<img src=x onerror=alert(1)><script>bad()</script>');
  app.run(`state.documents=${JSON.stringify([document])};viewDocument('${document.sha256}')`);
  const preview = app.element('#document-preview').innerHTML;
  assert.ok(preview.includes('&lt;script&gt;'));
  assert.ok(!preview.includes('<script>'));
  assert.ok(!preview.includes('<img'));
});
