(function (scope) {
  'use strict';
  const MAX_FILE = 20 * 1024 * 1024, MAX_TOTAL = 40 * 1024 * 1024, MAX_TRANSFER = 58 * 1024 * 1024, MAX_SEALED = 80 * 1024 * 1024;
  const ITERATIONS = 600000;
  const encoder = new TextEncoder();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  function exact(value, keys) { return value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join('|') === [...keys].sort().join('|'); }
  function base64(bytes) {
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
    return btoa(binary);
  }
  function unbase64(value, maximum) {
    if (typeof value !== 'string' || value.length > Math.ceil(maximum / 3) * 4 || value.length % 4 || /[^A-Za-z0-9+/=]/.test(value)) throw new Error('文件编码无效或超过限制');
    let binary;
    try { binary = atob(value); } catch { throw new Error('文件编码无效'); }
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    if (bytes.length > maximum || base64(bytes) !== value) throw new Error('文件编码无效或超过限制');
    return bytes;
  }
  function filename(value, legacy = false) {
    if (typeof value !== 'string' || !value.trim() || value !== value.trim() || [...value].length > 180 || /^[.]/.test(value) || /[\u0000-\u001f\u007f/\\<>:"|?*]/.test(value) || /[\uD800-\uDFFF]/u.test(value) || (!legacy && /[\u0080-\u009f\ufeff]/.test(value))) throw new Error('文件名无效；请使用简短名称，不含路径或特殊符号');
    return value;
  }
  function restoredFilename(value) {
    const name = filename(value, true).replace(/[\u0080-\u009f\ufeff]/g, '_');
    return /^(txt|pdf|png|jpe?g)$/i.test(name) ? '原件.' + name : name;
  }
  function documentType(name, bytes) {
    filename(name);
    if (!bytes.length || bytes.length > MAX_FILE) throw new Error('文件为空或超过 20 MB');
    const extension = name.includes('.') ? name.split('.').at(-1).toLowerCase() : '';
    if (extension === 'txt') {
      let content;
      try { content = decoder.decode(bytes); } catch { throw new Error('文字文件须使用 UTF-8 编码'); }
      if (content.includes('\0')) throw new Error('文字中含无效字符');
      return 'text/plain';
    }
    const signatures = { pdf: [[37, 80, 68, 70, 45], 'application/pdf'], png: [[137, 80, 78, 71, 13, 10, 26, 10], 'image/png'], jpg: [[255, 216, 255], 'image/jpeg'], jpeg: [[255, 216, 255], 'image/jpeg'] };
    const signature = signatures[extension];
    if (!signature) throw new Error('支持 JPG、PNG、PDF、TXT。HEIC/HEIF 请先导出为 JPG，保留原图；本应用不会偷偷转换');
    if (!signature[0].every((byte, index) => bytes[index] === byte)) throw new Error('文件内容与扩展名不一致');
    return signature[1];
  }
  async function digest(bytes) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join(''); }
  async function makeDocument(name, bytes) { return { filename: filename(name), mime: documentType(name, bytes), sha256: await digest(bytes), content: base64(bytes) }; }
  function pack(documents) { return { format: 'health-journal-transfer', version: 1, documents }; }
  async function validate(raw, restoreLegacyNames = false) {
    if (!exact(raw, ['format', 'version', 'documents']) || raw.format !== 'health-journal-transfer' || raw.version !== 1 || !Array.isArray(raw.documents) || raw.documents.length > 500) throw new Error('不支持的资料互传格式或数量；最多 500 份');
    let total = 0;
    const documents = [], seen = new Set();
    for (const item of raw.documents) {
      if (!exact(item, ['filename', 'mime', 'sha256', 'content'])) throw new Error('原件结构无效');
      const bytes = unbase64(item.content, MAX_FILE);
      total += bytes.length;
      if (total > MAX_TOTAL) throw new Error('原件合计超过 40 MB，请分开保管');
      const name = restoreLegacyNames ? restoredFilename(item.filename) : item.filename;
      if (documentType(name, bytes) !== item.mime || await digest(bytes) !== item.sha256 || seen.has(item.sha256)) throw new Error('原件校验失败或重复；未合并任何资料');
      seen.add(item.sha256);
      documents.push({ filename: name, mime: item.mime, sha256: item.sha256, content: item.content });
    }
    return documents;
  }
  function merge(existing, incoming) {
    const documents = [...existing], seen = new Map(existing.map(item => [item.sha256, item]));
    let added = 0, duplicates = 0, renamed = 0;
    for (const item of incoming) {
      if (seen.has(item.sha256)) { duplicates++; if (seen.get(item.sha256).filename !== item.filename) renamed++; }
      else { seen.set(item.sha256, item); documents.push(item); added++; }
    }
    if (documents.length > 500 || documents.reduce((sum, item) => sum + item.content.length / 4 * 3 - (item.content.endsWith('==') ? 2 : item.content.endsWith('=') ? 1 : 0), 0) > MAX_TOTAL) throw new Error('合并后超过 500 份或 40 MB；未写入资料');
    return { documents, added, duplicates, renamed };
  }
  function passwordCheck(password) { if (typeof password !== 'string' || password.trim().length < 12 || password.length > 256) throw new Error('请使用 12–256 字符的长密码，不要使用姓名或生日'); }
  async function derive(password, salt) {
    passwordCheck(password);
    const material = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: ITERATIONS, hash: 'SHA-256' }, material, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  }
  function header(salt) { return { format: 'health-journal-sealed', version: 1, kdf: 'PBKDF2-SHA256', iterations: ITERATIONS, cipher: 'AES-256-GCM', salt: base64(salt) }; }
  async function seal(documents, key, salt) {
    const metadata = header(salt), iv = crypto.getRandomValues(new Uint8Array(12));
    const data = encoder.encode(JSON.stringify(pack(documents)));
    if (data.length > MAX_TRANSFER) throw new Error('加密前数据过大');
    const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: encoder.encode(JSON.stringify(metadata)), tagLength: 128 }, key, data);
    return { ...metadata, iv: base64(iv), ciphertext: base64(new Uint8Array(encrypted)) };
  }
  async function open(envelope, password) {
    if (!exact(envelope, ['format', 'version', 'kdf', 'iterations', 'cipher', 'salt', 'iv', 'ciphertext']) || envelope.format !== 'health-journal-sealed' || envelope.version !== 1 || envelope.kdf !== 'PBKDF2-SHA256' || envelope.iterations !== ITERATIONS || envelope.cipher !== 'AES-256-GCM') throw new Error('不支持的加密备份格式');
    const salt = unbase64(envelope.salt, 16), iv = unbase64(envelope.iv, 12), ciphertext = unbase64(envelope.ciphertext, MAX_TRANSFER + 16);
    if (salt.length !== 16 || iv.length !== 12 || ciphertext.length < 16) throw new Error('加密参数无效');
    const key = await derive(password, salt);
    let plaintext;
    try { plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv, additionalData: encoder.encode(JSON.stringify(header(salt))), tagLength: 128 }, key, ciphertext); }
    catch { throw new Error('密码不正确，或加密文件已损坏；原档案没有改变'); }
    const raw = JSON.parse(decoder.decode(plaintext));
    const documents = await validate(raw, true);
    const renamed = documents.filter((item, index) => item.filename !== raw.documents[index].filename).length;
    return { documents, key, salt, renamed };
  }
  function suggest(item, catalog) {
    const body = item.mime === 'text/plain' ? decoder.decode(unbase64(item.content, MAX_FILE)).slice(0, 60000) : '';
    const haystack = (item.filename + '\n' + body).toLowerCase();
    return catalog.filter(department => department.keywords.some(word => haystack.includes(word.toLowerCase()))).slice(0, 12).map(department => department.name);
  }
  const api = { MAX_FILE, MAX_TOTAL, MAX_TRANSFER, MAX_SEALED, base64, unbase64, filename, documentType, digest, makeDocument, pack, validate, merge, passwordCheck, derive, seal, open, suggest };
  scope.PhoneVaultCore = api;
  if (typeof module !== 'undefined') module.exports = api;
})(globalThis);
