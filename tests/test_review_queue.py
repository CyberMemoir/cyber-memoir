from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Job


def test_review_queue_reports_material_jobs_not_indexing(client, auth, env, prepared):
    item = prepared(name="合成队列测试梗", publish=False)
    with Session(env) as db:
        for job in db.query(Job).all():
            job.status = "succeeded"
        db.add_all(
            [
                Job(kind="extract", status="pending", payload={}, dedupe_key="synthetic-extract"),
                Job(kind="media", status="running", payload={}, dedupe_key="synthetic-media"),
                Job(kind="ingest", status="failed", payload={}, dedupe_key="synthetic-ingest"),
                Job(kind="index", status="pending", payload={}, dedupe_key="synthetic-index"),
            ]
        )
        db.commit()
    assert client.get("/v1/reviews/queue").status_code == 401
    response = client.get("/v1/reviews/queue", headers=auth)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["pending_jobs"], data["running_jobs"], data["failed_jobs"]) == (1, 1, 1)
    assert [x["id"] for x in data["items"]] == [item["revision"]["id"]]
