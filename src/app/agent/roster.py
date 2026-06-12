"""园区租户名单 + 拼音模糊匹配。

ASR 容易把公司名听错（"鲸鱼"→"金鱼"）。把识别到的名字按拼音相似度去名单里匹配：
- high：高置信、唯一胜出 → 调用方直接折进复述
- fuzzy：有相近候选但不够确定 → 调用方单独快确认一句
- none：没匹配上 → 按来访者说的原样记
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from pypinyin import Style, lazy_pinyin

# 园区租户名单（demo 用，可在此维护）
ROSTER: list[str] = [
    "蓝色鲸鱼科技",
    "远峰物流",
    "恒达机械",
    "普瑞医疗器械",
    "星河电子",
]

# 常见行业后缀，匹配时连同核心词一起考虑
_SUFFIXES = ["科技", "物流", "机械", "医疗器械", "电子", "有限公司", "公司"]

# 置信阈值
_HIGH = 0.82
_FUZZY = 0.55
_MARGIN = 0.10  # 与次优的差距，够大才算"唯一胜出"


@dataclass
class CompanyMatch:
    name: str | None      # 匹配到的名单内准确名称（none 时为 None）
    confidence: str       # "high" | "fuzzy" | "none"
    score: float


def _pinyin(s: str) -> str:
    return "".join(lazy_pinyin(s, style=Style.NORMAL))


def _containment(a: str, b: str) -> float:
    """a 的字符有多少能在 b 里连续匹配上（衡量 a 是否近似 b 的子串）。"""
    if not a:
        return 0.0
    sm = SequenceMatcher(None, a, b)
    matched = sum(block.size for block in sm.get_matching_blocks())
    return matched / len(a)


def _score(query_py: str, entry_py: str) -> float:
    ratio = SequenceMatcher(None, query_py, entry_py).ratio()
    contain = _containment(query_py, entry_py)
    # 兼顾整体相似与"输入近似子串"两种情况
    return max(ratio, contain * 0.95)


def match_company(name: str) -> CompanyMatch:
    """把识别到的公司名匹配到名单。"""
    name = (name or "").strip()
    if not name:
        return CompanyMatch(None, "none", 0.0)

    # 名单里有原文直接命中
    if name in ROSTER:
        return CompanyMatch(name, "high", 1.0)

    query_py = _pinyin(name)
    scored: list[tuple[float, str]] = []
    for entry in ROSTER:
        s = max(_score(query_py, _pinyin(entry)), _score(query_py, _pinyin(_core(entry))))
        scored.append((s, entry))
    scored.sort(reverse=True)

    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score >= _HIGH and (best_score - second_score) >= _MARGIN:
        return CompanyMatch(best, "high", best_score)
    if best_score >= _FUZZY:
        return CompanyMatch(best, "fuzzy", best_score)
    return CompanyMatch(None, "none", best_score)


def _core(entry: str) -> str:
    """去掉行业后缀，取核心词（用于"金鱼"对"蓝色鲸鱼科技"这种部分匹配）。"""
    core = entry
    for suf in _SUFFIXES:
        if core.endswith(suf) and len(core) > len(suf):
            core = core[: -len(suf)]
            break
    return core
