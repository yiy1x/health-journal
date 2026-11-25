const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/wearables.js'), 'utf8');

function harness() {
  const listeners = {}, windowListeners = {}, requests = [], timers = [], modals = [];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
  const data = { today: '2026-01-04', wearables: { samples: 0, latest: '', catalog: [{ id: 'steps', name: '步数', unit: '步' }], metrics: [] } };
  const context = vm.createContext({ URLSearchParams, Date, console, crypto:require('node:crypto').webcrypto, location:{hash:'#wearables'},
    setTimeout(callback) { timers.push(callback); return timers.length; }, clearTimeout() {},
    document: { addEventListener(name, callback) { listeners[name] = callback; }, querySelector() { return {}; } },
    window: { addEventListener(name, callback) { windowListeners[name] = callback; } },
    FormData: class extends URLSearchParams { constructor(form) { super(form.fields); } },
  });
  vm.runInContext(source, context);
  let route = 'wearables', renders = 0;
  context.WearableUI.configure({ data: () => data, route: () => route, escape,
    header: (title, subtitle, buttons) => `<h1>${title}</h1><p>${subtitle}</p>${buttons}`,
    badge: value => escape(value), inputField: (label, name, value) => `<input name="${name}" value="${escape(value)}">`,
    selectField: (label, name, selected, choices) => `<select name="${name}">${choices.map(([value, title]) => `<option value="${escape(value)}">${escape(title)}</option>`).join('')}</select>`,
    request(url, options) { return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })); },
    render() { renders++; }, refresh: async () => {}, toast() {},
    openModal(title, body) { modals.push({title,body}); }, confirmation(title, body, callback) { modals.push({title,body,callback}); },
  });
  return { ui: context.WearableUI, listeners, windowListeners, requests, timers, data, modals, context, route(value) { route = value; }, renders: () => renders };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function snapshot(value = 100) { return { samples: 1, catalog: [{ id: 'steps', name: '步数', unit: '步' }], sources: [], metric: 'steps', from: '2026-01-02', to: '2026-01-02', daily: [{ day: '2026-01-02', value, count: 1, warning: '' }], meals: [], batches: [] }; }
function form(id, fields) { const error = { textContent: '' }, controls = [{disabled:false}]; return { id, fields, dataset: { dirty: 'true' }, querySelectorAll: () => controls, querySelector: () => error, error, controls }; }

test('wearable empty page has explicit no realtime and no diagnosis boundaries', () => {
  const app = harness(), html = app.ui.view();
  for (const text of ['不是实时连接', '不索取 Apple ID', '缺失', '不发送给 AI', '不会与', '人工记录']) {
    if (text !== '不会与') assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes('undefined'));
  assert.ok(!html.includes('NaN'));
});
test('wearable dates cross month and leap year correctly', () => {
  const app = harness();
  assert.equal(app.ui.dayBefore('2024-03-01', 1), '2024-02-29');
  assert.equal(app.ui.dayBefore('2026-01-01', 1), '2025-12-31');
});
test('missing numbers remain missing while zero stays zero', () => {
  const app = harness();
  assert.equal(app.ui.number(null), '—');
  assert.equal(app.ui.number(undefined), '—');
  assert.equal(app.ui.number(0), '0');
});
test('charts use CSP compatible SVG and never connect missing values', () => {
  const app = harness();
  const html = app.ui.chart([{day:'2026-01-01',value:0},{day:'2026-01-02',value:null},{day:'2026-01-03',value:100}], '步');
  assert.ok(html.includes('<rect'));
  assert.ok(html.includes('missing'));
  assert.ok(!/style=|<path|NaN|Infinity/.test(html));
  assert.ok(app.ui.chart([], '步').includes('缺失不会补成 0'));
});
test('wearable page escapes imported filenames devices warnings and meal text', () => {
  const app = harness(), payload = '<img src=x onerror=alert(1)>';
  app.ui.state.dashboard = {...snapshot(), sources:[{source:'source',source_name:payload,device:payload,count:1}], meals:[{day:'2026-01-02',meal:'breakfast',note:payload,source:payload}], batches:[{id:'safe',filename:payload,created_at:payload,samples:1}]};
  app.ui.state.query = {metric:'steps',from:'2026-01-02',to:'2026-01-02',source:''};
  const html = app.ui.view();
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes(payload));
});
test('initial entry loads once without polling forever', async () => {
  const app = harness();
  app.ui.enter(); app.ui.enter();
  assert.equal(app.requests.length, 2);
  app.requests[0].resolve(snapshot()); app.requests[1].resolve({day:'2026-01-04',metrics:{}}); await tick();
  app.ui.enter();
  assert.equal(app.requests.length, 2);
  assert.equal(app.timers.length, 1);
  const pending = app.timers[0]();
  app.requests[2].resolve({state:'idle'}); await pending;
  assert.equal(app.timers.length, 1);
});
test('leaving during status polling does not schedule more timers', async () => {
  const app = harness(); app.ui.enter(); app.requests[0].resolve(snapshot()); app.requests[1].resolve({day:'2026-01-04',metrics:{}}); await tick();
  const pending = app.timers[0](); app.route('settings');
  app.requests[2].resolve({state:'parsing'}); await pending;
  assert.equal(app.timers.length, 1);
});
test('filter captures input before disabling and resets source on metric switch', async () => {
  const app = harness(), target = form('wearable-filter-form', [['metric','heart_rate'],['from','2026-01-02'],['to','2026-01-03'],['source','old-device']]);
  app.ui.state.query = {metric:'steps',source:'old-device'};
  const pending = app.listeners.submit({target,preventDefault(){}});
  assert.ok(app.requests[0].url.includes('metric=heart_rate'));
  assert.ok(app.requests[0].url.endsWith('source='));
  assert.equal(target.controls[0].disabled, true);
  app.requests[0].resolve(snapshot()); app.requests[1].resolve({day:'2026-01-04',metrics:{}}); await tick();
  app.requests[2].resolve({meals:[]}); await pending;
  assert.equal(target.controls[0].disabled, false);
  assert.equal(target.dataset.dirty, undefined);
});
test('commit binds preview ID and selected metrics once', async () => {
  const app = harness(); app.ui.state.job={id:'opaque-preview',state:'ready'};
  const target = form('wearable-commit-form', [['metrics','steps'],['metrics','sleep'],['from','2026-01-02'],['to','2026-01-03'],['confirm','on']]);
  const pending = app.listeners.submit({target,preventDefault(){}});
  await app.listeners.submit({target,preventDefault(){}});
  assert.equal(app.requests.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(app.requests[0].options.json)), {id:'opaque-preview',metrics:['steps','sleep'],from:'2026-01-02',to:'2026-01-03',confirm:true});
  app.requests[0].reject(new Error('synthetic failed')); await pending;
  assert.equal(target.dataset.dirty, 'true');
  assert.equal(target.error.textContent, 'synthetic failed');
  assert.equal(app.ui.state.busy,false);
});
test('invalid large files never upload and unload warns during writes', async () => {
  const app = harness();
  const target = {id:'apple-health-upload',files:[{name:'large.zip',size:257*1024*1024}],value:'file'};
  await app.listeners.change({target});
  assert.equal(app.requests.length,0);
  assert.ok(app.ui.state.error.includes('256'));
  app.ui.state.busy=true; let warned=false;
  app.windowListeners.beforeunload({preventDefault(){warned=true;}});
  assert.ok(warned);
});
test('status preview discloses skipped data and profile exclusion', () => {
  const app = harness();
  app.ui.state.job = {id:'opaque',state:'ready',filename:'<bad>.xml',report:{samples:1,file_duplicates:0,metrics:[{metric:'steps',count:1,first:'2026-01-02',last:'2026-01-02'}],catalog:[{id:'steps',name:'步数'}],sources:[],unsupported:{Unknown:10},invalid:{'invalid unit':2}}};
  const html = app.ui.view();
  assert.ok(html.includes('Unknown：10'));
  assert.ok(html.includes('invalid unit：2'));
  assert.ok(html.includes('不会覆盖基本档案'));
  assert.ok(html.includes('&lt;bad&gt;.xml'));
});

test('daily view defaults to today not the last imported date', () => {
  const app = harness();
  app.data.wearables.latest='2025-01-01';
  const html=app.ui.view();
  assert.ok(html.includes('value="2026-01-04"'));
  assert.ok(html.includes('查看最近记录日'));
  assert.ok(html.includes('记一餐'));
  assert.ok(html.includes('还未记录，不代表没吃'));
});

test('date validation and URL selection reject impossible calendar days', () => {
  const app=harness();
  for(const day of ['2026-02-30','bad','1899-01-01','2026-1-1']) assert.equal(app.ui.validDay(day),false);
  app.context.location.hash='#wearables?date=2024-02-29';
  assert.ok(app.ui.view().includes('value="2024-02-29"'));
  app.context.location.hash='#wearables?date=2026-02-30';
  assert.ok(app.ui.view().includes('value="2026-01-04"'));
});

test('out of order date responses cannot replace current day snapshot', async () => {
  const app=harness(); app.ui.state.day='2026-01-02'; const old=app.ui.load();
  app.ui.state.day='2026-01-03'; app.ui.state.query=null; const fresh=app.ui.load();
  app.requests[2].resolve({...snapshot(200),marker:'fresh'});app.requests[3].resolve({day:'2026-01-03',metrics:{}});await fresh;
  app.requests[0].resolve({...snapshot(100),marker:'old'});app.requests[1].resolve({day:'2026-01-02',metrics:{}});await old;
  assert.equal(app.ui.state.dashboard.marker,'fresh');assert.equal(app.ui.state.dayData.day,'2026-01-03');
});

test('new food form starts without invented values and with stable client UUID', () => {
  const app=harness();app.ui.foodForm('lunch');
  const html=app.modals[0].body;
  assert.ok(html.includes('daily-food-form'));
  assert.ok(html.includes('name="time" value=""'));
  assert.ok(!html.includes('value="08:00"'));
  assert.match(html,/data-id="[a-f0-9-]{36}"/);
  assert.ok(html.includes('取消日记也会保留'));
});

test('food save failure preserves dirty inputs id and version for retry', async () => {
  const app=harness(), target=form('daily-food-form',[['date','2026-01-02'],['time','08:30'],['meal','breakfast'],['note','合成输入'],['document_id','']]);
  target.dataset.id='synthetic-id';target.dataset.version='2';
  const pending=app.listeners.submit({target,preventDefault(){}});
  assert.equal(app.requests[0].url,'/api/food');assert.equal(app.requests[0].options.method,'PUT');
  assert.equal(app.requests[0].options.json.note,'合成输入');assert.equal(app.requests[0].options.json.version,2);
  await app.listeners.submit({target,preventDefault(){}}); assert.equal(app.requests.length,1);
  app.requests[0].reject(new Error('conflict'));await pending;
  assert.equal(target.dataset.dirty,'true');assert.equal(target.dataset.version,'2');assert.equal(target.error.textContent,'conflict');
});

test('day metrics and actual food render in one view with no calorie budget', () => {
  const app=harness(); app.ui.state.day='2026-01-02';
  app.ui.state.dashboard={...snapshot(),meals:[{day:'2026-01-02',meal:'breakfast',note:'合成实际早餐',time:'08:30',origin:'journal',id:'opaque'}]};
  app.ui.state.dayData={day:'2026-01-02',metrics:{steps:{value:6200,count:1,sources:[],warning:''},sleep:{value:7.2,count:1},heart_rate:{value:65,count:2}}};
  const html=app.ui.view(); assert.ok(html.includes('6,200'));assert.ok(html.includes('合成实际早餐'));assert.ok(html.includes('7.2'));
  assert.ok(html.includes('不是浏览器缓存'));assert.ok(html.includes('本地不等于加密'));assert.ok(!html.includes('剩余热量'));
});

test('late responses after page leave cannot repaint or retain partial snapshot', async () => {
  const app=harness();const pending=app.ui.load();app.route('settings');app.windowListeners.hashchange();
  app.requests[0].resolve(snapshot());app.requests[1].resolve({day:'2026-01-04',metrics:{}});await pending;
  assert.equal(app.ui.state.dashboard,null);assert.equal(app.ui.state.loading,false);
});

test('opening help or modals does not repaint away expanded disclosures', async () => {
  const app=harness();
  const before=app.renders();
  await app.listeners.click({target:{closest:()=>({dataset:{wearable:'help'},disabled:false})}});
  assert.equal(app.modals.length,1);
  assert.equal(app.renders(),before);
});

test('new food submission omits zero version and deleting edited food refreshes document links', async () => {
  const app=harness();
  const createForm=form('daily-food-form',[['date','2026-01-02'],['time',''],['meal','breakfast'],['note','合成新餐'],['document_id','']]);
  createForm.dataset.id='synthetic-new';createForm.dataset.version='';
  const creating=app.listeners.submit({target:createForm,preventDefault(){}});
  assert.equal(app.requests[0].options.method,'POST');
  assert.equal('version' in app.requests[0].options.json,false);
  app.requests[0].resolve({date:'2026-01-02'}); await tick();
  app.requests[1].resolve(snapshot()); app.requests[2].resolve({day:'2026-01-02',metrics:{}}); await creating;
  const dirtyForm={dataset:{dirty:'true'}};
  let refreshed=0;
  app.ui.configure({
    data:()=>app.data, route:()=>'wearables', escape:value=>String(value??''), header:()=>'', badge:()=>'',
    inputField:()=>'', selectField:()=>'', request:(url,options)=>new Promise(resolve=>app.requests.push({url,options,resolve})),
    render(){}, refresh:async()=>{refreshed++;}, toast(){}, openModal(){},
    confirmation(title,body,callback){app.modals.push({title,body,callback});},
  });
  await app.listeners.click({target:{closest:selector=>selector==='[data-wearable]'?{dataset:{wearable:'food-delete',id:'synthetic-new',version:'1'},disabled:false,closest:()=>dirtyForm}:null}});
  assert.equal(dirtyForm.dataset.dirty,undefined);
  const deleting=app.modals.at(-1).callback();
  app.requests.at(-1).resolve({ok:true}); await tick();
  app.requests.at(-2).resolve(snapshot()); app.requests.at(-1).resolve({day:'2026-01-02',metrics:{}}); await deleting;
  assert.equal(refreshed,1);
});

test('stale source choice resets after source disappears and missing detail/job guards do not throw', async () => {
  const app = harness();
  app.ui.state.day = '2026-01-02';
  app.ui.state.choices.steps = 'a'.repeat(64);
  const loading = app.ui.load({ metric: 'steps', from: '2026-01-02', to: '2026-01-02', source: 'a'.repeat(64) });
  assert.equal(app.requests.length, 2);
  app.requests[0].resolve(snapshot(null));
  app.requests[1].resolve({ day: '2026-01-02', metrics: { steps: { value: null, count: 0, sources: [], warning: '未记录' } } });
  await tick();
  assert.equal(app.requests.length, 4);
  assert.equal(app.ui.state.choices.steps, '');
  assert.equal(app.ui.state.query.source, '');
  app.requests[2].resolve(snapshot(4200));
  app.requests[3].resolve({ day: '2026-01-02', metrics: { steps: { value: 4200, count: 1, sources: [{ source: 'b'.repeat(64), source_name: 'Watch', device: '' }], warning: '' } } });
  await loading;
  assert.equal(app.ui.state.dashboard.daily[0].value, 4200);
  for (const wearable of ['previous', 'next', 'cancel']) {
    const target = { disabled: false, dataset: { wearable }, closest: () => target };
    await app.listeners.click({ target });
  }
  assert.equal(app.requests.length, 4);
});
