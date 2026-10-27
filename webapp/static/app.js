/* ReportChecker Web 前端逻辑 */

const state = {
  doc: null,          // {doc_id, name, doc_type, page_count}
  page: 0,
  templates: [],
  selected: new Set(),
  taskId: null,
  polling: null,
};

const $ = (id) => document.getElementById(id);

/* ─────────── Toast ─────────── */
let toastTimer = null;
function toast(msg, ms = 2600) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), ms);
}

/* ─────────── API ─────────── */
async function api(path, opts = {}) {
  const resp = await fetch(path, opts);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `请求失败 ${resp.status}`);
  return data;
}

/* ─────────── 模板列表 ─────────── */
async function loadTemplates() {
  try {
    const { templates } = await api('/api/templates');
    state.templates = templates;
    renderTemplates();
  } catch (e) {
    $('templateList').innerHTML = `<div class="loading">模板加载失败：${e.message}</div>`;
  }
}

const GROUP_NAMES = {
  'GB3883': 'GB 3883.1 通用安全',
  'GB4343': 'GB 4343 EMC',
  'GB4208': 'GB/T 4208 外壳防护',
  'GB17625': 'GB 17625 谐波',
};

function renderTemplates() {
  const box = $('templateList');
  if (!state.templates.length) {
    box.innerHTML = '<div class="loading">未找到模板文件</div>';
    return;
  }
  let html = '';
  let lastGroup = null;
  state.templates.forEach((t) => {
    const g = t.standard_dir || '其他';
    if (g !== lastGroup) {
      lastGroup = g;
      html += `<div class="tmpl-group">${GROUP_NAMES[g] || g}</div>`;
    }
    html += `
      <div class="tmpl-item" data-name="${t.name}">
        <div class="check">✓</div>
        <div>
          <div class="tmpl-name">${t.display || t.title || t.name}</div>
          <div class="tmpl-std">${t.standard || ''} ${t.description || ''}</div>
        </div>
      </div>`;
  });
  box.innerHTML = html;
  box.querySelectorAll('.tmpl-item').forEach((el) => {
    el.addEventListener('click', () => {
      const name = el.dataset.name;
      if (state.selected.has(name)) {
        state.selected.delete(name);
        el.classList.remove('selected');
      } else {
        state.selected.add(name);
        el.classList.add('selected');
      }
      updateCheckBtn();
    });
  });
}

function updateCheckBtn() {
  $('btnCheck').disabled = !(state.doc && state.selected.size > 0);
}

/* ─────────── 上传 ─────────── */
function initUpload() {
  const dz = $('dropZone');
  const input = $('fileInput');
  dz.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    if (input.files.length) uploadFile(input.files[0]);
    input.value = '';
  });
  ['dragover', 'dragenter'].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('dragover'); }));
  ['dragleave', 'drop'].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('dragover'); }));
  dz.addEventListener('drop', (e) => {
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
  });
  $('btnReupload').addEventListener('click', () => input.click());
}

async function uploadFile(file) {
  toast('上传中...');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const info = await api('/api/upload', { method: 'POST', body: fd });
    state.doc = info;
    state.page = 0;
    $('docName').textContent = info.name;
    const typeMap = { pdf_text: '文字型 PDF', pdf_image: '图片型 PDF', word: 'Word', image: '图片' };
    $('docMeta').textContent = `${typeMap[info.doc_type] || info.doc_type} · ${info.page_count} 页`;
    $('docBar').classList.remove('hidden');
    renderPreview();
    updateCheckBtn();
    $('resultArea').innerHTML = '';
    toast('上传成功');
  } catch (e) {
    toast(e.message, 3500);
  }
}

/* ─────────── 预览 ─────────── */
function renderPreview() {
  const wrap = $('previewWrap');
  if (!state.doc) { wrap.classList.add('hidden'); return; }
  wrap.classList.remove('hidden');
  const { doc_id, page_count, doc_type } = state.doc;
  if (doc_type === 'word') {
    wrap.classList.add('hidden');
    return;
  }
  $('previewImg').src = `/api/doc/${doc_id}/page/${state.page}.png?t=${Date.now()}`;
  $('pageIndicator').textContent = `${state.page + 1} / ${page_count}`;
  $('btnPrev').disabled = state.page <= 0;
  $('btnNext').disabled = state.page >= page_count - 1;
}

$('btnPrev').addEventListener('click', () => {
  if (state.page > 0) { state.page--; renderPreview(); }
});
$('btnNext').addEventListener('click', () => {
  if (state.doc && state.page < state.doc.page_count - 1) { state.page++; renderPreview(); }
});

/* ─────────── 校验 ─────────── */
$('btnCheck').addEventListener('click', async () => {
  if (!state.doc || !state.selected.size) return;
  $('resultArea').innerHTML = '';
  showProgress('提交校验任务...');
  try {
    const { task_id } = await api('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_id: state.doc.doc_id, templates: [...state.selected] }),
    });
    state.taskId = task_id;
    pollTask();
  } catch (e) {
    hideProgress();
    toast(e.message, 3500);
  }
});

function showProgress(msg) {
  $('progressBox').classList.remove('hidden');
  $('progressText').textContent = msg;
  $('btnCheck').disabled = true;
}
function hideProgress() {
  $('progressBox').classList.add('hidden');
  updateCheckBtn();
}

function pollTask() {
  clearInterval(state.polling);
  state.polling = setInterval(async () => {
    try {
      const t = await api(`/api/task/${state.taskId}`);
      showProgress(t.progress || '处理中...');
      if (t.status === 'done') {
        clearInterval(state.polling);
        hideProgress();
        renderResults(t.result.checks);
      } else if (t.status === 'error') {
        clearInterval(state.polling);
        hideProgress();
        toast(t.error || '任务失败', 4000);
      }
    } catch (e) {
      clearInterval(state.polling);
      hideProgress();
      toast(e.message, 3500);
    }
  }, 1000);
}

/* ─────────── 结果渲染 ─────────── */
function fmtVal(v) {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return '[' + v.map((x) => (x === null ? '·' : x)).join(', ') + ']';
  return String(v);
}

function renderResults(checks) {
  const area = $('resultArea');
  area.innerHTML = '';
  if (!checks.length) {
    area.innerHTML = '<div class="loading">无校验结果</div>';
    return;
  }
  checks.forEach((c, i) => {
    const card = document.createElement('div');
    card.className = 'result-card';
    let head;
    if (c.error) {
      head = `
        <div class="result-head">
          <div class="result-title">${c.display || c.template}<span class="result-std">${c.standard || ''}</span></div>
          <div class="badges"><span class="badge fail">失败</span></div>
        </div>
        <div class="result-error">${c.error}</div>`;
      card.innerHTML = head;
    } else {
      const s = c.summary;
      head = `
        <div class="result-head" data-idx="${i}">
          <div class="result-title">${c.display || c.template}<span class="result-std">${c.standard || ''}</span></div>
          <div class="badges">
            ${s.pass ? `<span class="badge pass">✓ ${s.pass}</span>` : ''}
            ${s.warn ? `<span class="badge warn">! ${s.warn}</span>` : ''}
            ${s.fail ? `<span class="badge fail">✗ ${s.fail}</span>` : ''}
          </div>
        </div>`;
      const items = c.results.map((r) => `
        <div class="check-item">
          <span class="check-dot ${r.level}"></span>
          <span class="check-msg">${r.message}</span>
        </div>`).join('');
      const rows = Object.entries(c.extracted || {})
        .map(([k, v]) => `<tr><td>${k}</td><td>${fmtVal(v)}</td></tr>`).join('');
      const engineLabel = c.engine === 'docmind' ? 'DocMind 本地规则' : 'AI 视觉模型';
      card.innerHTML = `
        ${head}
        <div class="result-body" id="body-${i}">
          <div class="result-engine">识别引擎：${engineLabel}</div>
          ${items || '<div class="check-item">无规则结果</div>'}
          <div class="extracted-toggle" data-idx="${i}">▸ 查看提取的原始数据</div>
          <div class="hidden" id="ext-${i}">
            <table class="extracted-table">
              <tr><th>字段</th><th>提取值</th></tr>${rows}
            </table>
          </div>
        </div>`;
    }
    area.appendChild(card);
  });

  area.querySelectorAll('.extracted-toggle').forEach((el) => {
    el.addEventListener('click', () => {
      const target = $(`ext-${el.dataset.idx}`);
      const show = target.classList.contains('hidden');
      target.classList.toggle('hidden');
      el.textContent = show ? '▾ 收起原始数据' : '▸ 查看提取的原始数据';
    });
  });

  // 滚动到结果
  area.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ─────────── 识别与接口设置 ─────────── */
let providerPresets = [];
let enginePresets = [];

function applyEngine(key) {
  const engine = enginePresets.find((e) => e.key === key) || enginePresets[0];
  if (!engine) return;
  $('cfgEngine').value = engine.key;
  $('cfgEngineNote').textContent = engine.note || '';
  const isDocmind = engine.key === 'docmind';
  $('sectionDocmind').classList.toggle('hidden', !isDocmind);
  $('sectionAi').classList.toggle('hidden', isDocmind);
}

function fillProviderOptions(current) {
  const sel = $('cfgProvider');
  sel.innerHTML = providerPresets
    .map((p) => `<option value="${p.key}">${p.label}</option>`)
    .join('');
  sel.value = current || 'siliconflow';
  applyProvider(sel.value, false);
}

function applyProvider(key, overwrite) {
  const preset = providerPresets.find((p) => p.key === key);
  if (!preset) return;
  $('cfgProviderNote').textContent = preset.note || '';
  $('cfgModelList').innerHTML = (preset.models || [])
    .map((m) => `<option value="${m}"></option>`).join('');
  if (overwrite) {
    $('cfgBase').value = preset.base_url || '';
    $('cfgModel').value = preset.default_model || '';
  }
}

async function openSettings() {
  try {
    const cfg = await api('/api/config');
    providerPresets = cfg.providers || [];
    enginePresets = cfg.engines || [];
    $('cfgEngine').innerHTML = enginePresets
      .map((e) => `<option value="${e.key}">${e.label}</option>`).join('');
    applyEngine(cfg.engine || 'ai_vision');
    fillProviderOptions(cfg.provider);
    $('cfgBase').value = cfg.base_url;
    $('cfgModel').value = cfg.model;
    $('cfgKey').value = '';
    $('cfgAkId').value = '';
    $('cfgAkSecret').value = '';
    $('cfgKeyHint').textContent = cfg.has_key
      ? `已配置：${cfg.key_masked}（留空表示不修改）`
      : '未配置。硅基流动请填 sk- 开头的 API Key';
    $('cfgAkIdHint').textContent = cfg.has_access_key
      ? `已保存：${cfg.access_key_id_masked}（留空表示不修改）` : '';
    $('cfgAkSecretHint').textContent = cfg.has_access_key
      ? `已保存：${cfg.access_key_secret_masked}（留空表示不修改）` : '';
    $('cfgTestResult').classList.add('hidden');
    $('settingsModal').classList.remove('hidden');
  } catch (e) {
    toast(e.message);
  }
}

function collectConfigBody() {
  const body = {
    engine: $('cfgEngine').value,
    provider: $('cfgProvider').value,
    base_url: $('cfgBase').value.trim(),
    model: $('cfgModel').value.trim(),
  };
  if ($('cfgKey').value.trim()) body.api_key = $('cfgKey').value.trim();
  if ($('cfgAkId').value.trim()) body.access_key_id = $('cfgAkId').value.trim();
  if ($('cfgAkSecret').value.trim()) body.access_key_secret = $('cfgAkSecret').value.trim();
  return body;
}

async function saveConfig() {
  return api('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectConfigBody()),
  });
}

$('btnSettings').addEventListener('click', openSettings);
$('cfgEngine').addEventListener('change', (e) => applyEngine(e.target.value));
$('cfgProvider').addEventListener('change', (e) => applyProvider(e.target.value, true));
$('btnCfgCancel').addEventListener('click', () => $('settingsModal').classList.add('hidden'));

$('btnCfgSave').addEventListener('click', async () => {
  try {
    await saveConfig();
    $('settingsModal').classList.add('hidden');
    toast('已保存');
  } catch (e) {
    toast(e.message, 3500);
  }
});

$('btnCfgTest').addEventListener('click', async () => {
  const box = $('cfgTestResult');
  box.className = 'test-result';
  box.textContent = '正在测试...';
  try {
    await saveConfig();
    const r = await api('/api/config/test', { method: 'POST' });
    box.className = `test-result ${r.ok ? 'ok' : 'fail'}`;
    box.textContent = r.message;
  } catch (e) {
    box.className = 'test-result fail';
    box.textContent = e.message;
  }
});

/* ─────────── 启动 ─────────── */
initUpload();
loadTemplates();
