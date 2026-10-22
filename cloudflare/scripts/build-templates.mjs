/**
 * 从 ../templates 生成 public/templates.js
 * 用法：node scripts/build-templates.mjs
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_DIR = resolve(HERE, '../../templates');
const OUT = resolve(HERE, '../public/templates.js');

const DISPLAY_NAMES = {
  clause11_input_power_current: '输入功率和电流',
  clause12_heating: '发热',
  clause26_earthing: '接地装置',
  appendix_d_dielectric_strength: '电气强度与绝缘电阻',
  appendix_c_leakage_current: '泄漏电流',
  clause20_mechanical_strength: '机械强度',
  ip_rating: '外壳防护等级',
  clause25_power_cord_bending: '电缆弯曲测试',
  gb4343_1_emission: 'EMC',
  gb17625_1_harmonic_current: '谐波电流',
  gb17625_2_voltage_flicker: '电压波动和闪烁',
};

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (name.endsWith('.json')) out.push(p);
  }
  return out;
}

const files = walk(TEMPLATE_DIR).sort();
const seen = new Set();
const list = [];

for (const file of files) {
  const name = file.split(/[\\/]/).pop().replace(/\.json$/, '');
  if (seen.has(name)) continue;
  seen.add(name);
  let template;
  try {
    template = JSON.parse(readFileSync(file, 'utf8'));
  } catch (e) {
    console.warn(`跳过无法解析的模板：${file}（${e.message}）`);
    continue;
  }
  const rel = file.slice(TEMPLATE_DIR.length + 1).split(/[\\/]/);
  list.push({
    name,
    standard: template.standard || '',
    standard_dir: rel.length > 1 ? rel[0] : '',
    title: template.title || '',
    description: template.description || '',
    display: DISPLAY_NAMES[name] || template.title || name,
    template,
  });
}

list.sort((a, b) => (a.standard_dir + a.name).localeCompare(b.standard_dir + b.name));

const banner = `/* 自动生成，请勿手工编辑。来源：templates/（共 ${list.length} 个模板） */\n`;
writeFileSync(OUT, banner + `window.REPORT_TEMPLATES = ${JSON.stringify(list, null, 2)};\n`, 'utf8');
console.log(`已生成 ${OUT}，共 ${list.length} 个模板`);
