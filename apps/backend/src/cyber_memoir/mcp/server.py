from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session

from cyber_memoir.application.content import detail, dump, evidence_is_public, require
from cyber_memoir.config import settings
from cyber_memoir.db import engine
from cyber_memoir.domain.models import Evidence, Source
from cyber_memoir.domain.responses import AnswerOut, EvidenceOut, MemeOut, SearchOut
from cyber_memoir.domain.schemas import SearchRequest
from cyber_memoir.rag.answer import answer
from cyber_memoir.search.retrieval import search

mcp = FastMCP(
    "Cyber Memoir",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings().mcp_allowed_hosts.split(","),
        allowed_origins=settings().mcp_allowed_origins.split(","),
    ),
)
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


@mcp.tool(annotations=READ_ONLY)
def search_memes(query: str, platform: str | None = None, limit: int = 10) -> SearchOut:
    """Search reviewed memes. Scores express relevance, not truth. Returns evidence and degradation flags."""
    with Session(engine()) as db:
        return SearchOut.model_validate(
            search(db, SearchRequest(query=query, platform=platform, limit=limit))
        )


@mcp.tool(annotations=READ_ONLY)
def get_meme(meme_id: str) -> MemeOut:
    """Read the current published revision, claims and supporting/contradicting evidence."""
    with Session(engine()) as db:
        return MemeOut.model_validate(detail(db, meme_id))


@mcp.tool(annotations=READ_ONLY)
def get_evidence(evidence_id: str) -> EvidenceOut:
    """Read a public evidence excerpt with its original source URL and locator."""
    with Session(engine()) as db:
        if not evidence_is_public(db, evidence_id):
            raise ValueError("Evidence unavailable or not public")
        item = require(db, Evidence, evidence_id)
        return EvidenceOut.model_validate({**dump(item), "source": dump(db.get(Source, item.source_id))})


@mcp.tool(annotations=READ_ONLY)
def get_timeline(meme_id: str) -> dict[str, Any]:
    """Read reviewed events. Earliest recorded use is not proof of origin."""
    result = get_meme(meme_id).model_dump(mode="json")
    return {"events": result["events"], "claims": result["claims"], "evidence": result["evidence"]}


@mcp.tool(annotations=READ_ONLY)
def get_relations(meme_id: str) -> dict[str, Any]:
    """Read one-hop, human-reviewed cultural relationships and their evidence."""
    result = get_meme(meme_id).model_dump(mode="json")
    return {"relations": result["relations"], "evidence": result["evidence"]}


@mcp.tool(annotations=READ_ONLY)
def answer_question(question: str, platform: str | None = None) -> AnswerOut:
    """Answer exclusively using reviewed claims; return citations and explicit unknowns."""
    with Session(engine()) as db:
        return AnswerOut.model_validate(answer(db, SearchRequest(query=question, platform=platform)))
