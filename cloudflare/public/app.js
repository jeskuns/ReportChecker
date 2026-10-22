/* ReportChecker 网页版：PDF 转图 → Worker 识别+抽取 → 本地规则校验 */

(function () {
  const $ = (id) => document.getElementById(id);

  const MAX_PAGES = 10;
  const BATCH_PAGES = 4;
  const RENDER_WIDTH = 1400;
  const JPEG_QUALITY = 0.85;

  const state = {
    templates: window.REPORT_TEMPLATES || [],
    selected: new Set(),
    pages: [],
    pageIndex: 0,
    fileName: '',
    running: false,
    health: null,
  };

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  const accessCode = () => localStorage.getItem('rc_access_code') || '';

  function status(text) {
    $('statusText').textContent = text;
  }

  function setProgress(pct, text) {
    $('progressBox').classList.remove('hidden');
    $('progressBar').style.width = `${Math.max(2, Math.min(100, pct))}%`;
    if (text) $('progressText').textContent = text;
    if (text) status(text);
  }

  function hideProgress() {
    setTimeout(() => $('progressBox').classList.add('hidden'), 700);
  }

  const bytes = (n) => (n < 1024 ? `${n} B`
    : n < 1048576 ? `${(n / 1024).toFixed(0)} KB`
    : `${(n / 1048576).toFixed(1)} MB`);

  /* ── 初始化 ── */

  function init() {
    renderTemplates();
    bindEvents();
    loadHealth();
    syncUi();
  }

  function renderTemplates() {
    const groups = new Map();
    for (const t of state.templates) {
      const key = t.standard || '其他';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(t);
    }
    $('tmplList').innerHTML = [...groups.entries()].map(([std, list]) => `
      <div class="tmpl-group">
        <h4>${esc(std)}</h4>
        ${list.map((t) => `
          <div class="tmpl-item" data-name="${esc(t.name)}">
            <span class="tmpl-check"></span>
            <span>
              <span class="tmpl-name">${esc(t.display)}</span><br>
              <span class="tmpl-sub">${esc(t.description || '')}</span>
            </span>
          </div>`).join('')}
      </div>`).join('') || '<p class="muted">未找到模板</p>';
    $('tmplCount').textContent = `${state.templates.length} 项`;
  }

  function bindEvents() {
    const input = $('fileInput') || createFileInput();
    $('btnOpen').addEventListener('click', () => input.click());
    $('dropZone').addEventListener('click', () => input.click());
    $('previewImg').addEventListener('click', () => input.click());
    input.addEventListener('change', (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) handleFile(f);
      input.value = '';
    });

    const dz = $('dropZone');
    ['dragenter', 'dragover'].forEach((ev) =>
      dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach((ev) =>
      dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('dragover'); }));
    dz.addEventListener('drop', (e) => {
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) handleFile(f);
    });

    $('tmplList').addEventListener('click', (e) => {
      const item = e.target.closest('.tmpl-item');
      if (!item) return;
      const name = item.dataset.name;
      if (state.selected.has(name)) state.selected.delete(name);
      else state.selected.add(name);
      item.classList.toggle('selected', state.selected.has(name));
      syncUi();
    });

    $('btnPrev').addEventListener('click', () => goPage(state.pageIndex - 1));
    $('btnNext').addEventListener('click', () => goPage(state.pageIndex + 1));
    $('btnCheck').addEventListener('click', runCheck);
    $('btnSettings').addEventListener('click', openSettings);
    $('btnCancelSettings').addEventListener('click', () => $('settingsModal').classList.add('hidden'));
    $('btnSaveSettings').addEventListener('click', () => {
      const code = $('accessCode').value.trim();
      if (code) localStorage.setItem('rc_access_code', code);
      else localStorage.removeItem('rc_access_code');
      $('settingsModal').classList.add('hidden');
      status('接口设置已保存');
    });
  }

  function createFileInput() {
    const el = document.createElement('input');
    el.type = 'file';
    el.id = 'fileInput';
    el.accept = 'application/pdf,image/*';
    el.hidden = true;
    document.body.appendChild(el);
    return el;
  }

  function syncUi() {
    $('btnCheck').disabled = state.running || !state.pages.length || !state.selected.size;
    $('pageLabel').textContent = state.pages.length ? `${state.pageIndex + 1}/${state.pages.length}` : '0/0';
    $('btnPrev').disabled = state.pageIndex <= 0;
    $('btnNext').disabled = state.pageIndex >= state.pages.length - 1;
  }

  /* ── 服务状态 ── */

  async function loadHealth() {
    try {
      const r = await fetch('/api/health');
      state.health = await r.json();
      const h = state.health || {};
      $('modelName').textContent = h.ok ? `${h.ocrModel} → ${h.extractModel}` : '未连接';
    } catch {
      $('modelName').textContent = '未连接';
    }
  }

  function openSettings() {
    const h = state.health || {};
    $('apiStatus').innerHTML = h.ok
      ? `识别模型：<b>${esc(h.ocrModel)}</b><br>抽取模型：<b>${esc(h.extractModel)}</b><br>` +
        `接口：${esc(h.base)}<br>服务端密钥：${h.hasKey ? '已配置' : '未配置'}`
      : '无法连接服务端。';
    $('accessCode').value = accessCode();
    $('settingsModal').classList.remove('hidden');
  }

  /* ── 文件 ── */

  async function handleFile(file) {
    const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
    if (!isPdf && !file.type.startsWith('image/')) {
      alert('请选择 PDF 或图片文件');
      return;
    }

    state.fileName = file.name;
    state.pages = [];
    state.pageIndex = 0;
    $('results').innerHTML = '';
    $('progressBox').classList.add('hidden');
    status(`正在读取 ${file.name}…`);

    try {
      if (isPdf) await loadPdf(file);
      else await loadImage(file);

      $('dropZone').classList.add('hidden');
      $('previewImg').classList.remove('hidden');
      $('fileBar').classList.remove('hidden');
      $('fileBar').innerHTML =
        `<span>${esc(file.name)} · ${bytes(file.size)}</span><span>${state.pages.length} 页</span>`;
      showPage(0);
      status(`已打开：${file.name}（${state.pages.length} 页）`);
    } catch (e) {
      status(`读取失败：${e.message}`);
      alert(`读取失败：${e.message}`);
    }
    syncUi();
  }

  async function loadPdf(file) {
    if (!window.pdfjsLib) throw new Error('PDF 解析库未加载，请检查网络后刷新');
    const buf = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    const total = Math.min(pdf.numPages, MAX_PAGES);

    for (let i = 1; i <= total; i++) {
      const page = await pdf.getPage(i);
      const base = page.getViewport({ scale: 1 });
      const scale = Math.min(2.2, RENDER_WIDTH / base.width);
      const vp = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(vp.width);
      canvas.height = Math.round(vp.height);
      await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
      state.pages.push(canvas.toDataURL('image/jpeg', JPEG_QUALITY));
      status(`正在渲染第 ${i}/${total} 页…`);
    }
  }

  async function loadImage(file) {
    let bitmap;
    try {
      bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    } catch {
      bitmap = await createImageBitmap(file);
    }
    const scale = Math.min(1, RENDER_WIDTH / bitmap.width);
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    state.pages.push(canvas.toDataURL('image/jpeg', JPEG_QUALITY));
  }

  function showPage(i) {
    if (i < 0 || i >= state.pages.length) return;
    state.pageIndex = i;
    $('previewImg').src = state.pages[i];
    syncUi();
  }

  function goPage(i) {
    showPage(i);
  }

  /* ── 校验 ── */

  function mergeExtracted(base, extra) {
    for (const [key, val] of Object.entries(extra || {})) {
      if (val === null || val === undefined) continue;
      const old = base[key];
      if (old === null || old === undefined) {
        base[key] = val;
      } else if (Array.isArray(old) && Array.isArray(val)) {
        const len = Math.max(old.length, val.length);
        base[key] = Array.from({ length: len }, (_, i) => {
          const a = i < old.length ? old[i] : null;
          const b = i < val.length ? val[i] : null;
          return a !== null && a !== undefined ? a : b;
        });
      }
    }
    return base;
  }

  async function callExtract(template, images) {
    const headers = { 'content-type': 'application/json' };
    const code = accessCode();
    if (code) headers['x-access-code'] = code;
    const resp = await fetch('/api/extract', {
      method: 'POST',
      headers,
      body: JSON.stringify({ template, images }),
    });
    let data;
    try {
      data = await resp.json();
    } catch {
      throw new Error(`服务返回 ${resp.status}`);
    }
    if (!resp.ok || !data.ok) throw new Error(data.error || `服务返回 ${resp.status}`);
    return data.extracted || {};
  }

  async function runCheck() {
    const picked = state.templates.filter((t) => state.selected.has(t.name));
    if (!picked.length || !state.pages.length) return;

    state.running = true;
    syncUi();
    $('results').innerHTML = '';
    $('btnCheck').textContent = '校验中…';

    const batches = [];
    for (let i = 0; i < state.pages.length; i += BATCH_PAGES) {
      batches.push(state.pages.slice(i, i + BATCH_PAGES));
    }

    const totalSteps = picked.length * batches.length;
    let step = 0;

    try {
      for (const t of picked) {
        let extracted = {};
        for (let bi = 0; bi < batches.length; bi++) {
          step += 1;
          setProgress((step / totalSteps) * 90,
            `识别「${t.display}」第 ${bi + 1}/${batches.length} 批…`);
          const part = await callExtract(t.template, batches[bi]);
          extracted = mergeExtracted(extracted, part);
        }
        setProgress(95, `校验「${t.display}」规则…`);
        renderResult(t, extracted);
      }
      setProgress(100, '校验完成');
    } catch (e) {
      renderError(e.message);
      status(`校验失败：${e.message}`);
    } finally {
      state.running = false;
      $('btnCheck').textContent = '开始校验';
      syncUi();
      hideProgress();
    }
  }

  function renderResult(t, extracted) {
    const outcome = window.ReportRules.checkRules(t.template, extracted);
    const { summary } = outcome;
    const overall = summary.fail > 0 ? 'fail' : (summary.warn > 0 ? 'warn' : 'pass');
    const label = { pass: '通过', warn: '需关注', fail: '不通过' }[overall];

    const items = outcome.results.map((r) => `
      <div class="check-item">
        <span class="dot ${r.level}"></span>
        <span class="msg">${esc(r.message)}</span>
      </div>`).join('')
      || '<div class="check-item"><span class="dot warn"></span><span class="msg">未识别到可校验的数据</span></div>';

    const card = document.createElement('div');
    card.className = 'result-card';
    card.innerHTML = `
      <div class="result-head">
        <h3>${esc(t.display)}</h3>
        <span class="badge ${overall}">${label}</span>
        <div class="stats">
          <span>通过 <b>${summary.pass}</b></span>
          <span>警告 <b>${summary.warn}</b></span>
          <span>不通过 <b>${summary.fail}</b></span>
        </div>
      </div>
      <div>${items}</div>
      <div class="toggle">▸ 原始数据</div>
      <div class="raw hidden">${esc(JSON.stringify(extracted, null, 2))}</div>`;

    const toggle = card.querySelector('.toggle');
    const raw = card.querySelector('.raw');
    toggle.addEventListener('click', () => {
      const hidden = raw.classList.toggle('hidden');
      toggle.textContent = hidden ? '▸ 原始数据' : '▾ 收起数据';
    });

    $('results').appendChild(card);
    status(`「${t.display}」完成：通过 ${summary.pass} · 警告 ${summary.warn} · 不通过 ${summary.fail}`);
  }

  function renderError(msg) {
    const card = document.createElement('div');
    card.className = 'result-card';
    card.innerHTML = `<div class="result-head"><h3>校验失败</h3></div>
      <p class="result-error">${esc(msg)}</p>`;
    $('results').appendChild(card);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
