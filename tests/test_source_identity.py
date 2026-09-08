from cyber_memoir.ingestion.urls import canonicalize


def test_bilibili_multipart_is_not_silently_mapped_to_first_part():
    _, key, url = canonicalize("https://www.bilibili.com/video/BV1TEST00001?p=2&share_source=copy")
    assert key == "BV1TEST00001:p2"
    assert url.endswith("?p=2")
    assert canonicalize("https://www.bilibili.com/video/BV1TEST00001?p=1")[1] == "BV1TEST00001"


def test_source_id_exact_retrieval(client, prepared):
    item = prepared()
    result = client.post("/v1/search", json={"query": "BV1TEST00001"}).json()
    assert result["items"][0]["id"] == item["meme_id"]
