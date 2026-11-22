const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const core = require('../health_journal/web/phone/core.js');

const script = `
import json, sys, tempfile
from health_journal.store import Store
from health_journal.transfer import read_transfer, export_transfer
from health_journal.validation import AppError
content = sys.stdin.buffer.read()
if sys.argv[1] == 'validate':
    try:
        read_transfer(content)
        print('accepted')
    except AppError:
        print('rejected')
else:
    with tempfile.TemporaryDirectory(prefix='health-cross-runtime-') as directory:
        store = Store(directory)
        entries = read_transfer(content)
        first = store.merge_documents(entries)
        second = store.merge_documents(entries)
        assert first['imported'] == len(entries)
        assert second['imported'] == 0
        assert second['duplicates'] == len(entries)
        assert store.records() == []
        sys.stdout.buffer.write(export_transfer(store))
`;
function python(raw, mode = 'roundtrip') {
  const result = spawnSync(process.env.PYTHON || 'python3', ['-c', script, mode], {
    cwd: path.join(__dirname, '..'), input: JSON.stringify(raw), encoding: 'utf8',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, timeout: 10000, maxBuffer: 8 * 1024 * 1024,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('real JavaScript to Python to JavaScript preserves all supported original bytes and names', async () => {
  const inputs = [
    ['合成早餐🥣.txt', new TextEncoder().encode('\ufeff仅为合成测试\n<&>')],
    ['same.txt', new TextEncoder().encode('first')],
    ['same.txt', new TextEncoder().encode('second')],
    ['PHOTO.JPG', new Uint8Array([255, 216, 255, 0, 1, 2])],
    ['合成.png', new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0])],
    ['report.PDF', new TextEncoder().encode('%PDF-1.7\nsynthetic signature fixture')],
  ];
  const documents = await Promise.all(inputs.map(([name, content]) => core.makeDocument(name, content)));
  const returned = await core.validate(JSON.parse(python(core.pack(documents))));
  const ordered = items => items.slice().sort((left, right) => left.sha256.localeCompare(right.sha256));
  assert.deepEqual(ordered(returned), ordered(documents));
});

test('both runtimes reject malformed transfer filenames, encodings, MIME and schema', async () => {
  const document = await core.makeDocument('synthetic.txt', new TextEncoder().encode('synthetic'));
  const changed = value => core.pack([{ ...document, ...value }]);
  const samples = [
    changed({ filename: 'txt' }), changed({ filename: 'name\t.txt' }), changed({ filename: '../name.txt' }),
    changed({ filename: '\u0085name.txt' }), changed({ filename: '\ufeffname.txt' }),
    changed({ content: document.content + '\n' }), changed({ mime: 'text/html' }), changed({ sha256: '0'.repeat(64) }),
    changed({ extra: 'unknown' }), core.pack([document, document]), { ...core.pack([]), version: true },
  ];
  for (const raw of samples) {
    await assert.rejects(core.validate(raw));
    assert.equal(python(raw, 'validate').trim(), 'rejected');
  }
});
