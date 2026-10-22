"""
本地规则字段抽取（Web 版）

输入 DocMind 解析出的文本/表格，按模板字段定义抽取数值，不调用大模型。
适用于标签清晰、表格规整的检测报告；复杂排版建议人工复核。
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from ai_parser import collect_template_fields, parse_number


def _norm(s: Any) -> str:
    """归一化：全半角统一、去空白、小写"""
    text = unicodedata.normalize('NFKC', str(s or ''))
    return re.sub(r'\s+', '', text).lower()


def _strip_paren(s: str) -> str:
    return re.sub(r'[（(][^）)]*[）)]', '', s or '').strip()


def _labels(fdef: Dict[str, Any]) -> List[str]:
    """字段描述 → 候选标签（去单位/括号/报告值等后缀）"""
    desc = fdef['description'] or fdef['name']
    base = _strip_paren(desc)
    base = re.sub(r'(报告值|计算值|实测值|测量值)$', '', base).strip()
    labels = []
    for cand in (desc, base):
        n = _norm(cand)
        if len(n) >= 2 and n not in labels:
            labels.append(n)
    return labels


def _header_label(h: str) -> str:
    return _norm(_strip_paren(h))


def _is_number_cell(cell: str) -> bool:
    return parse_number(cell) is not None


def _data_start(rows: List[List[str]], headers: List[str]) -> int:
    """找出表头行位置，返回数据起始行索引"""
    if not headers:
        return 0
    want = [_header_label(h) for h in headers if h]
    best_idx, best_score = 0, 0
    for i, row in enumerate(rows[:4]):
        cells = [_norm(c) for c in row]
        score = sum(1 for w in want if any(w in c or c in w for c in cells if c))
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx + 1 if best_score else 0


def _table_score(table: Dict[str, Any], headers: List[str], title: str = '') -> float:
    rows = table.get('rows') or []
    if not headers or not rows:
        return 0.0
    want = [_header_label(h) for h in headers if h]
    if not want:
        return 0.0
    cells = [_norm(c) for row in rows[:3] for c in row if c]
    hit = sum(1 for w in want if any(w in c or c in w for c in cells))
    score = hit / len(want)
    ntitle = _norm(title)
    if ntitle and ntitle in _norm(table.get('title', '')):
        score += 0.6
    return score


def _pick_table(tables: List[Dict[str, Any]], headers: List[str],
                title: str = '') -> Optional[List[List[str]]]:
    best, best_score = None, 0.0
    for table in tables:
        score = _table_score(table, headers, title)
        if score > best_score:
            best, best_score = table.get('rows'), score
    if best_score >= 0.5:
        return best
    return None


def _row_by_label(rows: List[List[str]], labels: List[str], start: int) -> Optional[int]:
    for i in range(start, len(rows)):
        first = _norm(' '.join(rows[i][:2]))
        if any(lb in first for lb in labels):
            return i
    return None


def _row_by_index(rows: List[List[str]], name: str, start: int) -> Optional[int]:
    m = re.search(r'row_(\d+)$', name)
    if not m:
        return None
    idx = start + int(m.group(1)) - 1
    return idx if idx < len(rows) else None


def _cells_to_array(row: List[str], size: Optional[int],
                    header_count: int = 0) -> List[Optional[float]]:
    # 首列为行标签（如「额定负载1」「0.94倍额定电压1」）时先去掉
    cells = row
    if header_count and len(cells) == header_count + 1:
        cells = cells[1:]
    values = [parse_number(c) for c in cells]
    # 兜底：行首纯文字（解析不出数字）继续去掉
    while values and values[0] is None and len(values) > 1:
        values = values[1:]
    if size:
        values = values[:size] + [None] * max(0, size - len(values))
    return values


# ────────────────── 表格取值 ──────────────────

def _extract_array(fdef: Dict[str, Any], tables: List[Dict[str, Any]],
                   lines: List[str]) -> Optional[List[Optional[float]]]:
    headers = fdef.get('headers') or []
    size = fdef.get('array_size')
    rows = _pick_table(tables, headers, fdef.get('table', ''))
    if rows:
        start = _data_start(rows, headers)
        labels = _labels(fdef)
        idx = _row_by_label(rows, labels, start)
        if idx is None:
            idx = _row_by_index(rows, fdef['name'], start)
        if idx is None and size and len(rows) - start == 1:
            idx = start
        if idx is not None:
            return _cells_to_array(rows[idx], size, len(headers))

    # 退路：按标签在文本中找数值
    for lb in _labels(fdef):
        for i, line in enumerate(lines):
            pos = _norm(line).find(lb)
            if pos >= 0:
                window = ' '.join(lines[i:i + 3])
                nums = [parse_number(x) for x in re.findall(
                    r'[-+]?\d+(?:\.\d+)?', unicodedata.normalize('NFKC', window))]
                nums = [n for n in nums if n is not None]
                if nums:
                    if size:
                        nums = nums[:size] + [None] * max(0, size - len(nums))
                    return nums
    return None


# ────────────────── 键值取值 ──────────────────

def _section_lines(lines: List[str], title: str, all_titles: List[str]) -> List[str]:
    """按表格标题切出该字段所在区段；找不到标题则返回全文"""
    ntitle = _norm(title)
    if not ntitle:
        return lines
    starts = [i for i, ln in enumerate(lines) if ntitle in _norm(ln)]
    if not starts:
        return lines
    # 优先精确标题行，避免「电缆弯曲测试」这种长标题抢先命中
    exact = [i for i in starts if _norm(lines[i]) == ntitle]
    start = exact[0] if exact else min(starts, key=lambda i: len(_norm(lines[i])))
    others = [_norm(t) for t in all_titles if t and _norm(t) != ntitle]
    end = len(lines)
    for i in range(start + 1, len(lines)):
        n = _norm(lines[i])
        if any(o in n for o in others):
            end = i
            break
    return lines[start:end]


def _section_by_anchors(lines: List[str], labels: List[str]) -> List[str]:
    """按同表其它字段标签定位区段，用于同名标签（如两处「测试结果」）消歧"""
    nlabels = [_norm(lb) for lb in labels if lb]
    pos = [i for i, ln in enumerate(lines)
           if any(lb in _norm(ln) for lb in nlabels)]
    if not pos:
        return lines
    start = max(0, min(pos) - 1)
    end = min(len(lines), max(pos) + 4)
    return lines[start:end]


def _value_from_tables(fdef: Dict[str, Any], tables: List[Dict[str, Any]]) -> Tuple[bool, Any]:
    labels = _labels(fdef)
    headers = fdef.get('headers') or []
    rows = _pick_table(tables, headers, fdef.get('table', '')) if headers else None
    candidates = [rows] if rows else [t.get('rows') or [] for t in tables]
    for tbl in candidates:
        for row in tbl:
            for ci, cell in enumerate(row):
                ncell = _norm(cell)
                if any(lb == ncell or lb in ncell for lb in labels):
                    for nxt in row[ci + 1:]:
                        if not str(nxt).strip():
                            continue
                        if fdef['type'] == 'number':
                            num = parse_number(nxt)
                            if num is not None:
                                return True, num
                        else:
                            return True, str(nxt).strip()
    return False, None


def _extract_scalar(fdef: Dict[str, Any], tables: List[List[List[str]]],
                    lines: List[str]) -> Any:
    ok, val = _value_from_tables(fdef, tables)
    if ok:
        return val

    for lb in _labels(fdef):
        for i, line in enumerate(lines):
            nline = _norm(line)
            pos = nline.find(lb)
            if pos < 0:
                continue
            rest = nline[pos + len(lb):]
            rest = rest.lstrip('：:|；;，,、-— ')
            if not rest and i + 1 < len(lines):
                rest = _norm(lines[i + 1])
            if not rest:
                continue
            if fdef['type'] == 'number':
                num = parse_number(unicodedata.normalize('NFKC', rest))
                if num is not None:
                    return num
            else:
                # 文本值保留原始大小写：在原始行上按标签重新截取
                orig = unicodedata.normalize('NFKC', line)
                m = re.search(re.escape(lb), orig, re.IGNORECASE)
                if m:
                    rest_orig = orig[m.end():]
                    rest_orig = rest_orig.lstrip('：:|；;，,、-— ')
                    token = re.split(r'[|；;，,、\s]', rest_orig, maxsplit=1)[0]
                    token = token.strip('：:.-—')
                    if token:
                        return token
                token = re.split(r'[|；;，,、\s]', rest, maxsplit=1)[0]
                token = token.strip('：:.-—')
                if token:
                    return unicodedata.normalize('NFKC', token)
    return None


# ────────────────── 主入口 ──────────────────

def extract_fields_local(parsed: Dict[str, Any], template: Dict[str, Any],
                         progress=None) -> Dict[str, Any]:
    """
    从 DocMind 解析结果中按模板抽取字段。

    Args:
        parsed: docmind_ocr.parse_document 的返回值
    Returns:
        {field_name: 数值/数组/文本/None}
    """
    text = parsed.get('text', '') or ''
    tables = parsed.get('tables', []) or []
    lines = [ln for ln in re.split(r'\n+', text) if ln.strip()]
    fields = collect_template_fields(template)
    all_titles = [t.get('title', '') for t in template.get('tables', [])]

    if progress:
        progress(f'本地规则抽取：{len(fields)} 个字段，{len(tables)} 张表格...')

    result: Dict[str, Any] = {}
    siblings: Dict[str, List[str]] = {}
    for fdef in fields:
        siblings.setdefault(fdef['table'], []).extend(_labels(fdef))

    for fdef in fields:
        if fdef.get('computed'):
            continue
        if fdef['type'] == 'number_array':
            result[fdef['name']] = _extract_array(fdef, tables, lines)
        else:
            scoped = _section_lines(lines, fdef['table'], all_titles)
            if scoped is lines:
                scoped = _section_by_anchors(lines, siblings.get(fdef['table'], []))
            result[fdef['name']] = _extract_scalar(fdef, tables, scoped)
    return result
