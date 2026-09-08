from sqlalchemy import or_, select

from cyber_memoir.domain.models import Evidence, EvidenceLink, Meme


def publication_is_valid():
    """Defense in depth against stale indexes and concurrent evidence invalidation."""
    invalid = (
        select(EvidenceLink.id)
        .join(Evidence)
        .where(
            EvidenceLink.meme_id == Meme.id,
            EvidenceLink.revision == Meme.published_revision,
            or_(Evidence.retracted.is_(True), Evidence.verified.is_(False)),
        )
        .correlate(Meme)
        .exists()
    )
    return (Meme.status == "published") & ~invalid
