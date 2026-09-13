"""The universe view: every published meme as a galaxy of stars placed by date.

These pin the rules the drawing depends on and cannot check for itself: stage never
decides position, a stage with no evidence is distinguishable from one without a date,
dates arrive read in Beijing, and nothing retracted is drawn.
"""

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def revise(client, made, reason, **fields):
    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], **fields},
        headers=AUTH,
        params={"meme_id": made["meme_id"]},
    )
    assert revision.status_code == 201, revision.text
    approved = client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={"decision": "approve", "reason": reason, "verified_evidence_ids": [made["evidence"]["id"]]},
        headers=AUTH,
    )
    assert approved.status_code == 200, approved.text


def remix(made, when, title="合成衍生作品"):
    return {
        "event_type": "remix",
        "description": title,
        "occurred_at_start": when,
        "time_precision": "day",
        "time_basis": "合成测试",
        "to_source_id": made["source"]["id"],
        "evidence_ids": [made["evidence"]["id"]],
    }


def link(made, predicate, target_type="source", target_id=None):
    return {
        "predicate": predicate,
        "target_type": target_type,
        "target_id": target_id or made["source"]["id"],
        "evidence_ids": [made["evidence"]["id"]],
    }


def galaxy(client, name):
    body = client.get("/v1/universe")
    assert body.status_code == 200, body.text
    found = [g for g in body.json()["galaxies"] if g["name"] == name]
    assert len(found) == 1, [g["name"] for g in body.json()["galaxies"]]
    return found[0], body.json()


def test_stars_are_placed_by_date_and_dated_in_beijing(client, prepared):
    made = prepared(name="合成星系梗")
    revise(client, made, "合成测试：两次衍生，相隔一年",
           events=[remix(made, "2026-08-20T00:00:00+08:00", "后来的衍生"),
                   remix(made, "2025-08-01T00:00:00+08:00", "更早的衍生")],
           relations=[link(made, "popularized_by")])

    g, universe = galaxy(client, "合成星系梗")
    derivatives = sorted((s for s in g["stars"] if s["stage"] == "derivative"), key=lambda s: s["t"])
    # SQLite drops the zone without converting, so this cannot catch a UTC-slicing bug:
    # here a slice and a Beijing reading agree. test_timescale holds china_date to a real
    # UTC instant, and the day-early bug was caught against PostgreSQL.
    assert [s["date"] for s in derivatives] == ["2025-08-01", "2026-08-20"]
    assert derivatives[0]["t"] == 0.0 and derivatives[1]["t"] > derivatives[0]["t"]
    # 384 days apart is past the quiet threshold, so the axis must say how long it cut.
    assert [b["days"] for b in g["bands"]] == [384]
    assert universe["timezone"] == "Asia/Shanghai"
    assert g["emergence"] == {**g["emergence"], "date": "2025-08-01", "basis": "derivative"}


def test_the_first_of_each_stage_is_its_milestone_and_an_empty_stage_is_null(client, prepared):
    made = prepared(name="合成里程碑梗")
    revise(client, made, "合成测试：只有来源与衍生",
           events=[remix(made, "2026-08-21T00:00:00+08:00"), remix(made, "2026-08-19T00:00:00+08:00")],
           relations=[link(made, "derived_from")])

    g, _ = galaxy(client, "合成里程碑梗")
    by_id = {s["id"]: s for s in g["stars"]}
    assert by_id[g["milestones"]["derivative"]]["date"] == "2026-08-19"
    assert g["milestones"]["popularized_by"] is None, "no evidence at all: the UI draws an empty slot"
    assert g["milestones"]["derived_meme"] is None
    # The source has no platform date in tests. It is evidenced but undated, so its stage
    # is not empty - it has a milestone - and it simply has no position.
    source = by_id[g["milestones"]["source"]]
    assert source["t"] is None and source["date"] is None
    assert sum(1 for s in g["stars"] if s["milestone"]) == 2


def test_a_meme_built_on_another_shows_up_in_both_galaxies(client, prepared):
    parent = prepared(name="合成母梗")
    revise(client, parent, "合成测试：母梗的衍生", events=[remix(parent, "2026-08-20T00:00:00+08:00")])
    child = prepared(name="合成子梗")
    revise(client, child, "合成测试：子梗衍生自母梗",
           events=[remix(child, "2026-08-16T00:00:00+08:00")],
           relations=[link(child, "derived_from", "meme", parent["meme_id"])])

    parent_galaxy, universe = galaxy(client, "合成母梗")
    child_galaxy, _ = galaxy(client, "合成子梗")
    derived = [s for s in parent_galaxy["stars"] if s["stage"] == "derived_meme"]
    assert [(s["kind"], s["label"]) for s in derived] == [("meme", "合成子梗")]
    # Dated by the child's own emergence, which here precedes the parent's first derivative.
    # That is drawn as it is, not reordered to fit the four-stage story.
    assert derived[0]["date"] == "2026-08-16"
    assert derived[0]["t"] < next(s["t"] for s in parent_galaxy["stars"] if s["stage"] == "derivative")
    upstream = [s for s in child_galaxy["stars"] if s["stage"] == "source" and s["kind"] == "meme"]
    assert [s["label"] for s in upstream] == ["合成母梗"]
    assert {"from_meme_id": child["meme_id"], "to_meme_id": parent["meme_id"], "predicate": "derived_from"} in universe["links"]


def test_nothing_retracted_is_drawn(client, prepared):
    parent = prepared(name="合成留存梗")
    revise(client, parent, "合成测试：母梗", events=[remix(parent, "2026-08-20T00:00:00+08:00")])
    child = prepared(name="合成撤回子梗")
    revise(client, child, "合成测试：将被撤回的子梗",
           relations=[link(child, "derived_from", "meme", parent["meme_id"])])

    retracted = client.post(f"/v1/reviews/memes/{child['meme_id']}/retract",
                            json={"reason": "合成测试：撤回子梗"}, headers=AUTH)
    assert retracted.status_code == 200, retracted.text

    parent_galaxy, universe = galaxy(client, "合成留存梗")
    assert "合成撤回子梗" not in [g["name"] for g in universe["galaxies"]]
    assert [s for s in parent_galaxy["stars"] if s["stage"] == "derived_meme"] == []
    assert all(child["meme_id"] not in (l["from_meme_id"], l["to_meme_id"]) for l in universe["links"])
