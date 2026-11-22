(function (scope) {
  'use strict';
  function database() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('health-journal-phone-v1', 1);
      let blocked = false;
      request.onupgradeneeded = () => request.result.createObjectStore('vault', { keyPath: 'id' });
      request.onerror = () => reject(new Error('无法打开手机本地数据库，请使用普通浏览模式并检查可用空间'));
      request.onblocked = () => { blocked = true; reject(new Error('数据库升级被其他窗口阻止，请关闭本应用其他窗口后重试')); };
      request.onsuccess = () => { if (blocked) { request.result.close(); return; } request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    });
  }
  async function read() {
    const connection = await database();
    return new Promise((resolve, reject) => {
      const transaction = connection.transaction('vault', 'readonly');
      const request = transaction.objectStore('vault').get('main');
      transaction.oncomplete = () => { connection.close(); resolve(request.result || null); };
      transaction.onabort = transaction.onerror = () => { connection.close(); reject(new Error('本地读取失败，请保留浏览器数据并重试')); };
    });
  }
  async function write(envelope, expectedRevision) {
    const connection = await database();
    return new Promise((resolve, reject) => {
      const transaction = connection.transaction('vault', 'readwrite'), store = transaction.objectStore('vault');
      const current = store.get('main'), revision = crypto.randomUUID();
      let conflict = false;
      current.onsuccess = () => {
        if ((current.result?.revision || null) !== expectedRevision) { conflict = true; transaction.abort(); return; }
        store.put({ id: 'main', revision, envelope });
      };
      transaction.oncomplete = () => { connection.close(); resolve(revision); };
      transaction.onabort = transaction.onerror = () => { connection.close(); reject(new Error(conflict ? '另一窗口已经更新档案。请锁定后重新解锁，再导入；没有覆盖其他窗口的资料' : '保存失败，可能存储空间不足。原档案未改变；请保留原文件并导出已有备份')); };
    });
  }
  scope.PhoneVaultDB = { read, write };
  if (typeof module !== 'undefined') module.exports = scope.PhoneVaultDB;
})(globalThis);
