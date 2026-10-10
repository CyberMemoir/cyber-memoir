"""Fictional software fixtures, never imported into the deployment database."""

DEMO_TOKEN = "local-synthetic-demo-only"
DEMO_SUBMISSION_URL = "https://www.bilibili.com/video/BV1DEMO00002"
DEMO_QUERY = "合成星灯"


def seed(db):
    from cyber_memoir.application.content import add_material, create_draft, review
    from cyber_memoir.application.publications import register_source
    from cyber_memoir.domain.publications import SourceRegistration
    from cyber_memoir.domain.schemas import Material, MemeDraft, ReviewAction

    published = []
    for index, (name, platform, url, publish) in enumerate(
        [
            ("合成演示：星灯亮起", "web", "https://example.org/memoir-demo/star", True),
            (
                "合成演示：星灯续章",
                "xiaohongshu",
                "https://www.xiaohongshu.com/explore/0123456789abcdef01234567",
                True,
            ),
            ("合成演示：等待审核", "douyin", "https://www.douyin.com/video/1234567890123456789", False),
        ]
    ):
        source, _ = register_source(
            db,
            SourceRegistration(
                platform=platform,
                url=url,
                title=f"{name}的虚构来源，不是真实文化材料",
                platform_published_at=f"2026-0{index + 1}-10T12:00:00+08:00",
            ),
        )
        source.metadata_note = "本地合成演示占位 URL，未抓取、未核查真实平台；所有日期和文字均为虚构。"
        definition = f"{name}是用于软件演示的虚构表达，不代表真实互联网文化或历史。"
        usage = "仅在本地演示中，用来检验检索、证据定位和人工审核流程。"
        evidence = add_material(
            db,
            source.id,
            Material(text=f"{definition}\n{usage}", locator={"note": "合成演示摘录，非真实证据"}),
            {"method": "synthetic_demo", "not_real_cultural_evidence": True},
            enqueue_extract=False,
        )
        payload = {
            "canonical_name": name,
            "aliases": [DEMO_QUERY] if index == 0 else [],
            "definition": definition,
            "usage_context": usage,
            "claims": [
                {"key": "definition", "statement": definition, "evidence_ids": [evidence.id]},
                {"key": "usage_context", "statement": usage, "evidence_ids": [evidence.id]},
            ],
            "events": [
                {
                    "event_type": "observed_use",
                    "description": "虚构的演示使用记录，不是实际平台事件。",
                    "occurred_at_start": f"2026-0{index + 1}-01T00:00:00+08:00",
                    "time_precision": "month",
                    "time_basis": "合成演示日期，仅展示月份精度。",
                    "to_source_id": source.id,
                    "evidence_ids": [evidence.id],
                }
            ],
            "relations": [
                {
                    "predicate": "documented_in",
                    "target_type": "source",
                    "target_id": source.id,
                    "evidence_ids": [evidence.id],
                }
            ],
        }
        if index == 1:
            payload["relations"].append(
                {
                    "predicate": "variant_of",
                    "target_type": "meme",
                    "target_id": published[0],
                    "evidence_ids": [evidence.id],
                }
            )
        revision = create_draft(db, MemeDraft.model_validate(payload))
        if publish:
            review(
                db,
                revision.id,
                ReviewAction(
                    decision="approve",
                    reason="合成夹具初始化：仅模拟审核，非真实文化事实核验。",
                    verified_evidence_ids=[evidence.id],
                ),
                "synthetic-demo-bootstrap",
            )
            published.append(revision.meme_id)
        else:
            db.commit()
    return published
