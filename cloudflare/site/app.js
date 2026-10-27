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

  const SETTINGS_KEY = 'rc_api_settings';

  /* 模型厂家预设：识别接口用视觉模型，抽取接口用文本模型 */
  const PROVIDERS = {
    aliyun: {
      label: '阿里（百炼）',
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      ocr: ['qwen-vl-ocr', 'qwen-vl-max', 'qwen-vl-plus'],
      extract: ['qwen-plus', 'qwen-max', 'qwen-turbo'],
    },
    deepseek: {
      label: 'DeepSeek',
      baseUrl: 'https://api.deepseek.com/v1',
      ocr: ['deepseek-flash'],
      extract: ['deepseek-flash', 'deepseek-v4-pro'],
    },
    moonshot: {
      label: 'Kimi（月之暗面）',
      baseUrl: 'https://api.moonshot.cn/v1',
      ocr: ['moonshot-v1-8k-vision-preview', 'moonshot-v1-32k-vision-preview'],
      extract: ['kimi-k2-0711-preview', 'moonshot-v1-32k', 'moonshot-v1-8k'],
    },
    zhipu: {
      label: 'GLM（智谱）',
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      ocr: ['glm-4v-plus', 'glm-4v'],
      extract: ['glm-4-plus', 'glm-4-air', 'glm-4-flash'],
    },
    doubao: {
      label: '豆包（火山引擎）',
      baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
      ocr: ['doubao-vision-pro-32k', 'doubao-vision-lite-32k'],
      extract: ['doubao-pro-32k', 'doubao-lite-32k'],
    },
    hunyuan: {
      label: '元宝（腾讯混元）',
      baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1',
      ocr: ['hunyuan-vision'],
      extract: ['hunyuan-pro', 'hunyuan-standard'],
    },
    siliconflow: {
      label: '硅基流动',
      baseUrl: 'https://api.siliconflow.cn/v1',
      ocr: ['Qwen/Qwen2.5-VL-72B-Instruct', 'Qwen/Qwen2-VL-72B-Instruct'],
      extract: ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen2.5-72B-Instruct'],
    },
    openai: {
      label: 'OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      ocr: ['gpt-4o', 'gpt-4o-mini'],
      extract: ['gpt-4o', 'gpt-4o-mini'],
    },
    custom: { label: '自定义', baseUrl: '', ocr: [], extract: [] },
  };

  function providerByBaseUrl(baseUrl) {
    const b = (baseUrl || '').replace(/\/+$/, '');
    for (const [key, p] of Object.entries(PROVIDERS)) {
      if (p.baseUrl && p.baseUrl === b) return key;
    }
    return 'custom';
  }

  function fillProviderOptions(el) {
    el.innerHTML = Object.entries(PROVIDERS)
      .map(([key, p]) => `<option value="${key}">${p.label}</option>`).join('');
  }

  /** 按厂家联动 Base URL 与模型候选；keepModel 用于打开弹窗时保留已填模型 */
  function applyProvider(kind, key, { keepModel = false } = {}) {
    const p = PROVIDERS[key] || PROVIDERS.custom;
    const baseEl = $(kind === 'ocr' ? 'ocrBaseUrl' : 'extractBaseUrl');
    const modelEl = $(kind === 'ocr' ? 'ocrModel' : 'extractModel');
    const listEl = $(kind === 'ocr' ? 'ocrModelOptions' : 'extractModelOptions');
    const models = kind === 'ocr' ? p.ocr : p.extract;
    listEl.innerHTML = models.map((m) => `<option value="${m}"></option>`).join('');
    if (p.baseUrl) baseEl.value = p.baseUrl;
    if (!keepModel || !modelEl.value) modelEl.value = models[0] || modelEl.value;
  }

  function getSettings() {
    try {
      return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {};
    } catch {
      return {};
    }
  }

  function saveSettings(obj) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(obj));
  }

  /** 表单值优先，其次本地保存值，最后服务端默认 */
  function currentConfig() {
    const saved = getSettings();
    const d = (state.health && state.health.defaults) || {};
    const ocr = Object.assign({}, d.ocr, saved.ocr);
    const ext = Object.assign({}, d.extract, saved.extract);
    return { ocr, extract: ext };
  }

  function refreshModelLabel() {
    const { ocr, extract } = currentConfig();
    $('modelName').textContent = ocr.model
      ? `${ocr.model} → ${extract.model}`
      : '未设置';
  }

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
    // 与桌面版一致：横向排列的测试项目标签，不按标准分组
    $('tmplList').innerHTML = state.templates.map((t) => `
      <div class="tmpl-item${state.selected.has(t.name) ? ' selected' : ''}"
           data-name="${esc(t.name)}" title="${esc(t.standard || '')} · ${esc(t.description || '')}">
        <span class="tmpl-name">${esc(t.display)}</span>
      </div>`).join('') || '<p class="muted">未找到模板</p>';
    $('tmplCount').textContent = `${state.templates.length} 项`;
  }

  function renderFields() {
    const picked = state.templates.filter((t) => state.selected.has(t.name));
    if (!picked.length) {
      $('fieldCount').textContent = '';
      $('fieldList').innerHTML = '<p class="muted">选择测试项目后显示字段</p>';
      return;
    }
    const t = picked[0];
    const tmpl = t.template;
    let total = 0;

    const blocks = (tmpl.tables || []).map((tb) => {
      const fields = (tb.fields || []).filter((f) => f.name);
      if (!fields.length) return '';
      total += fields.length;
      const title = tb.table_name || tb.title || tb.description || '';
      const headers = (tb.headers || []).map((h) => h.label).filter(Boolean);
      const rows = fields.map((f) => {
        const desc = f.description || f.name;
        const unit = f.unit && !String(desc).includes(f.unit) ? `（${f.unit}）` : '';
        const size = f.array_size ? ` ×${f.array_size}` : '';
        const calc = f.computed ? '<span class="field-tag">计算</span>' : '';
        return `
        <div class="field-item">
          <span class="field-name">${esc(desc)}${esc(unit)}${calc}</span>
          <span class="field-desc">${esc(f.name)}${esc(size)}</span>
        </div>`;
      }).join('');
      return `
      <div class="field-block">
        ${title ? `<div class="field-block-title">${esc(title)}</div>` : ''}
        ${headers.length ? `<div class="field-headers">${headers.map(esc).join(' · ')}</div>` : ''}
        ${rows}
      </div>`;
    }).join('');

    const legacy = (tmpl.fields || []).filter((f) => f.name);
    if (!blocks && legacy.length) {
      total = legacy.length;
      $('fieldList').innerHTML = legacy.map((f) => `
        <div class="field-item">
          <span class="field-name">${esc(f.description || f.name)}</span>
          <span class="field-desc">${esc(f.name)}</span>
        </div>`).join('');
    } else {
      $('fieldList').innerHTML = blocks || '<p class="muted">该模板未定义字段</p>';
    }

    const version = tmpl.version ? ` · v${esc(tmpl.version)}` : '';
    $('fieldCount').textContent = `${total} 项${version}${picked.length > 1 ? `（显示「${t.display}」）` : ''}`;
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
      renderFields();
      syncUi();
    });

    $('btnPrev').addEventListener('click', () => goPage(state.pageIndex - 1));
    $('btnNext').addEventListener('click', () => goPage(state.pageIndex + 1));
    $('btnZoomIn').addEventListener('click', () => setZoom(zoom + 0.1));
    $('btnZoomOut').addEventListener('click', () => setZoom(zoom - 0.1));
    $('btnFit').addEventListener('click', () => { setZoom(1); $('canvasWrap').scrollTop = 0; });
    $('btnCheck').addEventListener('click', runCheck);
    $('btnSettings').addEventListener('click', openSettings);
    $('btnCancelSettings').addEventListener('click', () => $('settingsModal').classList.add('hidden'));
    $('btnSaveSettings').addEventListener('click', saveSettingsFromForm);
    $('btnTest').addEventListener('click', testSettings);
    $('ocrProvider').addEventListener('change', () => applyProvider('ocr', $('ocrProvider').value));
    $('extractProvider').addEventListener('change', () => applyProvider('extract', $('extractProvider').value));
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
    } catch {
      state.health = { ok: false };
    }
    refreshModelLabel();
  }

  function openSettings() {
    const h = state.health || {};
    $('apiStatus').innerHTML = h.ok
      ? `服务端密钥：识别 ${h.hasServerKey.ocr ? '已配置' : '未配置'} / 抽取 ${h.hasServerKey.extract ? '已配置' : '未配置'}` +
        `　访问码：${h.needCode ? '已启用' : '未启用'}`
      : '未连接到服务端';

    const cfg = currentConfig();
    $('ocrBaseUrl').value = cfg.ocr.baseUrl || '';
    $('ocrModel').value = cfg.ocr.model || '';
    $('ocrApiKey').value = cfg.ocr.apiKey || '';
    $('extractBaseUrl').value = cfg.extract.baseUrl || '';
    $('extractModel').value = cfg.extract.model || '';
    $('extractApiKey').value = cfg.extract.apiKey || '';
    fillProviderOptions($('ocrProvider'));
    fillProviderOptions($('extractProvider'));
    $('ocrProvider').value = providerByBaseUrl(cfg.ocr.baseUrl);
    $('extractProvider').value = providerByBaseUrl(cfg.extract.baseUrl);
    applyProvider('ocr', $('ocrProvider').value, { keepModel: true });
    applyProvider('extract', $('extractProvider').value, { keepModel: true });
    $('accessCode').value = accessCode();
    $('testResult').classList.add('hidden');
    $('settingsModal').classList.remove('hidden');
  }

  function collectSettings() {
    return {
      ocr: {
        baseUrl: $('ocrBaseUrl').value.trim(),
        model: $('ocrModel').value.trim(),
        apiKey: $('ocrApiKey').value.trim(),
      },
      extract: {
        baseUrl: $('extractBaseUrl').value.trim(),
        model: $('extractModel').value.trim(),
        apiKey: $('extractApiKey').value.trim(),
      },
    };
  }

  function saveSettingsFromForm() {
    saveSettings(collectSettings());
    const code = $('accessCode').value.trim();
    if (code) localStorage.setItem('rc_access_code', code);
    else localStorage.removeItem('rc_access_code');
    refreshModelLabel();
    $('settingsModal').classList.add('hidden');
    status('接口设置已保存');
  }

  async function testSettings() {
    const box = $('testResult');
    box.className = 'test-line';
    box.textContent = '正在测试…';
    box.classList.remove('hidden');
    const headers = { 'content-type': 'application/json' };
    const code = $('accessCode').value.trim();
    if (code) headers['x-access-code'] = code;
    try {
      const resp = await fetch('/api/test', {
        method: 'POST',
        headers,
        body: JSON.stringify({ settings: collectSettings() }),
      });
      const data = await resp.json();
      box.className = `test-line ${data.ok ? 'ok' : 'fail'}`;
      box.textContent = data.message || (data.ok ? '连接成功' : '连接失败');
    } catch (e) {
      box.className = 'test-line fail';
      box.textContent = `测试失败：${e.message}`;
    }
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
      $('canvasWrap').classList.remove('hidden');
      $('fileBar').textContent = `${file.name} · ${bytes(file.size)} · ${state.pages.length} 页`;
      showPage(0);
      applyZoom();
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

  /* ── 预览缩放 ── */

  let zoom = 1;

  function applyZoom() {
    $('previewImg').style.width = `${zoom * 100}%`;
    $('zoomLabel').textContent = `${Math.round(zoom * 100)}%`;
  }

  function setZoom(z) {
    zoom = Math.min(2.5, Math.max(0.5, Math.round(z * 20) / 20));
    applyZoom();
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
      body: JSON.stringify({ template, images, settings: getSettings() }),
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
