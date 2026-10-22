"""
规则校验引擎（Web 版）
复刻桌面版 report_form_panel 的校验语义：
- formula_verify：公式计算值 vs 报告记录值（容差百分比/绝对值）
- limit：限值判定（支持数组逐元素）
- tolerance：两字段/两数组差值判定
"""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional

import web_config

# 模板中文显示名（与桌面版一致，未收录的退回英文键）
TEMPLATE_DISPLAY_NAMES: Dict[str, str] = {
    'clause11_input_power_current': '输入功率和电流',
    'clause12_heating': '发热',
    'clause26_earthing': '接地装置',
    'appendix_d_dielectric_strength': '电气强度与绝缘电阻',
    'appendix_c_leakage_current': '泄漏电流',
    'clause20_mechanical_strength': '机械强度',
    'ip_rating': '外壳防护等级',
    'clause25_power_cord_bending': '电缆弯曲测试',
    'gb4343_1_emission': 'EMC',
    'gb17625_1_harmonic_current': '谐波电流',
    'gb17625_2_voltage_flicker': '电压波动和闪烁',
}

_SAFE_FUNCS = {
    'abs': abs, 'min': min, 'max': max, 'round': round,
    'sqrt': math.sqrt, 'pow': pow, 'log': math.log, 'log10': math.log10,
    'pi': math.pi, 'e': math.e,
}


# ────────────────── 模板加载 ──────────────────

def list_templates() -> List[Dict[str, Any]]:
    """递归扫描模板目录，返回模板元信息列表"""
    results = []
    for root, _dirs, files in os.walk(web_config.TEMPLATES_DIR):
        for fn in files:
            if not fn.endswith('.json'):
                continue
            name = os.path.splitext(fn)[0]
            path = os.path.join(root, fn)
            rel_dir = os.path.relpath(root, web_config.TEMPLATES_DIR)
            standard_dir = rel_dir.split(os.sep)[0] if rel_dir != '.' else ''
            meta = {'name': name, 'standard_dir': standard_dir}
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    tmpl = json.load(f)
                meta.update({
                    'standard': tmpl.get('standard', ''),
                    'title': tmpl.get('title', ''),
                    'description': tmpl.get('description', ''),
                    'display': TEMPLATE_DISPLAY_NAMES.get(name, tmpl.get('title') or name),
                })
            except Exception:
                meta['display'] = TEMPLATE_DISPLAY_NAMES.get(name, name)
            results.append(meta)
    # 去重（同名模板以先扫描到的为准）并按标准分组排序
    seen = set()
    unique = []
    for m in sorted(results, key=lambda x: (x['standard_dir'], x['name'])):
        if m['name'] not in seen:
            seen.add(m['name'])
            unique.append(m)
    return unique


def load_template(name: str) -> Optional[Dict[str, Any]]:
    """按名称加载模板 JSON（递归查找）"""
    for root, _dirs, files in os.walk(web_config.TEMPLATES_DIR):
        if f'{name}.json' in files:
            try:
                with open(os.path.join(root, f'{name}.json'), 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
    return None


# ────────────────── 取值与公式 ──────────────────

def _flatten(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """数组字段展开为 name_0、name_1... 便于公式引用"""
    flat = dict(extracted)
    for key, val in extracted.items():
        if isinstance(val, list):
            for i, v in enumerate(val):
                if v is not None:
                    flat[f'{key}_{i}'] = v
    return flat


def get_value(store: Dict[str, Any], ref: str) -> Any:
    """按引用名取值：先直接匹配，再按 base_idx 取数组元素"""
    if not ref:
        return None
    val = store.get(ref)
    if val is not None:
        return val
    m = re.match(r'^(.+?)_(\d+)$', ref)
    if m:
        base, idx = m.group(1), int(m.group(2))
        arr = store.get(base)
        if isinstance(arr, list) and idx < len(arr):
            return arr[idx]
    return None


def _set_indexed(store: Dict[str, Any], ref: str, value: Any):
    """写入（支持 indexed 引用同步回数组）"""
    store[ref] = value
    m = re.match(r'^(.+?)_(\d+)$', ref)
    if m:
        base, idx = m.group(1), int(m.group(2))
        arr = store.get(base)
        if not isinstance(arr, list):
            arr = []
            store[base] = arr
        while len(arr) <= idx:
            arr.append(None)
        arr[idx] = value


def eval_formula(formula: str, flat: Dict[str, Any]) -> Any:
    """
    安全计算公式。变量全部缺失或无法计算时返回 None。
    若变量含数组则逐元素计算返回数组。
    """
    tokens = [t for t in re.findall(r'[a-zA-Z_]\w*', formula) if t not in _SAFE_FUNCS]
    vals = [flat.get(t) for t in tokens]
    if not tokens:
        return None
    has_list = any(isinstance(v, list) for v in vals)

    def _eval_single(single_vals: list) -> Optional[float]:
        namespace = dict(_SAFE_FUNCS)
        for name, v in zip(tokens, single_vals):
            if not isinstance(v, (int, float)):
                return None
            namespace[name] = float(v)
        try:
            result = eval(formula, {'__builtins__': {}}, namespace)  # noqa: S307 - 与桌面版一致的受限 eval
            return float(result)
        except Exception:
            return None

    if has_list:
        max_len = max((len(v) for v in vals if isinstance(v, list)), default=0)
        out = []
        for i in range(max_len):
            elem = [(v[i] if i < len(v) else None) if isinstance(v, list) else v for v in vals]
            out.append(_eval_single(elem))
        return out if any(v is not None for v in out) else None
    return _eval_single(vals)


def _compare(calc: float, report: float, tolerance_pct: float,
             tolerance_abs: Optional[float]) -> bool:
    diff = abs(calc - report)
    if tolerance_abs is not None:
        return diff <= tolerance_abs
    if report != 0:
        return diff / abs(report) * 100 <= tolerance_pct
    return diff <= 0.01


def _check_limit(val: float, limit: float, op: str) -> bool:
    return {
        '<=': val <= limit, '<': val < limit,
        '>=': val >= limit, '>': val > limit,
        '==': abs(val - limit) < 0.01,
    }.get(op, False)


def _fmt(v: Any) -> str:
    if v is None:
        return '—'
    if isinstance(v, float):
        return f'{v:g}'
    return str(v)


# ────────────────── 主校验入口 ──────────────────

def check_rules(template: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行模板规则校验。

    Returns:
        {
          'results': [{level, rule_type, field, description, calc, report, message}],
          'computed': {...},   # 公式计算出的字段值
          'summary': {'pass': n, 'fail': n, 'warn': n},
          'all_pass': bool,
        }
    """
    results: List[Dict[str, Any]] = []
    computed: Dict[str, Any] = {}
    flat = _flatten(extracted)

    # 第一遍：先算所有 formula_verify 的计算值（limit 规则可能引用 computed 字段）
    for rule in template.get('rules', []):
        if rule.get('_comment') or rule.get('type') != 'formula_verify':
            continue
        formula = rule.get('formula', '')
        output_field = rule.get('field_name') or rule.get('output_field') or rule.get('result_field', '')
        if not formula or not output_field:
            continue
        calc = eval_formula(formula, {**flat, **_flatten(computed)})
        if calc is not None:
            _set_indexed(computed, output_field, calc)

    flat_all = {**flat, **_flatten(computed)}

    for rule in template.get('rules', []):
        if rule.get('_comment') or not rule.get('type'):
            continue
        rtype = rule['type']
        desc = rule.get('description') or rule.get('message') or ''

        if rtype == 'formula_verify':
            output_field = rule.get('field_name') or rule.get('output_field') or rule.get('result_field', '')
            report_source = rule.get('report_field') or output_field
            tolerance_pct = rule.get('tolerance_pct', 5.0)
            tolerance_abs = rule.get('tolerance')
            calc_val = get_value(computed, output_field)
            report_val = get_value({**extracted, **flat_all}, report_source)

            if calc_val is None and report_val is None:
                results.append({'level': 'fail', 'rule_type': rtype, 'field': output_field,
                                'description': desc, 'calc': '—', 'report': '—',
                                'message': f'{desc}：计算与识别均无数据'})
            elif calc_val is None:
                results.append({'level': 'fail', 'rule_type': rtype, 'field': output_field,
                                'description': desc, 'calc': '—（计算失败）', 'report': _fmt(report_val),
                                'message': f'{desc}：公式计算失败（缺参数）'})
            elif report_val is None:
                # 报告未记录该值：仅提示计算结果，作为警告而非失败
                results.append({'level': 'warn', 'rule_type': rtype, 'field': output_field,
                                'description': desc, 'calc': _fmt(calc_val), 'report': '—（报告未记录）',
                                'message': f'{desc}：计算值 {_fmt(calc_val)}，报告未记录该值'})
            else:
                pairs = []
                if isinstance(calc_val, list) and isinstance(report_val, list):
                    pairs = [(i, cv, rv) for i, (cv, rv) in enumerate(zip(calc_val, report_val))]
                elif isinstance(calc_val, (int, float)) and isinstance(report_val, (int, float)):
                    pairs = [(None, calc_val, report_val)]
                if not pairs:
                    results.append({'level': 'fail', 'rule_type': rtype, 'field': output_field,
                                    'description': desc, 'calc': str(calc_val), 'report': str(report_val),
                                    'message': f'{desc}：值类型不匹配，无法比对'})
                for idx, cv, rv in pairs:
                    if not isinstance(cv, (int, float)) or not isinstance(rv, (int, float)):
                        continue
                    ok = _compare(float(cv), float(rv), tolerance_pct, tolerance_abs)
                    label = f'{desc}[{idx}]' if idx is not None else desc
                    results.append({
                        'level': 'pass' if ok else 'fail', 'rule_type': rtype,
                        'field': f'{output_field}[{idx}]' if idx is not None else output_field,
                        'description': label, 'calc': _fmt(cv), 'report': _fmt(rv),
                        'message': (f'{label}：计算 {cv:.2f} vs 报告 {rv:.2f}，'
                                    f'{"一致" if ok else f"偏差 {abs(cv - rv):.2f} 超容差"}'),
                    })

        elif rtype == 'limit':
            field = rule.get('field') or rule.get('field_name', '')
            limit_val = rule.get('value', rule.get('limit'))
            operator = rule.get('operator', '<=')
            val = get_value(computed, field)
            if val is None:
                val = get_value({**extracted, **flat_all}, field)
            if limit_val is None:
                continue
            if val is None:
                results.append({'level': 'fail', 'rule_type': rtype, 'field': field,
                                'description': desc, 'calc': '—', 'report': f'{operator} {limit_val}',
                                'message': f'{desc}：未识别到数据'})
                continue
            items = list(enumerate(val)) if isinstance(val, list) else [(None, val)]
            for idx, v in items:
                if not isinstance(v, (int, float)):
                    continue
                ok = _check_limit(float(v), float(limit_val), operator)
                label = f'{desc}[{idx}]' if idx is not None else desc
                results.append({
                    'level': 'pass' if ok else 'fail', 'rule_type': rtype,
                    'field': f'{field}[{idx}]' if idx is not None else field,
                    'description': label, 'calc': _fmt(v), 'report': f'{operator} {limit_val}',
                    'message': f'{label}：{_fmt(v)} {operator} {limit_val}，{"符合" if ok else "超出限值"}',
                })

        elif rtype == 'tolerance':
            field_a = rule.get('field_a') or rule.get('field_name', '')
            field_b = rule.get('field_b') or rule.get('field_name_b', '')
            tolerance = rule.get('tolerance', rule.get('max_diff', 0.5))
            va = get_value({**extracted, **flat_all}, field_a)
            vb = get_value({**extracted, **flat_all}, field_b)
            if va is None or vb is None:
                continue
            if isinstance(va, list) and isinstance(vb, list):
                pairs = [(f'[{i}]', a, b) for i, (a, b) in enumerate(zip(va, vb))]
            else:
                pairs = [('', va, vb)]
            for suffix, a, b in pairs:
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                    continue
                diff = abs(float(a) - float(b))
                ok = diff <= tolerance
                results.append({
                    'level': 'pass' if ok else 'warn', 'rule_type': rtype,
                    'field': f'{field_a}{suffix}', 'description': f'{desc}{suffix}',
                    'calc': _fmt(a), 'report': _fmt(b),
                    'message': f'{desc}{suffix}：差值 {diff:.2f} {"≤" if ok else ">"} {tolerance}',
                })

    summary = {
        'pass': sum(1 for r in results if r['level'] == 'pass'),
        'fail': sum(1 for r in results if r['level'] == 'fail'),
        'warn': sum(1 for r in results if r['level'] == 'warn'),
    }
    return {
        'results': results,
        'computed': computed,
        'summary': summary,
        'all_pass': summary['fail'] == 0,
    }
