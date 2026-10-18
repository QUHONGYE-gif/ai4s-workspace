/* Same-origin API client. This ID isolates demo snapshots, not real user accounts. */
const DemoAPI = (() => {
  const sessionKey = 'yanxu-demo-browser-session-v1';
  let session;
  try { session = localStorage.getItem(sessionKey); } catch (_) { /* ephemeral fallback */ }
  if (!/^[a-f0-9]{32}$/.test(session || '')) {
    session = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
    try { localStorage.setItem(sessionKey, session); } catch (_) { /* ephemeral fallback */ }
  }
  const pendingKey = 'yanxu-demo-pending-' + session;
  const localStateKey = 'yanxu-product-loop-v1';
  let revision = 0, pending = null, timer = null, sending = false, blocked = false;
  let inFlight = Promise.resolve();
  function markPending() { try { localStorage.setItem(pendingKey, JSON.stringify({revision})); } catch (_) {} }
  function clearPending() { try { localStorage.removeItem(pendingKey); } catch (_) {} }
  let label = '后端连接中';
  function report(value, error = '') {
    label = value;
    window.dispatchEvent(new CustomEvent('demo-api-status', { detail: { label, error } }));
  }
  async function request(path, options = {}) {
    const response = await fetch(new URL(path, document.baseURI), {
      ...options, credentials: 'same-origin', cache: 'no-store',
      headers: { 'X-Demo-Session': session, ...(options.headers || {}) }
    });
    let body;
    try { body = await response.json(); } catch (_) { throw new Error('后端未返回 JSON；请使用 Python 应用入口启动页面。'); }
    if (!response.ok) {
      const error = new Error(body.error || '后端请求失败');
      error.status = response.status; throw error;
    }
    return body;
  }
  async function flush(keepalive = false) {
    if (sending || blocked || !pending) return;
    const state = pending; pending = null; sending = true;
    try {
      const result = await (inFlight = request('api/demo/state', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision, state }), keepalive
      }));
      revision = result.revision;
      if (pending) markPending(); else clearPending();
      report(pending ? '后端保存中' : '后端已保存');
    } catch (error) {
      pending = pending || state;
      blocked = true; // Keep the local copy; never silently overwrite a newer tab.
      report('后端未同步 · 请先导出', error.status === 409 ? '另一页面已有新版本，请先导出本页记录再刷新。' : '后端保存失败，浏览器副本仍保留；请先导出记录再刷新重试。');
    } finally {
      sending = false;
      if (pending && !blocked) void flush();
    }
  }
  return {
    async bootstrap() { return (await request('api/demo/bootstrap')).fixtures; },
    async loadState() {
      const result = await request('api/demo/state'); revision = result.revision;
      let unsynced = null;
      try { if (localStorage.getItem(localStateKey)) unsynced = JSON.parse(localStorage.getItem(pendingKey)); } catch (_) {}
      result.preferLocal = !!unsynced;
      result.conflict = !!unsynced && unsynced.revision !== revision;
      blocked = result.conflict;
      report(blocked ? '本地修改待处理 · 请先导出' : result.state ? '后端已恢复' : '后端待保存');
      return result;
    },
    async prepareImport() {
      clearTimeout(timer); pending = null;
      try { await inFlight; } catch (_) { /* user explicitly chose recovery */ }
      const result = await request('api/demo/state'); revision = result.revision;
      clearTimeout(timer); pending = null; blocked = false; clearPending();
      return result;
    },
    scheduleSave(state) {
      pending = state;
      if (blocked) return;
      markPending();
      report('后端保存中'); clearTimeout(timer); timer = setTimeout(() => void flush(), 180);
    },
    flush: () => flush(true),
    statusLabel: () => label
  };
})();
