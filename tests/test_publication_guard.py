from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Evidence


def test_invalid_evidence_blocks_detail_even_before_status_propagation(client, prepared, env):
    item = prepared()
    # Simulate evidence invalidation racing an approval or a delayed propagation.
    with Session(env) as db:
        db.get(Evidence, item["evidence"]["id"]).retracted = True
        db.commit()
    assert client.get(f"/v1/memes/{item['meme_id']}").status_code == 404
    assert client.get(f"/v1/evidence/{item['evidence']['id']}").status_code == 404
    assert client.post("/v1/search", json={"query": "合成测试梗"}).json()["total"] == 0


def test_body_size_rejected_with_content_length(client):
    response = client.post(
        "/v1/search",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "20000000"},
    )
    assert response.status_code == 413
