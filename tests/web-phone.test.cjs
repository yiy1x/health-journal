const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../health_journal/web/phone/core.js');
const bytes = text => new TextEncoder().encode(text);
const password = 'synthetic-phone-test-password';
const sample = () => core.makeDocument('合成随记.txt', bytes('合成体检资料，不是真实医疗信息'));

test('phone base64 handles canonical small and multi-megabyte files', () => {
  for (const size of [0, 1, 2, 3, 65537, 2 * 1024 * 1024]) {
    const content = new Uint8Array(size).fill(137);
    assert.deepEqual(core.unbase64(core.base64(content), size), content);
  }
});
test('phone rejects noncanonical base64 and oversize data', () => {
  for (const value of ['YQ==\n', 'YR==', '____', 'YQ', '====']) assert.throws(() => core.unbase64(value, 100));
  assert.throws(() => core.unbase64('YQ==', 0));
});
test('phone validates filename paths, controls and Unicode', () => {
  for (const name of ['../a.txt', '.hidden.txt', 'a/b.txt', 'a\\b.txt', 'a\0.txt', 'a\t.txt', 'a:b.txt', '\ud800.txt', ' a.txt']) assert.throws(() => core.filename(name));
  assert.equal(core.filename('我的早餐🥣.txt'), '我的早餐🥣.txt');
});
test('phone refuses invalid UTF8, NUL, HEIC and mismatched signatures', () => {
  for (const [name, content] of [['image.heic', bytes('heic')], ['image.png', bytes('not png')], ['note.txt', new Uint8Array([255])], ['note.txt', bytes('a\0')], ['note.txt', bytes('')]]) assert.throws(() => core.documentType(name, content));
  assert.equal(core.documentType('report.PDF', bytes('%PDF-1.7')), 'application/pdf');
  assert.equal(core.documentType('photo.jpg', new Uint8Array([255, 216, 255, 1])), 'image/jpeg');
});
test('phone rejects extensionless names that desktop cannot import', () => {
  for (const name of ['txt', 'pdf', 'jpg', 'png']) assert.throws(() => core.documentType(name, bytes('synthetic')));
});
test('phone transfer validates and returns only allowlisted fields', async () => {
  const item = await sample();
  assert.deepEqual(await core.validate(core.pack([item])), [item]);
  await assert.rejects(core.validate({ ...core.pack([item]), profile: {} }));
  await assert.rejects(core.validate(core.pack([{ ...item, extra: true }])));
});
test('phone rejects tampered content, wrong MIME, repeated hashes and future schemas', async () => {
  const item = await sample();
  for (const raw of [core.pack([{ ...item, sha256: '0'.repeat(64) }]), core.pack([{ ...item, mime: 'text/html' }]), core.pack([item, item]), { ...core.pack([]), version: 2 }, { ...core.pack([]), version: true }]) await assert.rejects(core.validate(raw));
});
test('phone merging is idempotent and keeps local names on same-content conflicts', async () => {
  const item = await sample(), renamed = { ...item, filename: '其他名称.txt' };
  const merged = core.merge([item], [renamed]);
  assert.deepEqual(merged, { documents: [item], added: 0, duplicates: 1, renamed: 1 });
});
test('phone same filename different contents preserves both without last-writer-wins', async () => {
  const first = await sample(), second = await core.makeDocument(first.filename, bytes('different'));
  const merged = core.merge([first], [second]);
  assert.equal(merged.documents.length, 2);
  assert.equal(merged.added, 1);
  assert.deepEqual(merged.documents[0], first);
});
test('phone merge limit failure does not mutate existing snapshot', () => {
  const existing = Array.from({ length: 500 }, (_, index) => ({ sha256: String(index), content: 'YQ==', filename: 'a.txt' }));
  assert.throws(() => core.merge(existing, [{ sha256: 'new', content: 'Yg==', filename: 'b.txt' }]));
  assert.equal(existing.length, 500);
});
test('phone long passwords required, not whitespace-only', () => {
  for (const value of ['short', ' '.repeat(20), 'a'.repeat(257), null]) assert.throws(() => core.passwordCheck(value));
  core.passwordCheck(password);
});
test('phone encrypted backup roundtrip uses a nonextractable key and random IV', async () => {
  const item = await sample(), salt = crypto.getRandomValues(new Uint8Array(16)), key = await core.derive(password, salt);
  assert.equal(key.extractable, false);
  const first = await core.seal([item], key, salt), second = await core.seal([item], key, salt);
  assert.notEqual(first.iv, second.iv);
  assert.notEqual(first.ciphertext, second.ciphertext);
  assert.ok(!JSON.stringify(first).includes(item.filename));
  assert.ok(!JSON.stringify(first).includes(password));
  const opened = await core.open(first, password);
  assert.deepEqual(opened.documents, [item]);
});
test('phone still unlocks authenticated 1.2.0 backups with legacy names without changing bytes', async () => {
  const salt = new Uint8Array(16), key = await core.derive(password, salt);
  const first = { ...await core.makeDocument('valid.txt', bytes('legacy extensionless')), filename: 'txt' };
  const second = { ...await core.makeDocument('valid.txt', bytes('legacy control')), filename: 'legacy\u0085\ufeff.txt' };
  const envelope = await core.seal([first, second], key, salt);
  const opened = await core.open(envelope, password);
  assert.equal(opened.renamed, 2);
  assert.deepEqual(opened.documents, [{ ...first, filename: '原件.txt' }, { ...second, filename: 'legacy__.txt' }]);
  assert.deepEqual(await core.validate(core.pack(opened.documents)), opened.documents);
});
test('phone legacy backup compatibility never repairs paths or bypasses content validation', async () => {
  const salt = new Uint8Array(16), key = await core.derive(password, salt), document = await sample();
  for (const changed of [{ filename: '../unsafe.txt' }, { filename: 'pdf' }, { sha256: '0'.repeat(64) }]) {
    const envelope = await core.seal([{ ...document, ...changed }], key, salt);
    await assert.rejects(core.open(envelope, password));
  }
});
test('phone rejects wrong password, changed salt and changed ciphertext', async () => {
  const salt = new Uint8Array(16), key = await core.derive(password, salt), envelope = await core.seal([await sample()], key, salt);
  await assert.rejects(core.open(envelope, password + '-wrong'), /密码不正确/);
  await assert.rejects(core.open({ ...envelope, salt: core.base64(new Uint8Array(16).fill(1)) }, password));
  const ciphertext = core.unbase64(envelope.ciphertext, core.MAX_TRANSFER + 16); ciphertext[3] ^= 1;
  await assert.rejects(core.open({ ...envelope, ciphertext: core.base64(ciphertext) }, password), /密码不正确/);
});
test('phone rejects KDF manipulation and unknown envelope fields before derivation', async () => {
  const salt = new Uint8Array(16), key = await core.derive(password, salt), envelope = await core.seal([], key, salt);
  for (const changed of [{ iterations: 1 }, { iterations: 100000000000 }, { version: 2 }, { unsafe: true }, { iv: 'YQ==' }, { cipher: 'AES-CBC' }]) await assert.rejects(core.open({ ...envelope, ...changed }, password));
});
test('phone keyword classification is a suggestion based only on name and text', async () => {
  const catalog = [{ name: '体检中心', keywords: ['体检'] }, { name: '眼科', keywords: ['眼底'] }];
  assert.deepEqual(core.suggest(await sample(), catalog), ['体检中心']);
  assert.deepEqual(core.suggest({ filename: '未分类.jpg', mime: 'image/jpeg', content: '' }, catalog), []);
});
test('phone service worker caches static exact allowlist, not APIs or user uploads', () => {
  const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/sw.js'), 'utf8');
  assert.ok(source.includes("event.request.method !== 'GET' || !approved.has(url.href)"));
  assert.ok(!source.includes('skipWaiting'));
  assert.ok(!source.includes('/api/'));
});
test('phone HTML has native rear-camera hint and no analytics or remote scripts', () => {
  const html = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/index.html'), 'utf8');
  assert.ok(html.includes('capture="environment"'));
  assert.ok(html.includes("connect-src 'self'"));
  assert.ok(!/<script[^>]*https?:/i.test(html));
  const style = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/phone.css'), 'utf8');
  assert.ok(style.includes('[hidden] { display: none !important; }'));
  assert.ok(style.includes('env(safe-area-inset-bottom)'));
});

test('phone export uses a real second-tap download link after encryption', () => {
  const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/phone.js'), 'utf8');
  assert.ok(source.includes('id="save-file" class="download-link" download='));
  assert.ok(!source.includes('anchor.click()'));
  assert.ok(source.includes('仅看到本提示不代表备份完成'));
});

test('phone offline routing strips fragments but never catches APIs or unrelated resources', async () => {
  const vm = require('node:vm'), listeners = {}, matches = [];
  const source = fs.readFileSync(path.join(__dirname, '../health_journal/web/phone/sw.js'), 'utf8');
  const context = vm.createContext({ URL, self: { registration: { scope: 'https://synthetic.invalid/phone/' }, addEventListener(name, callback) { listeners[name] = callback; } }, caches: { open: async () => ({ match: async url => { matches.push(url); return 'cached-shell'; } }) }, fetch: () => { throw new Error('unexpected network'); } });
  vm.runInContext(source, context);
  for (const fragment of ['', '#capture', '#library', '#backup']) {
    let result;
    listeners.fetch({ request: { method: 'GET', url: 'https://synthetic.invalid/phone/' + fragment }, respondWith(promise) { result = promise; } });
    assert.equal(await result, 'cached-shell');
  }
  assert.ok(matches.every(url => url === 'https://synthetic.invalid/phone/'));
  for (const url of ['https://synthetic.invalid/api/state', 'https://synthetic.invalid/phone/?unknown=1', 'https://other.invalid/phone/']) {
    listeners.fetch({ request: { method: 'GET', url }, respondWith() { assert.fail('unexpected interception'); } });
  }
});
