/**
 * ReportChecker 在线版核心逻辑（Cloudflare Pages Functions）
 *
 * 两部分接口各自独立配置：
 *   识别接口 OCR：页面图像 → 文字（默认阿里百炼 qwen-vl-ocr）
 *   抽取接口 LLM：文字 + 模板字段 → JSON（默认 DeepSeek deepseek-flash）
 */

export const ALLOWED_HOSTS = [
  'dashscope.aliyuncs.com',
  'dashscope-intl.aliyuncs.com',
  'api.deepseek.com',
  'ark.cn-beijing.volces.com',
  'open.bigmodel.cn',
  'api.moonshot.cn',
  'api.hunyuan.cloud.tencent.com',
  'api.openai.com',
  'api.siliconflow.cn',
];

const MAX_IMAGES = 8;
const MAX_IMAGE_CHARS = 8 * 1024 * 1024;

const DEFAULT_OCR = {
  baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  model: 'qwen-vl-ocr',
};
const DEFAULT_EXTRACT = {
  baseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-flash',
};

// 1x1 白色 PNG，仅用于测试识别接口能否读图
const TINY_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

const OCR_PROMPT =
  '你是 OCR 引擎。识别这页图片中的全部文字，按从上到下、从左到右的顺序输出。' +
  '表格按行输出，同一行的单元格之间用 " | " 分隔。' +
  '只输出识别到的原文，不要解释、不要使用 Markdown 代码块。';

export function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

/* ───────────── 配置 ───────────── */

export function health(env) {
  return json({
    ok: true,
    defaults: {
      ocr: {
        baseUrl: env.OCR_BASE_URL || DEFAULT_OCR.baseUrl,
        model: env.OCR_MODEL || DEFAULT_OCR.model,
      },
      extract: {
        baseUrl: env.EXTRACT_BASE_URL || env.AI_BASE_URL || DEFAULT_EXTRACT.baseUrl,
        model: env.EXTRACT_MODEL || DEFAULT_EXTRACT.model,
      },
    },
    hasServerKey: {
      ocr: Boolean(env.OCR_API_KEY),
      extract: Boolean(env.EXTRACT_API_KEY || env.AI_API_KEY),
    },
    needCode: Boolean(env.ACCESS_CODE),
    allowedHosts: ALLOWED_HOSTS,
  });
}

function resolvePair(env, body, kind) {
  const s = (body && typeof body.settings === 'object' && body.settings) || {};
  const sec = (s && typeof s[kind] === 'object' && s[kind]) || {};
  const isOcr = kind === 'ocr';
  const up = isOcr ? 'OCR' : 'EXTRACT';
  const def = isOcr ? DEFAULT_OCR : DEFAULT_EXTRACT;
  const fallbackBase = env.AI_BASE_URL || def.baseUrl;
  const fallbackKey = isOcr ? '' : (env.EXTRACT_API_KEY || env.AI_API_KEY || '');
  return {
    baseUrl: String(sec.baseUrl || env[`${up}_BASE_URL`] || fallbackBase)
      .trim().replace(/\/+$/, ''),
    model: String(sec.model || env[`${up}_MODEL`] || def.model).trim(),
    apiKey: String(sec.apiKey || env[`${up}_API_KEY`] || fallbackKey).trim(),
  };
}

function validatePair(cfg, label) {
  let u;
  try {
    u = new URL(cfg.baseUrl);
  } catch {
    return `${label}：Base URL 格式不正确`;
  }
  if (u.protocol !== 'https:') return `${label}：Base URL 必须使用 https`;
  if (!ALLOWED_HOSTS.includes(u.hostname)) {
    return `${label}：暂不支持域名 ${u.hostname}`;
  }
  if (!cfg.model) return `${label}：未填写模型名称`;
  if (!cfg.apiKey) return `${label}：未填写 API Key`;
  return '';
}

/* ───────────── 模型调用 ───────────── */

function friendlyError(status, detail) {
  const hint = status === 401 ? 'API Key 无效'
    : status === 402 ? '账户余额不足，请先充值'
    : status === 429 ? '请求过于频繁，请稍后重试'
    : `模型接口返回 ${status}`;
  return `${hint}：${detail}`;
}

async function chat(cfg, messages) {
  let resp;
  try {
    resp = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${cfg.apiKey}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ model: cfg.model, temperature: 0, messages }),
    });
  } catch (e) {
    throw new Error(`接口连接失败：${e.message}`);
  }
  if (!resp.ok) {
    const detail = (await resp.text()).slice(0, 300).replace(/\s+/g, ' ');
    throw new Error(friendlyError(resp.status, detail));
  }
  const data = await resp.json().catch(() => null);
  let content = data?.choices?.[0]?.message?.content;
  if (Array.isArray(content)) content = content.map((p) => p.text || '').join('');
  if (!content) throw new Error('模型返回内容为空');
  return String(content);
}

/* ───────────── 模板字段 → 提示词 ───────────── */

function collectFields(template) {
  const fields = [];
  for (const t of template.tables || []) {
    const headers = (t.headers || []).map((h) => h.label || '').filter(Boolean);
    for (const f of t.fields || []) {
      if (!f.name) continue;
      fields.push({
        name: f.name,
        type: f.type || 'text',
        description: f.description || '',
        unit: f.unit || '',
        array_size: f.array_size ?? null,
        computed: Boolean(f.computed),
        table: t.title || '',
        headers,
      });
    }
  }
  for (const f of template.fields || []) {
    const name = f.field_name || f.name;
    if (!name) continue;
    fields.push({
      name,
      type: f.type || 'text',
      description: f.description || '',
      unit: f.unit || '',
      array_size: null,
      computed: false,
      table: '',
      headers: [],
    });
  }
  return fields;
}

function buildPrompt(template, fields) {
  const head = [
    `标准：${template.standard || ''}`,
    `测试项目：${template.title || ''}（${template.description || ''}）`,
  ];
  const lines = [];
  let curTable = null;
  for (const f of fields) {
    if (f.table !== curTable) {
      curTable = f.table;
      if (curTable) {
        const headerStr = f.headers.length ? f.headers.join('、') : '键值对';
        lines.push(`\n◆ 表格「${curTable}」（列：${headerStr}）`);
      }
    }
    const desc = f.description || f.name;
    const unit = f.unit ? `（单位 ${f.unit}）` : '';
    let shape = '文本';
    if (f.type === 'number_array') shape = `数字数组，长度 ${f.array_size || '按表格列数'}`;
    else if (f.type === 'number') shape = '单个数字';
    const note = f.computed ? '；该字段为计算值，若报告中印有记录值则提取，否则填 null' : '';
    lines.push(`  - "${f.name}": ${desc}${unit}，${shape}${note}`);
  }
  return (
    '你是电动工具检测报告的数据提取助手。请阅读提供的报告识别文本，' +
    '提取下列字段并以严格 JSON 输出。\n\n' +
    head.join('\n') + '\n' + lines.join('\n') + '\n\n' +
    '输出要求：\n' +
    '1. 只输出一个 JSON 对象，键为字段英文名，不要输出任何解释、注释或 markdown 代码围栏。\n' +
    '2. 数字字段输出数值（不带单位、不带千分位逗号）；确实找不到的填 null。\n' +
    '3. 数字数组按表格从左到右的顺序输出，缺失的单元格用 null 占位，保持数组长度。\n' +
    '4. 文本字段输出原文。\n' +
    '5. 报告中未出现的字段一律填 null，不要猜测。'
  );
}

/* ───────────── 结果规整 ───────────── */

function parseNumber(text) {
  if (text === null || text === undefined) return null;
  if (typeof text === 'number') return Number.isFinite(text) ? text : null;
  if (typeof text !== 'string') return null;
  const t = text.trim();
  if (!t) return null;
  if (['N/A', 'NA', '无', '—', '-', '合格', 'PASS', 'OK'].includes(t.toUpperCase())) return null;
  const m = t.match(/[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/);
  if (m) {
    const v = parseFloat(m[0].replace(/,/g, ''));
    if (Number.isFinite(v)) return v;
  }
  const m2 = t.match(/(?:≤|≥|<|>)?\s*([-+]?\d[\d.,]*)/);
  if (m2) {
    const v = parseFloat(m2[1].replace(/,/g, ''));
    if (Number.isFinite(v)) return v;
  }
  return null;
}

function coerce(raw, fdef) {
  if (raw === null || raw === undefined) return null;
  if (fdef.type === 'number') return parseNumber(raw);
  if (fdef.type === 'number_array') {
    let items;
    if (Array.isArray(raw)) items = raw;
    else if (typeof raw === 'string') items = raw.split(/[，,、;；\s]+/).filter(Boolean);
    else items = [raw];
    let values = items.map((v) => parseNumber(v));
    if (fdef.array_size) {
      values = values.slice(0, fdef.array_size);
      while (values.length < fdef.array_size) values.push(null);
    }
    return values;
  }
  if (typeof raw === 'string') return raw.trim() || null;
  return String(raw);
}

function extractJson(text) {
  let s = String(text || '').trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) s = fence[1].trim();
  const start = s.indexOf('{');
  const end = s.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  const body = s.slice(start, end + 1);
  try {
    return JSON.parse(body);
  } catch {
    try {
      return JSON.parse(body.replace(/,\s*([}\]])/g, '$1'));
    } catch {
      return null;
    }
  }
}

/* ───────────── 接口实现 ───────────── */

function checkAccess(request, env) {
  if (!env.ACCESS_CODE) return '';
  const code = request.headers.get('x-access-code') || '';
  return code === env.ACCESS_CODE ? '' : '访问码不正确';
}

export async function handleTest(request, env) {
  const denied = checkAccess(request, env);
  if (denied) return json({ ok: false, message: denied });

  let body = {};
  try {
    body = await request.json();
  } catch {
    /* 允许空请求体 */
  }
  const ocr = resolvePair(env, body, 'ocr');
  const ext = resolvePair(env, body, 'extract');

  const ocrErr = validatePair(ocr, '识别接口');
  const extErr = validatePair(ext, '抽取接口');
  if (ocrErr || extErr) {
    return json({ ok: false, message: [ocrErr, extErr].filter(Boolean).join('；') });
  }

  const results = [];
  let allOk = true;

  try {
    await chat(ocr, [{
      role: 'user',
      content: [
        { type: 'text', text: '这张图是什么颜色？只回复一个词。' },
        { type: 'image_url', image_url: { url: TINY_PNG } },
      ],
    }]);
    results.push(`识别接口可用（${ocr.model}）`);
  } catch (e) {
    allOk = false;
    results.push(`识别接口失败：${e.message}`);
  }

  try {
    await chat(ext, [{ role: 'user', content: '回复 OK' }]);
    results.push(`抽取接口可用（${ext.model}）`);
  } catch (e) {
    allOk = false;
    results.push(`抽取接口失败：${e.message}`);
  }

  return json({ ok: allOk, message: results.join('；') });
}

export async function handleExtract(request, env) {
  const denied = checkAccess(request, env);
  if (denied) return json({ ok: false, error: denied }, 401);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: '请求体不是合法 JSON' }, 400);
  }

  const ocr = resolvePair(env, body, 'ocr');
  const ext = resolvePair(env, body, 'extract');
  const cfgError = validatePair(ocr, '识别接口') || validatePair(ext, '抽取接口');
  if (cfgError) return json({ ok: false, error: cfgError }, 400);

  const template = body.template;
  if (!template || typeof template !== 'object') return json({ ok: false, error: '缺少模板' }, 400);

  const images = Array.isArray(body.images) ? body.images.slice(0, MAX_IMAGES) : [];
  for (const img of images) {
    if (typeof img !== 'string' || img.length > MAX_IMAGE_CHARS) {
      return json({ ok: false, error: '图片过大或格式错误' }, 413);
    }
  }
  const extraText = typeof body.text === 'string' ? body.text.slice(0, 20000) : '';
  if (!images.length && !extraText) return json({ ok: false, error: '没有可识别的页面' }, 400);

  const fields = collectFields(template);
  if (!fields.length) return json({ ok: false, error: '模板中未定义任何字段' }, 400);

  try {
    // 第一段：识别
    const pageTexts = await Promise.all(images.map((img) =>
      chat(ocr, [{
        role: 'user',
        content: [
          { type: 'text', text: OCR_PROMPT },
          { type: 'image_url', image_url: { url: img } },
        ],
      }])
    ));

    const parts = [];
    pageTexts.forEach((t, i) => {
      if (t && t.trim()) parts.push(`【第 ${i + 1} 页】\n${t.trim()}`);
    });
    if (extraText) parts.push(`【文本层】\n${extraText}`);
    const ocrText = parts.join('\n\n').slice(0, 60000);
    if (!ocrText) return json({ ok: false, error: '未识别到文字，请检查图片清晰度' }, 422);

    // 第二段：字段抽取
    const prompt = buildPrompt(template, fields);
    const raw = await chat(ext, [
      { role: 'system', content: '你是严谨的数据提取助手，只输出 JSON。' },
      { role: 'user', content: `${prompt}\n\n报告识别文本：\n${ocrText}` },
    ]);

    const obj = extractJson(raw);
    if (!obj) return json({ ok: false, error: '模型输出无法解析为 JSON，请重试' }, 502);

    const extracted = {};
    for (const f of fields) extracted[f.name] = coerce(obj[f.name], f);
    return json({ ok: true, extracted, ocrModel: ocr.model, extractModel: ext.model });
  } catch (e) {
    return json({ ok: false, error: e.message || '识别失败' }, 502);
  }
}
