#!/usr/bin/env python3
"""Validate curation records against what the review API will actually accept.

Encodes the constraints in apps/backend/src/cyber_memoir/application/content.py
review() and domain/schemas.py, so a record fails here instead of on a 422.

    python evals/validate_curation.py evals/curation/
    python evals/validate_curation.py evals/curation/ji-ni-tai-mei.yaml

Exit code 1 if any record has errors. Warnings do not fail the run.
"""

from __future__ import annotations

import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")

# Windows consoles default to cp1252 and would crash on Chinese output.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def normalize(text) -> str:
    """Mirrors domain/schemas.py normalize(); alias collisions must match DB behaviour."""
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


TAXONOMY = {
    "slang", "catchphrase", "reaction", "audio", "challenge", "visual_template",
    "editing_grammar", "character", "ironic", "linguistic_play", "regional",
    "fandom", "event", "commercial", "historical", "unknown",
}
ORIGIN_TYPES = {"on_platform", "off_platform_media", "live", "text_forum", "offline", "unknown"}
MATERIAL_PATHS = {"subtitle", "asr", "ocr", "manual"}
# The vocabulary the curation actually uses: what the meme came from, what made it
# spread, and what was made from it. Set during the role pass over lineage.csv.
SOURCE_ROLES = {"source", "popularized_by", "derivative", "reference", "irrelevant"}
PLATFORMS = {"bilibili", "douyin"}
CLAIM_KEYS = {"definition", "usage_context", "origin", "alias"}
STANCES = {"supports", "contradicts"}
EVENT_TYPES = {"observed_use", "spread", "remix", "origin_claim"}
TIME_PRECISION = {"unknown", "year", "month", "day", "second"}
ORIGIN_STATUS = {"unknown", "supported", "disputed"}
# review() rejects any predicate whose target_type does not match.
# Mirrors the map in application/content.py review(); the two must agree, and this one
# has already drifted once. A predicate added there has to be added here.
PREDICATE_TARGET = {
    "derived_from": {"meme", "source"},
    "variant_of": {"meme"},
    "claimed_origin": {"source"},
    "popularized_by": {"source"},
    "documented_in": {"source"},
    "mentions": {"entity"},
}
GOLD_BUCKETS = ("canonical", "alias", "origin_intent", "polysemy", "adversarial", "must_not_return")
ORIGIN_WORDS = ("起源", "来源", "最早", "谁先", "首创", "出处")


def text_of(value) -> str:
    return value if isinstance(value, str) else ""


class Record:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data if isinstance(data, dict) else {}
        self.slug = self.data.get("slug") or path.stem
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def get(self, key, default=None):
        return self.data.get(key, default)


def check_identity(r: Record) -> None:
    name = text_of(r.get("canonical_name")).strip()
    if not name:
        r.err("canonical_name 不能为空")
    elif len(name) > 200:
        r.err("canonical_name 超过 200 字符（%d）" % len(name))
    aliases = r.get("aliases") or []
    if not isinstance(aliases, list):
        r.err("aliases 必须是列表")
        return
    if len(aliases) > 50:
        r.err("aliases 最多 50 条（%d）" % len(aliases))
    seen: dict[str, str] = {}
    for alias in aliases:
        norm = normalize(alias)
        if not norm:
            r.err("aliases 含空白项")
        elif norm in seen:
            r.err("aliases 规范化后重复：%r 与 %r" % (alias, seen[norm]))
        else:
            seen[norm] = alias
        if norm and norm == normalize(name):
            r.warn("alias %r 规范化后等于 canonical_name，入库时会被去重" % alias)


def check_enums(r: Record) -> None:
    for field, allowed in (
        ("origin_status", ORIGIN_STATUS),
        ("origin_type", ORIGIN_TYPES),
        ("material_path", MATERIAL_PATHS),
        ("platform_primary", PLATFORMS),
    ):
        value = r.get(field)
        if value is not None and value not in allowed:
            r.err("%s=%r 不在 %s 中" % (field, value, sorted(allowed)))
    for item in r.get("taxonomy") or []:
        if item not in TAXONOMY:
            r.err("taxonomy 含未知取值 %r；取自 taxonomy.md" % item)
    for source in r.get("sources") or []:
        if not isinstance(source, dict):
            r.err("sources 每项必须是映射")
            continue
        if source.get("role") not in SOURCE_ROLES:
            r.err("sources.role=%r 不在 %s 中" % (source.get("role"), sorted(SOURCE_ROLES)))
    for i, claim in enumerate(r.get("claims") or []):
        if claim.get("key") not in CLAIM_KEYS:
            r.err("claims[%d].key=%r 非法" % (i, claim.get("key")))
        if claim.get("stance", "supports") not in STANCES:
            r.err("claims[%d].stance=%r 非法" % (i, claim.get("stance")))
        if len(text_of(claim.get("statement"))) > 5000:
            r.err("claims[%d].statement 超过 5000 字符" % i)


def check_exact_statements(r: Record) -> None:
    """review() requires a supporting claim whose statement equals the field byte for byte."""
    claims = r.get("claims") or []
    if not text_of(r.get("definition")).strip():
        r.err("definition 为空；审核通过前必须填写（review() 硬性要求）")
    for field in ("definition", "usage_context"):
        value = text_of(r.get(field))
        if not value.strip():
            continue
        if any(
            c.get("key") == field
            and text_of(c.get("statement")) == value
            and c.get("stance", "supports") == "supports"
            for c in claims
        ):
            continue
        near = any(
            c.get("key") == field and text_of(c.get("statement")).strip() == value.strip()
            for c in claims
        )
        if near:
            r.err(
                "%s 的 claim.statement 与字段仅在首尾空白上不同。审核按字节比对，会 422。"
                "两处都用 |- 块标量，不要用 >- 或带换行的引号字符串。" % field
            )
        else:
            r.err("%s 非空，但没有 statement 与其逐字相同且 stance=supports 的 claim" % field)


def check_origin_rules(r: Record) -> None:
    status = r.get("origin_status", "unknown")
    claims = r.get("claims") or []
    relations = r.get("relations") or []
    if status != "unknown" and not any(c.get("key") == "origin" for c in claims):
        r.err("origin_status=%s 需要一条 key=origin 的 claim" % status)
    if status == "supported":
        if not any(rel.get("predicate") == "claimed_origin" for rel in relations):
            r.err("origin_status=supported 需要 predicate=claimed_origin 的关系指向 Source")
        if r.get("origin_type") not in (None, "on_platform"):
            r.err(
                "origin_status=supported 且 origin_type 非 on_platform：Source 需要 "
                "platform_item_id，审核会被拒绝。保持 unknown 并记录 origin_blocked（ADR 0003）"
            )
    if r.get("origin_blocked"):
        if status == "supported":
            r.err("origin_blocked=true 与 origin_status=supported 矛盾")
        if not text_of(r.get("origin_blocked_reason")).strip():
            r.err("origin_blocked=true 必须写 origin_blocked_reason —— 这是 ADR 0003 的证据")
    if r.get("origin_type") == "off_platform_media" and not text_of(r.get("origin_ref")).strip():
        r.warn("origin_type 为站外来源但 origin_ref 为空，起源无法被后人复核")


def check_relations(r: Record) -> None:
    for i, rel in enumerate(r.get("relations") or []):
        predicate = rel.get("predicate")
        if predicate not in PREDICATE_TARGET:
            r.err("relations[%d].predicate=%r 不在允许集合中" % (i, predicate))
            continue
        expected = PREDICATE_TARGET[predicate]
        if rel.get("target_type") not in expected:
            r.err(
                "relations[%d] %s 的 target_type 必须是 %s 之一，实为 %r"
                % (i, predicate, sorted(expected), rel.get("target_type"))
            )
        if rel.get("assertion_status", "supported") not in {"supported", "disputed"}:
            r.err("relations[%d].assertion_status 取值非法" % i)
        # Exactly one way of naming the far end. target_bv is a video, so it can only
        # ever be a source; a meme target is named, because its id does not exist until
        # that meme is published.
        named = [k for k in ("target_bv", "target_name", "target_id") if rel.get(k)]
        if len(named) != 1:
            r.err(
                "relations[%d] 必须且只能用 target_bv / target_name / target_id 之一指定目标，实为 %s"
                % (i, named or "空")
            )
        elif named[0] == "target_bv" and rel.get("target_type") != "source":
            r.err("relations[%d] target_bv 指向视频，target_type 只能是 source" % i)
        elif named[0] == "target_name" and rel.get("target_type") != "meme":
            r.err("relations[%d] target_name 指向另一个梗，target_type 只能是 meme" % i)


def check_events(r: Record) -> None:
    for i, event in enumerate(r.get("events") or []):
        if event.get("event_type") not in EVENT_TYPES:
            r.err("events[%d].event_type=%r 非法" % (i, event.get("event_type")))
        precision = event.get("time_precision", "unknown")
        if precision not in TIME_PRECISION:
            r.err("events[%d].time_precision=%r 非法" % (i, precision))
        start = event.get("occurred_at_start")
        end = event.get("occurred_at_end")
        if precision != "unknown" and not start:
            r.err("events[%d] time_precision=%s 需要 occurred_at_start" % (i, precision))
        for label, value in (("occurred_at_start", start), ("occurred_at_end", end)):
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    r.err("events[%d].%s 缺少时区；schemas.py 会拒绝" % (i, label))
            elif value is not None:
                r.err("events[%d].%s 不是时间值（YAML 里不要加引号）" % (i, label))
        if isinstance(start, datetime) and isinstance(end, datetime) and end < start:
            r.err("events[%d] 结束时间早于开始时间" % i)
        if not text_of(event.get("time_basis")).strip():
            r.err("events[%d].time_basis 必填：说明时间依据是什么" % i)


def check_evidence(r: Record) -> None:
    mapping = r.get("evidence_map") or {}
    if not isinstance(mapping, dict):
        r.err("evidence_map 必须是映射")
        mapping = {}
    used: set[str] = set()
    for group in ("claims", "events", "relations"):
        for i, item in enumerate(r.get(group) or []):
            refs = item.get("evidence") or []
            if not isinstance(refs, list) or not refs:
                r.err("%s[%d] 至少需要一条 evidence（schemas.py min_length=1）" % (group, i))
                continue
            if len(refs) > 30:
                r.err("%s[%d] evidence 超过 30 条" % (group, i))
            for ref in refs:
                used.add(ref)
                if ref not in mapping:
                    r.err("%s[%d] 引用了未在 evidence_map 声明的占位名 %r" % (group, i, ref))
    for name in mapping:
        if name not in used:
            r.warn("evidence_map 中 %r 未被任何断言引用" % name)
    if r.get("resolved"):
        unfilled = sorted(k for k, v in mapping.items() if not v)
        if unfilled:
            r.err("resolved=true 但这些占位名仍未填真实 evidence ID：%s" % unfilled)
        for value, count in Counter(v for v in mapping.values() if v).items():
            if count > 1:
                r.err("evidence ID %r 在 evidence_map 中出现 %d 次" % (value, count))


def check_gold(r: Record) -> None:
    gold = r.get("gold") or {}
    if not isinstance(gold, dict):
        r.err("gold 必须是映射")
        return
    for key in gold:
        if key not in GOLD_BUCKETS:
            r.warn("gold 含未知分类 %r；已知：%s" % (key, list(GOLD_BUCKETS)))
    if not (gold.get("canonical") or []):
        r.err("gold.canonical 至少需要一条查询")
    if (r.get("aliases") or []) and not (gold.get("alias") or []):
        r.warn("本条目有别名但没有 alias 用例 —— 别名检索是最有价值的一类，别漏")
    for query in gold.get("origin_intent") or []:
        if not any(word in str(query) for word in ORIGIN_WORDS):
            r.warn("origin_intent 用例 %r 不含起源意图词，RAG 的弃答分支不会触发" % query)
    seen: dict[str, str] = {}
    for bucket in GOLD_BUCKETS:
        for query in gold.get(bucket) or []:
            norm = normalize(query)
            if norm in seen:
                r.err("gold 查询重复：%r 同时出现在 %s 和 %s" % (query, seen[norm], bucket))
            else:
                seen[norm] = bucket


def check_curation_log(r: Record) -> None:
    curation = r.get("curation") or {}
    if not isinstance(curation, dict):
        r.err("curation 必须是映射")
        return
    if curation.get("ingestion_ok") is False and not text_of(curation.get("ingestion_note")).strip():
        r.warn("ingestion_ok=false 但没写 ingestion_note；平台失败率报告需要它")
    if r.get("resolved") and not text_of(curation.get("curator")).strip():
        r.warn("resolved=true 但 curation.curator 为空")


CHECKS = (
    check_identity,
    check_enums,
    check_exact_statements,
    check_origin_rules,
    check_relations,
    check_events,
    check_evidence,
    check_gold,
    check_curation_log,
)


def load_negatives(directory: Path) -> tuple[list[dict], list[str]]:
    """Negative cases live outside the per-meme records because they belong to no meme.

    correct_abstention is computed only over answerable: false rows, so an empty or malformed
    negatives file yields no abstention score at all rather than a low one.
    """
    path = directory / "_negatives.yaml"
    if not path.exists():
        return [], ["没有 _negatives.yaml；correct_abstention 无法计算（ADR 0002 条款 3）"]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [], ["_negatives.yaml 解析失败：%s" % exc]
    if not isinstance(data, dict):
        return [], ["_negatives.yaml 顶层必须是映射，含 negatives 键"]
    items = data.get("negatives") or []
    if not isinstance(items, list):
        return [], ["_negatives.yaml 的 negatives 必须是列表"]
    problems: list[str] = []
    seen: dict[str, int] = {}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append("negatives[%d] 必须是映射" % i)
            continue
        query = text_of(item.get("query")).strip()
        if not query:
            problems.append("negatives[%d].query 为空" % i)
            continue
        if not text_of(item.get("reason")).strip():
            problems.append("negatives[%d] (%r) 必须写 reason：为什么它不该有答案" % (i, query))
        norm = normalize(query)
        if norm in seen:
            problems.append("negatives 查询重复：%r 与第 %d 条相同" % (query, seen[norm]))
        else:
            seen[norm] = i
    return [x for x in items if isinstance(x, dict)], problems


def check_relation_targets(records: list["Record"]) -> list[str]:
    """A relation naming a meme must name one this corpus defines.

    The loader publishes the target first, so a name with no record behind it is a
    typo or a meme nobody has curated yet - either way the relation cannot resolve.
    """
    known = {text_of(r.get("canonical_name")) for r in records}
    problems = []
    for r in records:
        for i, rel in enumerate(r.get("relations") or []):
            wanted = text_of(rel.get("target_name")).strip()
            if wanted and wanted not in known:
                problems.append(
                    "%s relations[%d] 指向《%s》，但没有任何记录以此为 canonical_name"
                    % (r.slug, i, wanted)
                )
    return problems


def check_negatives_against_records(negatives: list[dict], records: list["Record"]) -> list[str]:
    """A query matching a curated entry is not a negative; the library should answer it."""
    surface: dict[str, str] = {}
    for r in records:
        for value in [text_of(r.get("canonical_name")), *(r.get("aliases") or [])]:
            norm = normalize(value)
            if norm:
                surface.setdefault(norm, r.slug)
    problems = []
    for item in negatives:
        norm = normalize(text_of(item.get("query")))
        if norm in surface:
            problems.append(
                "反例 %r 就是 %s 的表述，本库应当回答它，不构成反例" % (item.get("query"), surface[norm])
            )
    return problems


def validate(path: Path) -> Record:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        record = Record(path, {})
        record.err("YAML 解析失败：%s" % exc)
        return record
    record = Record(path, data)
    if not isinstance(data, dict):
        record.err("顶层必须是映射")
        return record
    for check in CHECKS:
        check(record)
    return record


def cross_check(records: list[Record]) -> list[str]:
    problems: list[str] = []
    slugs: dict[str, Path] = {}
    surface: dict[str, tuple[str, str]] = {}
    for r in records:
        if r.slug in slugs:
            problems.append("slug 重复：%s 出现在 %s 和 %s" % (r.slug, slugs[r.slug].name, r.path.name))
        slugs[r.slug] = r.path
        for value in [text_of(r.get("canonical_name")), *(r.get("aliases") or [])]:
            norm = normalize(value)
            if not norm:
                continue
            if norm in surface and surface[norm][0] != r.slug:
                problems.append(
                    "表述冲突：%r 同时属于 %s 和 %s。Alias 表按规范化字符串唯一，"
                    "exact_alias 通道会互相污染" % (value, surface[norm][0], r.slug)
                )
            else:
                surface[norm] = (r.slug, value)
    for r in records:
        for query in (r.get("gold") or {}).get("adversarial") or []:
            hit = surface.get(normalize(query))
            if hit and hit[0] == r.slug:
                problems.append("%s 的 adversarial 用例 %r 就是本条目的表述，不构成对抗" % (r.slug, query))
    names = [text_of(r.get("canonical_name")) for r in records]
    for name, count in Counter(n for n in names if n).items():
        if count > 1:
            problems.append("canonical_name %r 重复 %d 次；gold 的 expected_names 无法区分" % (name, count))
    return problems


def report_strata(records: list[Record], negatives: list[dict] | None = None) -> None:
    """ADR 0002 stratification targets, so gaps surface before curation finishes."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        counts["platform"][r.get("platform_primary") or "?"] += 1
        counts["material"][r.get("material_path") or "?"] += 1
        counts["origin"][r.get("origin_type") or "?"] += 1
        for item in r.get("taxonomy") or []:
            counts["taxonomy"][item] += 1
    off_platform = sum(v for k, v in counts["origin"].items() if k not in ("on_platform", "unknown", "?"))
    blocked = sum(1 for r in records if r.get("origin_blocked"))
    failed = sum(1 for r in records if (r.get("curation") or {}).get("ingestion_ok") is False)
    alias_heavy = sum(1 for r in records if len(r.get("aliases") or []) >= 2)
    done = sum(1 for r in records if r.get("resolved"))
    gold_total = sum(
        len((r.get("gold") or {}).get(b) or [])
        for r in records
        for b in GOLD_BUCKETS
        if b != "must_not_return"
    )
    print("\n分层进度（ADR 0002 目标：20 条，站外起源 ≥8，抖音 ≥6，多别名 ≥6）")
    print("  记录 %d（已落库 %d）  gold 用例 %d" % (len(records), done, gold_total))
    print("  站外起源 %d   其中 schema 无法表达 %d   多别名 %d" % (off_platform, blocked, alias_heavy))
    print("  平台 %s   抓取失败 %d" % (dict(counts["platform"]), failed))
    print("  材料路径 %s" % dict(counts["material"]))
    missing = {"catchphrase", "audio", "visual_template", "linguistic_play"} - set(counts["taxonomy"])
    if missing:
        print("  类型覆盖缺口：%s" % sorted(missing))
    if negatives is not None:
        short = "" if len(negatives) >= 8 else "   <- 少于 ADR 0002 要求的 8 条，弃答率不可报告"
        print("  反例 %d%s" % (len(negatives), short))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    target = Path(argv[1])
    if target.is_dir():
        paths = sorted(p for p in target.glob("*.y*ml") if not p.name.startswith("_"))
    elif target.exists():
        paths = [target]
    else:
        sys.stderr.write("找不到 %s\n" % target)
        return 2
    if not paths:
        print("%s 下没有策展文件（_template.yaml 已跳过）" % target)
        return 0
    records = [validate(path) for path in paths]
    negatives, negative_problems = load_negatives(target if target.is_dir() else target.parent)
    failed = 0
    for r in records:
        if r.errors or r.warnings:
            print("\n%s  [%s]" % (r.path.name, r.slug))
        for msg in r.errors:
            print("  x %s" % msg)
        for msg in r.warnings:
            print("  ! %s" % msg)
        failed += bool(r.errors)
    for problem in cross_check(records):
        print("\nx 跨文件：%s" % problem)
        failed += 1
    for problem in check_relation_targets(records):
        print("\nx 关系目标：%s" % problem)
        failed += 1
    for problem in negative_problems + check_negatives_against_records(negatives, records):
        print("\nx 反例：%s" % problem)
        failed += 1
    report_strata(records, negatives)
    print("\n%d 个文件，%d 处需要修。" % (len(records), failed) if failed else "\n%d 个文件全部通过。" % len(records))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
