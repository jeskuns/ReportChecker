/**
 * 规则校验引擎（浏览器端）
 * 与桌面版 / Python Web 版规则语义一致：
 *   formula_verify 公式计算值 vs 报告值（容差）
 *   limit          限值判定（支持数组逐元素）
 *   tolerance      两字段差值判定
 */

(function (global) {
  const SAFE = {
    abs: Math.abs,
    min: Math.min,
    max: Math.max,
    round: Math.round,
    sqrt: Math.sqrt,
    pow: Math.pow,
    log: Math.log,
    log10: Math.log10,
    pi: Math.PI,
    e: Math.E,
  };
  const SAFE_NAMES = Object.keys(SAFE);

  function flatten(extracted) {
    const flat = Object.assign({}, extracted);
    for (const [key, val] of Object.entries(extracted || {})) {
      if (Array.isArray(val)) {
        val.forEach((v, i) => {
          if (v !== null && v !== undefined) flat[`${key}_${i}`] = v;
        });
      }
    }
    return flat;
  }

  function getValue(store, ref) {
    if (!ref) return null;
    const val = store[ref];
    if (val !== null && val !== undefined) return val;
    const m = /^(.+?)_(\d+)$/.exec(ref);
    if (m) {
      const arr = store[m[1]];
      const idx = Number(m[2]);
      if (Array.isArray(arr) && idx < arr.length) return arr[idx];
    }
    return null;
  }

  function setIndexed(store, ref, value) {
    store[ref] = value;
    const m = /^(.+?)_(\d+)$/.exec(ref);
    if (!m) return;
    const base = m[1];
    const idx = Number(m[2]);
    if (!Array.isArray(store[base])) store[base] = [];
    const arr = store[base];
    while (arr.length <= idx) arr.push(null);
    arr[idx] = value;
  }

  /** 安全计算公式；变量缺失返回 null，含数组时逐元素计算 */
  function evalFormula(formula, flat) {
    if (!formula) return null;
    const tokens = [...new Set(
      (formula.match(/[a-zA-Z_]\w*/g) || []).filter((t) => !SAFE_NAMES.includes(t))
    )];
    if (!tokens.length) return null;
    const values = tokens.map((t) => flat[t]);
    const hasList = values.some(Array.isArray);

    let fn;
    try {
      fn = new Function(...SAFE_NAMES, ...tokens, `"use strict"; return (${formula});`);
    } catch {
      return null;
    }

    const evalOne = (vals) => {
      const safeVals = SAFE_NAMES.map((n) => SAFE[n]);
      for (const v of vals) {
        if (typeof v !== 'number' || !Number.isFinite(v)) return null;
      }
      try {
        const r = fn(...safeVals, ...vals.map(Number));
        return typeof r === 'number' && Number.isFinite(r) ? r : null;
      } catch {
        return null;
      }
    };

    if (hasList) {
      const maxLen = Math.max(0, ...values.filter(Array.isArray).map((v) => v.length));
      const out = [];
      for (let i = 0; i < maxLen; i++) {
        const elem = values.map((v) => (Array.isArray(v) ? (i < v.length ? v[i] : null) : v));
        out.push(evalOne(elem));
      }
      return out.some((v) => v !== null) ? out : null;
    }
    return evalOne(values);
  }

  function compare(calc, report, pct, absTol) {
    const diff = Math.abs(calc - report);
    if (absTol !== null && absTol !== undefined) return diff <= absTol;
    if (report !== 0) return (diff / Math.abs(report)) * 100 <= pct;
    return diff <= 0.01;
  }

  function checkLimit(val, limit, op) {
    switch (op) {
      case '<=': return val <= limit;
      case '<': return val < limit;
      case '>=': return val >= limit;
      case '>': return val > limit;
      case '==': return Math.abs(val - limit) < 0.01;
      default: return false;
    }
  }

  function fmt(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
    return String(v);
  }

  const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

  function checkRules(template, extracted) {
    const results = [];
    const computed = {};
    const flat = flatten(extracted);
    const rules = template.rules || [];

    // 第一遍：计算所有公式值，供后续 limit 引用
    for (const rule of rules) {
      if (rule._comment || rule.type !== 'formula_verify') continue;
      const output = rule.field_name || rule.output_field || rule.result_field || '';
      if (!rule.formula || !output) continue;
      const calc = evalFormula(rule.formula, Object.assign({}, flat, flatten(computed)));
      if (calc !== null) setIndexed(computed, output, calc);
    }
    const flatAll = Object.assign({}, flat, flatten(computed));

    for (const rule of rules) {
      if (rule._comment || !rule.type) continue;
      const type = rule.type;
      const desc = rule.description || rule.message || '';

      if (type === 'formula_verify') {
        const output = rule.field_name || rule.output_field || rule.result_field || '';
        const reportSource = rule.report_field || output;
        const pct = rule.tolerance_pct ?? 5.0;
        const absTol = rule.tolerance;
        const calcVal = getValue(computed, output);
        const reportVal = getValue(Object.assign({}, extracted, flatAll), reportSource);

        if (calcVal === null && reportVal === null) {
          results.push({ level: 'fail', ruleType: type, field: output, description: desc, calc: '—', report: '—', message: `${desc}：计算与识别均无数据` });
        } else if (calcVal === null) {
          results.push({ level: 'fail', ruleType: type, field: output, description: desc, calc: '—（计算失败）', report: fmt(reportVal), message: `${desc}：公式计算失败（缺参数）` });
        } else if (reportVal === null) {
          results.push({ level: 'warn', ruleType: type, field: output, description: desc, calc: fmt(calcVal), report: '—（报告未记录）', message: `${desc}：计算值 ${fmt(calcVal)}，报告未记录该值` });
        } else {
          let pairs = [];
          if (Array.isArray(calcVal) && Array.isArray(reportVal)) {
            pairs = calcVal.map((cv, i) => [i, cv, reportVal[i]]);
          } else if (isNum(calcVal) && isNum(reportVal)) {
            pairs = [[null, calcVal, reportVal]];
          }
          if (!pairs.length) {
            results.push({ level: 'fail', ruleType: type, field: output, description: desc, calc: String(calcVal), report: String(reportVal), message: `${desc}：值类型不匹配，无法比对` });
          }
          for (const [idx, cv, rv] of pairs) {
            if (!isNum(cv) || !isNum(rv)) continue;
            const ok = compare(cv, rv, pct, absTol);
            const label = idx === null ? desc : `${desc}[${idx}]`;
            results.push({
              level: ok ? 'pass' : 'fail',
              ruleType: type,
              field: idx === null ? output : `${output}[${idx}]`,
              description: label,
              calc: fmt(cv),
              report: fmt(rv),
              message: `${label}：计算 ${cv.toFixed(2)} vs 报告 ${rv.toFixed(2)}，${ok ? '一致' : `偏差 ${Math.abs(cv - rv).toFixed(2)} 超容差`}`,
            });
          }
        }
      } else if (type === 'limit') {
        const field = rule.field || rule.field_name || '';
        const limitVal = rule.value ?? rule.limit;
        const op = rule.operator || '<=';
        let val = getValue(computed, field);
        if (val === null || val === undefined) val = getValue(Object.assign({}, extracted, flatAll), field);
        if (limitVal === null || limitVal === undefined) continue;
        if (val === null || val === undefined) {
          results.push({ level: 'fail', ruleType: type, field, description: desc, calc: '—', report: `${op} ${limitVal}`, message: `${desc}：未识别到数据` });
          continue;
        }
        const items = Array.isArray(val) ? val.map((v, i) => [i, v]) : [[null, val]];
        for (const [idx, v] of items) {
          if (!isNum(v)) continue;
          const ok = checkLimit(v, Number(limitVal), op);
          const label = idx === null ? desc : `${desc}[${idx}]`;
          results.push({
            level: ok ? 'pass' : 'fail',
            ruleType: type,
            field: idx === null ? field : `${field}[${idx}]`,
            description: label,
            calc: fmt(v),
            report: `${op} ${limitVal}`,
            message: `${label}：${fmt(v)} ${op} ${limitVal}，${ok ? '符合' : '超出限值'}`,
          });
        }
      } else if (type === 'tolerance') {
        const fieldA = rule.field_a || rule.field_name || '';
        const fieldB = rule.field_b || rule.field_name_b || '';
        const tol = rule.tolerance ?? rule.max_diff ?? 0.5;
        const va = getValue(Object.assign({}, extracted, flatAll), fieldA);
        const vb = getValue(Object.assign({}, extracted, flatAll), fieldB);
        if (va === null || vb === null || va === undefined || vb === undefined) continue;
        const pairs = Array.isArray(va) && Array.isArray(vb)
          ? va.map((a, i) => [`[${i}]`, a, vb[i]])
          : [['', va, vb]];
        for (const [suffix, a, b] of pairs) {
          if (!isNum(a) || !isNum(b)) continue;
          const diff = Math.abs(a - b);
          const ok = diff <= tol;
          results.push({
            level: ok ? 'pass' : 'warn',
            ruleType: type,
            field: `${fieldA}${suffix}`,
            description: `${desc}${suffix}`,
            calc: fmt(a),
            report: fmt(b),
            message: `${desc}${suffix}：差值 ${diff.toFixed(2)} ${ok ? '≤' : '>'} ${tol}`,
          });
        }
      }
    }

    const summary = { pass: 0, fail: 0, warn: 0 };
    for (const r of results) summary[r.level] = (summary[r.level] || 0) + 1;
    return { results, computed, summary, allPass: summary.fail === 0 };
  }

  global.ReportRules = { checkRules, flatten, evalFormula };
})(window);
