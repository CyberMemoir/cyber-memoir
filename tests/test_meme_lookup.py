"""Looking a meme up by the name you already have, without going through search."""

from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Evidence


def test_lookup_returns_the_addressable_id(client, prepared):
    item = prepared(name="查名测试梗")
    rows = client.get("/v1/memes", params={"name": "查名测试梗"}).json()
    assert [x["id"] for x in rows] == [item["meme_id"]]
    # The fields have to survive the response model; two of them have been silently
    # dropped in this codebase before, each time by an undeclared field.
    assert rows[0]["canonical_name"] == "查名测试梗"
    assert rows[0]["published_revision"] >= 1
    assert rows[0]["created_at"]


def test_lookup_normalises_the_way_publication_does(client, prepared):
    prepared(name="Cased Name")
    assert len(client.get("/v1/memes", params={"name": "  cased   name "}).json()) == 1


def test_lookup_reports_every_meme_sharing_a_name(client, prepared):
    """Nothing stops two published memes sharing a name, so the caller must see both.

    Returning one of them would let a tool bind a relation to whichever row happened
    to sort first, which is how a loader silently creates a duplicate instead of
    revising what is already there.
    """
    first = prepared(name="同名测试梗")
    second = prepared(name="同名测试梗")
    rows = client.get("/v1/memes", params={"name": "同名测试梗"}).json()
    assert {x["id"] for x in rows} == {first["meme_id"], second["meme_id"]}


def test_lookup_hides_a_meme_whose_evidence_died(client, prepared, env):
    item = prepared(name="失效证据测试梗")
    with Session(env) as db:
        db.get(Evidence, item["evidence"]["id"]).retracted = True
        db.commit()
    assert client.get("/v1/memes", params={"name": "失效证据测试梗"}).json() == []


def test_lookup_of_an_unknown_name_is_empty_not_an_error(client):
    response = client.get("/v1/memes", params={"name": "从未收录过的名字"})
    assert response.status_code == 200
    assert response.json() == []
