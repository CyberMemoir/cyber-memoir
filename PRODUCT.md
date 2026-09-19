# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Curious netizens (confirmed 2026-09-19). Someone meets an unfamiliar Chinese internet meme,
in a comment section or a video, and wants to know what it means and where it came from.
Search is their door; the star map of the meme's history is the reward after the answer.

Secondary, not designed for first: the two curators (Vincent and his partner) who use the
submission and review tools.

## Product Purpose

Cyber Memoir / 赛博回忆录 is an evidence-first archive of Chinese internet memes. Every
published statement traces to evidence someone can go and look at, and the system abstains
rather than guessing. Success is a visitor who leaves knowing what a meme means, when and
from what it came, and able to check each of those against its source.

## Positioning

cnmeme.wiki has 6,000+ LLM-written entries with no citations. Cyber Memoir does not compete
on volume. Its mechanism: 梗百科 explainer episodes burn the BV id of every work they cite
onto the screen; OCR those ids, resolve each against the platform, and a dated lineage
falls out with nobody asserting a date. The archive shows a meme as a timeline of evidence,
not as an article.

## Operating Context

- Search: exact/alias, BM25 and a reranker, with a score floor under which it abstains.
  Answers can take tens of seconds to minutes on current hardware; the page must stay alive
  and honest while it waits.
- Universe of Memes: every meme on a time axis; open one to see its galaxy.
- Four causal stages of a meme's history: source, popularized_by, derivative videos,
  derived memes. Stages are causal, not chronological.
- Chinese-language interface. Dates are shown in Beijing time.

## Capabilities and Constraints

- Position by date, colour by role: where a star sits comes only from its date, never its
  stage. A meme's galaxy is a spiral whose arm is time (confirmed 2026-09-19).
- Evidence must be distinguishable from decoration at a glance: decorative particles are
  colourless, small and not interactive; evidence stars carry their role's colour, a label,
  and their shape on hover/focus (confirmed 2026-09-19).
- Missing stages show as visible empty slots (无证据), distinct from an evidenced star with
  no date (无日期). Time direction is always drawn.
- No takedown checking: `availability` is ingestion state, never "is the video online".
- Stack: Next.js 16.3.4, React 19.2.8, no UI dependencies. Evidence stars stay DOM/SVG
  elements, focusable with aria-labels, because e2e tests and keyboard users need them.
- The dev machine is slow (OCR ~3 s/frame; reranking 2-3 s per pair); motion must not
  depend on a fast GPU.

## Brand Commitments

- Name: Cyber Memoir / 赛博回忆录.
- The whole site lives in one night-sky world (confirmed 2026-09-19).
- Honesty over polish: a caveat travels with every number, and the interface says 无证据
  rather than filling a gap.

## Evidence on Hand

- 14 published memes, 12 more awaiting review; live data from `GET /v1/universe`.
- Real explainer OCR, platform titles and dates for every evidence star.
- No testimonials, users, press or usage statistics exist. None may be invented.

## Product Principles

1. Evidence before conclusion: every visual claim is traceable to a record.
2. Absence is shown, never hidden or filled.
3. Ornament and evidence never look alike.
4. The answer comes first; exploration is the reward.
5. Wait honestly: slow work is shown as work, never disguised as speed.

## Accessibility & Inclusion

Keyboard access to every evidence star; stage survives colour-blind readers through shape
and size; motion respects `prefers-reduced-motion`.
