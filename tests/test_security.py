import pytest

from cyber_memoir.domain.schemas import EventInput, normalize
from cyber_memoir.ingestion.urls import canonicalize, validate_public


@pytest.mark.parametrize(
    "url",
    [
        "http://www.bilibili.com/video/BV1TEST00001",
        "https://evil.test/video/BV1TEST00001",
        "https://www.bilibili.com.evil.test/video/BV1TEST00001",
        "https://127.0.0.1/video/BV1TEST00001",
        "https://user:password@www.bilibili.com/video/BV1TEST00001",
        "https://www.bilibili.com:123/video/BV1TEST00001",
        "https://www.bilibili.com/",
        "file:///etc/passwd",
    ],
)
def test_only_supported_https_platform_urls(url):
    with pytest.raises(ValueError):
        canonicalize(url)


def test_platform_id_parsing():
    assert canonicalize("https://www.bilibili.com/video/BV1TEST00001?spm=x")[1] == "BV1TEST00001"
    assert canonicalize("https://www.douyin.com/video/1234567890123456789")[0] == "douyin"


def test_private_dns_resolution_blocked(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("192.168.1.2", 443))])
    with pytest.raises(ValueError, match="内部网络"):
        validate_public("https://www.bilibili.com/video/BV1TEST00001", True)


def test_normalization_preserves_original_outside_search_key():
    assert normalize(" ＡＢＣ　 Meme ") == "abc meme"


def test_unknown_dates_not_invented():
    event = EventInput(
        event_type="observed_use", description="合成事件", time_basis="来源无日期", evidence_ids=["fixture"]
    )
    assert event.occurred_at_start is None


def test_event_requires_timezone():
    with pytest.raises(ValueError):
        EventInput(
            event_type="observed_use",
            description="合成事件",
            time_basis="平台时间",
            occurred_at_start="2020-01-01T00:00:00",
            evidence_ids=["fixture"],
        )


def test_material_requires_locator(client, prepared):
    item = prepared()
    assert (
        client.post(f"/v1/sources/{item['source']['id']}/materials", json={"text": "无定位原文"}).status_code
        == 422
    )


def test_submitter_token_enforced(client):
    from cyber_memoir.config import settings

    settings().submitter_token = "test-submitter"
    assert (
        client.post(
            "/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001"}
        ).status_code
        == 401
    )


def test_rate_limit(client):
    for _ in range(60):
        response = client.post("/v1/search", json={})
        assert response.status_code == 200
    assert client.post("/v1/search", json={}).status_code == 429
