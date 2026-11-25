const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/app.js'), 'utf8');
const element = { content: 'synthetic-token', addEventListener() {}, innerHTML: '' };
const context = vm.createContext({
  document: { querySelector() { return element; }, addEventListener() {} },
  window: { addEventListener() {} },
  location: { hash: '#home' },
  fetch: () => new Promise(() => {}),
  console,
});
vm.runInContext(source, context);
const run = expression => vm.runInContext(expression, context);
run(`state.data = {
  today: '2026-11-13', version: '1.1.0', records: [], documents: [], plans: [], analyses: [], departments: [],
  profile: {name: '合成测试', birth_date: '', sex: 'unspecified', allergies: [], diet: 'balanced', clinical_diet: false, diet_notes: '', diet_acknowledged: true, emergency_contact: '', notes: ''},
  allergens: [], nutrition_restrictions: [], recipes: [], audits: [], model: '', demo: false,
  nutrition_notice: '合成测试', safety: '测试安全提示', data_directory: '/synthetic',
};`);

test('escapes text and attribute delimiters', () => {
  assert.equal(run(`escape(${JSON.stringify('<script>"&\'')})`), '&lt;script&gt;&quot;&amp;&#39;');
});

test('retains small values rather than rounding to zero', () => {
  assert.equal(run('numeric(0.00000012)'), '1.2e-7');
  assert.equal(run('numeric(1.23456789)'), '1.23456789');
});

test('unknown values are not rendered as undefined', () => {
  assert.equal(run('escape(null)'), '');
  assert.equal(run('fmtDate("")'), '未记录');
});

test('medication status respects dates', () => {
  assert.equal(run(`currentMedication({data:{status:'active',start_date:'2026-01-01',end_date:''}})`), true);
  assert.equal(run(`currentMedication({data:{status:'active',start_date:'2026-01-01',end_date:'2026-11-12'}})`), false);
  assert.equal(run(`currentMedication({data:{status:'planned',start_date:'2026-01-01',end_date:''}})`), false);
});

test('unverified and comparator values do not gain reference classification', () => {
  assert.equal(run(`flag({verification:'pending',data:{value:999,comparator:'=',reference_high:4}})[0]`), '待核对');
  assert.equal(run(`flag({verification:'verified',data:{value:999,comparator:'>',reference_high:4}})[0]`), '非精确值');
});

test('trend grouping separates unit and laboratory', () => {
  run(`state.data.records = [
    {kind:'observation',title:'合成指标',data:{unit:'mmol/L',lab:'A'}},
    {kind:'observation',title:'合成指标',data:{unit:'mg/dL',lab:'A'}},
    {kind:'observation',title:'合成指标',data:{unit:'mmol/L',lab:'B'}}
  ]`);
  assert.equal(run('observationGroups().length'), 3);
  run('state.data.records = []');
});

test('trend excludes pending and nonexact points', () => {
  const rendered = run(`chart([
    {title:'合成指标',date:'2026-01-01',verification:'verified',data:{value:2,comparator:'=',unit:'x'}},
    {title:'合成指标',date:'2026-01-02',verification:'pending',data:{value:3,comparator:'=',unit:'x'}},
    {title:'合成指标',date:'2026-01-03',verification:'verified',data:{value:4,comparator:'>',unit:'x'}}
  ])`);
  assert.ok(rendered.includes('至少需要两条'));
  assert.ok(!rendered.includes('chart-line'));
});

test('constant-value and same-day charts produce finite coordinates', () => {
  const rendered = run(`chart([
    {title:'合成指标',date:'2026-01-01',verification:'verified',data:{value:2,comparator:'=',unit:'x'}},
    {title:'合成指标',date:'2026-01-01',verification:'verified',data:{value:2,comparator:'=',unit:'x'}}
  ])`);
  assert.ok(rendered.includes('chart-line'));
  assert.ok(!/NaN|Infinity/.test(rendered));
});

test('extreme chart range shows a safe fallback', () => {
  const rendered = run(`chart([
    {title:'合成指标',date:'2026-01-01',verification:'verified',data:{value:-1e308,comparator:'=',unit:'x'}},
    {title:'合成指标',date:'2026-01-02',verification:'verified',data:{value:1e308,comparator:'=',unit:'x'}}
  ])`);
  assert.ok(rendered.includes('数值量级过大'));
  assert.ok(!/NaN|Infinity/.test(rendered));
});

test('search matches free text and department together', () => {
  run(`state.data.records = [{kind:'visit',title:'合成检查',department:'全科',topic:'年度',notes:'合成备注',source_label:'',data:{hospital:'测试机构'}}];state.query='测试机构';state.department='全科'`);
  assert.equal(run('filterRecords().length'), 1);
  run(`state.department='口腔科'`);
  assert.equal(run('filterRecords().length'), 0);
  run(`state.data.records=[];state.department='';state.query=''`);
});

test('stale plan adopts backend safety restrictions including age', () => {
  assert.equal(run(`planStale({constraints:{allergies:[],diet:'balanced'}})`), false);
  run(`state.data.nutrition_restrictions=['未成年人']`);
  assert.equal(run(`planStale({constraints:{allergies:[],diet:'balanced'}})`), true);
  run(`state.data.nutrition_restrictions=[]`);
  assert.equal(run(`planStale({constraints:{allergies:['牛奶'],diet:'balanced'}})`), true);
});

test('all eleven routes render empty states without exceptions', () => {
  for (const view of ['homeView', 'timelineView', 'documentWorkspaceView', 'trendsView', 'careView', 'mealWorkspaceView', 'assistantView', 'summaryView', 'settingsView', 'departmentsView', 'modelsView']) {
    const rendered = run(`${view}()`);
    assert.ok(rendered.length > 100, view);
    assert.ok(!rendered.includes('undefined'), view);
  }
});

test('blank personal profile renders neutral titles and no demo banner on all routes', () => {
  const original = run('JSON.stringify(state.data.profile)');
  run(`state.data.profile.name='';state.data.profile.diet='unspecified';state.data.profile.diet_acknowledged=false`);
  for (const view of ['homeView', 'timelineView', 'documentWorkspaceView', 'trendsView', 'careView', 'mealWorkspaceView', 'assistantView', 'summaryView', 'settingsView', 'departmentsView', 'modelsView']) {
    const html = run(`${view}()`);
    assert.ok(!/合成演示|体验档案|示例医生|示例健康中心|--demo|undefined|NaN/.test(html), view);
  }
  assert.ok(run('homeView()').includes('我的健康档案'));
  assert.ok(!run('homeView()').includes('你好，'));
  assert.ok(run('summaryView()').includes('<h2>就医摘要</h2>'));
  assert.ok(run('settingsView()').includes('name="name" value="" maxlength="40"'));
  assert.ok(run('settingsView()').includes('value="unspecified" selected>暂未填写'));
  assert.ok(run('mealsView()').includes('饮食偏好未填写'));
  assert.ok(!run('mealsView()').includes('均衡搭配偏好'));
  run(`state.data.profile=${original}`);
});

test('empty trends do not imply a prior measurement', () => {
  const html = run('chart([])');
  assert.ok(html.includes('还没有检验指标'));
  assert.ok(!html.includes('再记录一次'));
  assert.ok(!html.includes('chart-line'));
});

test('assistant task tabs and medical warnings are present for all modes', () => {
  for (const task of ['breakfast', 'document', 'chat', 'local']) {
    run(`state.aiTask=${JSON.stringify(task)}`);
    const rendered = run('assistantView()');
    assert.ok(rendered.includes('测试安全提示'));
    assert.ok(rendered.includes('aria-selected="true"'));
  }
  run(`state.aiTask='breakfast'`);
});

test('draft output and provenance are text only, not active markup', () => {
  const rendered = run(`analysisResult({id:'synthetic',task:'breakfast',result:{summary:'<script>unsafe()</script>',foods:[{name:'<img src=x>',portion:'unknown',confidence:'low'}],uncertainties:['<iframe>'],suggestions:[],questions:[]},intake:{},provenance:{provider:'custom',model:'<svg>',endpoint:'https://example.com/v1',submitted_text:'<script>unsafe()</script>'}})`);
  assert.ok(rendered.includes('AI 草稿'));
  assert.ok(rendered.includes('记录实际饮食'));
  assert.ok(rendered.includes('&lt;script&gt;'));
  assert.ok(!rendered.includes('<script>'));
  assert.ok(!rendered.includes('<img src=x>'));
});

test('department folders preserve pending provenance and custom record names', () => {
  run(`state.data.departments=[{name:'内分泌科',group:'内科',description:'血糖',keywords:['血糖']}]; state.data.documents=[{id:'doc',filename:'合成.txt',routing:{status:'pending',links:[{name:'内分泌科'}]}}];state.data.records=[{kind:'visit',department:'自定义合成科室',document_id:'doc'}]`);
  assert.equal(run(`specialtyData('内分泌科').items.length`), 1);
  assert.ok(run(`specialtyFolders()`).includes('待确认'));
  assert.ok(run(`departmentCatalog().some(item=>item.name==='自定义合成科室')`));
  run(`state.specialtyQuery='血糖'`);
  assert.ok(run('specialtyFolders()').includes('内分泌科'));
  assert.ok(!run('specialtyFolders()').includes('自定义合成科室'));
  run(`state.specialtyQuery='';state.data.records=[];state.data.documents=[];state.data.departments=[]`);
});

test('privacy labels disclose optional cloud and memory-only key', () => {
  assert.ok(run('settingsView()').includes('逐次确认后才外发'));
  assert.ok(!run('settingsView()').includes('无云端 API'));
  assert.ok(run('modelsView()').includes('重启后需重新填写'));
  assert.ok(!source.includes('localStorage'));
});

test('two-section navigation groups daily and archive views with compact model settings', () => {
  assert.equal(run('navSections.map(section => section[0]).join(",")'), '日常记录,医疗档案');
  assert.equal(run(`routeGroup('wearables')`), '日常记录');
  assert.equal(run(`routeGroup('timeline')`), '医疗档案');
  assert.equal(run(`routeGroup('models')`), '设置');
  run(`state.data.cloud={provider:'deepseek',base_url:'https://api.deepseek.com',model:'deepseek-flash',vision:true,has_key:false,providers:[{id:'deepseek',name:'DeepSeek（深度求索）',base_url:'https://api.deepseek.com'}]}`);
  const html = run('modelsView()');
  assert.ok(html.includes('deepseek-flash'));
  assert.ok(html.includes('https://api.deepseek.com'));
  assert.ok(html.includes('方式二：使用 ChatGPT 账号 · Codex'));
});

test('user data in profile and summary is escaped', () => {
  run(`state.data.profile.name='<img src=x onerror=alert(1)>'`);
  const rendered = run('summaryView()');
  assert.ok(rendered.includes('&lt;img'));
  assert.ok(!rendered.includes('<img src=x'));
  run(`state.data.profile.name='合成测试'`);
});

test('all record kinds offer explicit source and kind-specific forms', () => {
  for (const kind of ['visit', 'observation', 'medication', 'symptom', 'condition', 'reminder']) {
    assert.ok(run(`recordFields('${kind}')`).includes('name='));
  }
});

test('summary retains visit conclusions, notes and original filenames', () => {
  run(`state.data.documents=[{id:'synthetic',filename:'合成原件.txt'}]`);
  const details = run(`summaryDetails({kind:'visit',document_id:'synthetic',department:'全科',topic:'合成主题',notes:'合成补充',data:{doctor:'合成医生',reason:'合成主诉',conclusion:'合成原文结论'}})`);
  for (const value of ['合成原文结论', '合成主诉', '合成医生', '合成补充', '合成原件.txt']) assert.ok(details.includes(value));
  run('state.data.documents=[]');
});

test('summary keeps medication dates, source, symptom triggers and diet notes', () => {
  assert.ok(run(`summaryDetails({kind:'medication',data:{start_date:'2026-01-01',end_date:'',prescriber:'合成处方来源'}})`).includes('合成处方来源'));
  assert.ok(run(`summaryDetails({kind:'symptom',data:{triggers:'合成诱因',red_flags:true}})`).includes('危险表现'));
  run(`state.data.profile.diet_notes='合成饮食医嘱'`);
  assert.ok(run('summaryView()').includes('合成饮食医嘱'));
  run(`state.data.profile.diet_notes=''`);
});
