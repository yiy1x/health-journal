const test = require('node:test');
const assert = require('node:assert/strict');
const storage = require('../health_journal/web/phone/db.js');

function syntheticIDB() {
  let row = null, fail = false;
  const connection = {
    close() {},
    transaction() {
      let aborted = false, pending;
      const transaction = {
        abort() { aborted = true; setImmediate(() => transaction.onabort?.()); },
        objectStore() {
          return {
            get() {
              const request = {};
              setImmediate(() => {
                request.result = row ? structuredClone(row) : undefined;
                request.onsuccess?.();
                setImmediate(() => {
                  if (aborted) return;
                  if (fail && pending) { transaction.abort(); return; }
                  if (pending) row = structuredClone(pending);
                  transaction.oncomplete?.();
                });
              });
              return request;
            },
            put(value) { pending = value; },
          };
        },
      };
      return transaction;
    },
  };
  return {
    open() { const request = {}; setImmediate(() => { request.result = connection; request.onsuccess?.(); }); return request; },
    failNext() { fail = true; },
    current() { return row; },
  };
}

test('phone IndexedDB adapter stores only encrypted envelope and revision', async () => {
  global.indexedDB = syntheticIDB();
  assert.equal(await storage.read(), null);
  const envelope = { ciphertext: 'synthetic-encrypted-content' };
  const revision = await storage.write(envelope, null);
  const row = await storage.read();
  assert.deepEqual(row, { id: 'main', revision, envelope });
  assert.deepEqual(Object.keys(row).sort(), ['envelope', 'id', 'revision']);
});

test('phone stale window cannot overwrite a newer revision', async () => {
  global.indexedDB = syntheticIDB();
  const initial = await storage.write({ ciphertext: 'one' }, null);
  const newer = await storage.write({ ciphertext: 'two' }, initial);
  await assert.rejects(storage.write({ ciphertext: 'stale' }, initial), /另一窗口/);
  assert.equal((await storage.read()).revision, newer);
  assert.equal((await storage.read()).envelope.ciphertext, 'two');
});

test('phone creation race cannot replace an existing vault', async () => {
  global.indexedDB = syntheticIDB();
  const revision = await storage.write({ ciphertext: 'keep' }, null);
  await assert.rejects(storage.write({ ciphertext: 'replace' }, null), /另一窗口/);
  assert.equal((await storage.read()).revision, revision);
});

test('phone aborted transaction retains prior envelope', async () => {
  global.indexedDB = syntheticIDB();
  const revision = await storage.write({ ciphertext: 'keep' }, null);
  global.indexedDB.failNext();
  await assert.rejects(storage.write({ ciphertext: 'new' }, revision), /保存失败/);
  assert.equal(global.indexedDB.current().envelope.ciphertext, 'keep');
  assert.equal(global.indexedDB.current().revision, revision);
});
