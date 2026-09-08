import ipaddress
import re
import socket
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

HOSTS = {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "b23.tv",
    "www.douyin.com",
    "douyin.com",
    "v.douyin.com",
    "iesdouyin.com",
    "www.iesdouyin.com",
}


def validate_public(url: str, platform_only=False):
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("仅接受标准 HTTPS 平台链接")
    if platform_only and p.hostname not in HOSTS:
        raise ValueError("仅支持 Bilibili / 抖音链接")
    for answer in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(answer[4][0]).is_global:
            raise ValueError("不允许访问内部网络")


def safe_get(url: str, platform_only=False, limit=4_000_000) -> bytes:
    # Validate every redirect; no environment-provided proxy or implicit redirects.
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        for _ in range(6):
            validate_public(url, platform_only)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise ValueError("材料超过大小限制")
                return bytes(body)
    raise ValueError("重定向次数过多")


def canonicalize(url: str) -> tuple[str, str, str]:
    p = urlparse(url.strip())
    if (
        p.scheme != "https"
        or p.hostname not in HOSTS
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        raise ValueError("请提交 Bilibili 或抖音的 HTTPS 视频链接")
    if p.hostname in {"b23.tv", "v.douyin.com"}:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            for _ in range(5):
                validate_public(url, platform_only=True)
                response = client.get(url)
                if not response.is_redirect:
                    break
                url = urljoin(url, response.headers["location"])
                p = urlparse(url)
                if p.hostname not in {"b23.tv", "v.douyin.com"}:
                    break
        p = urlparse(url)
        if p.hostname not in HOSTS or p.scheme != "https":
            raise ValueError("短链接未指向支持的平台")
    if p.hostname in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        match = re.search(r"/video/(BV[0-9A-Za-z]{10}|av[0-9]+)(?:/|$)", p.path)
        if match:
            item = match[1]
            parts = parse_qs(p.query).get("p", ["1"])
            if len(parts) != 1 or not parts[0].isdigit() or not 1 <= int(parts[0]) <= 10000:
                raise ValueError("Bilibili 分 P 参数无效")
            part = int(parts[0])
            if part > 1:
                return "bilibili", f"{item}:p{part}", f"https://www.bilibili.com/video/{item}?p={part}"
            return "bilibili", item, f"https://www.bilibili.com/video/{item}"
    if p.hostname in {"douyin.com", "www.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}:
        match = re.search(r"/(?:video|share/video)/(\d{10,25})(?:/|$)", p.path)
        if match:
            return "douyin", match[1], f"https://www.douyin.com/video/{match[1]}"
    raise ValueError("未找到视频 ID，请提交具体视频而不是主页或分享文案")
