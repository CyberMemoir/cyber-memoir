"""Offline source identity. Registration never resolves DNS or follows short links."""

import ipaddress
import re
from hashlib import sha256
from typing import Literal
from urllib.parse import parse_qs, urlparse, urlunparse

Platform = Literal["bilibili", "douyin", "xiaohongshu", "web"]


def source_identity(platform: Platform, url: str) -> tuple[str, str]:
    if any(ord(c) < 33 or c == "\\" for c in url):
        raise ValueError("来源链接不能包含空白、控制字符或反斜线")
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("来源必须使用无凭据的标准 HTTPS 链接")
    host = p.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if "." not in host or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("不能登记本地网络来源")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("不能登记内部网络来源")
    if platform == "bilibili" and host in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10}|av[0-9]+)/?", p.path)
        if match:
            item = match[1]
            parts = parse_qs(p.query, keep_blank_values=True).get("p", ["1"])
            if len(parts) != 1 or not parts[0].isdigit() or not 1 <= int(parts[0]) <= 10000:
                raise ValueError("Bilibili 分 P 参数无效")
            part = int(parts[0])
            suffix = f"?p={part}" if part > 1 else ""
            return item + (f":p{part}" if part > 1 else ""), f"https://www.bilibili.com/video/{item}{suffix}"
    elif platform == "douyin" and host in {
        "douyin.com",
        "www.douyin.com",
        "iesdouyin.com",
        "www.iesdouyin.com",
    }:
        match = re.fullmatch(r"/(?:video|share/video)/(\d{10,25})/?", p.path)
        if match:
            return match[1], f"https://www.douyin.com/video/{match[1]}"
    elif platform == "xiaohongshu" and host in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        match = re.fullmatch(r"/(?:explore|discovery/item)/([0-9a-fA-F]{24})/?", p.path)
        if match:
            item = match[1].lower()
            return item, f"https://www.xiaohongshu.com/explore/{item}"
    elif platform == "web":
        if host in {"b23.tv", "v.douyin.com", "xhslink.com"} or host.endswith(
            ("bilibili.com", "douyin.com", "iesdouyin.com", "xiaohongshu.com")
        ):
            raise ValueError("平台页面必须使用正确的平台标识及完整内容链接")
        # Query strings may contain the actual page identity. Never discard or sort them.
        authority = f"[{host}]" if ":" in host else host
        canonical = urlunparse(("https", authority, p.path or "/", p.params, p.query, ""))
        return "url:" + sha256(canonical.encode()).hexdigest(), canonical
    raise ValueError("来源平台与链接不匹配；请使用完整内容链接，不使用短链")
