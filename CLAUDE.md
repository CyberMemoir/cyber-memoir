# Cyber Memoir — working context

Evidence-first archive of Chinese internet memes. Everything published must trace to
evidence; the system abstains rather than guessing. Vincent curates (judgement, facts),
Claude builds (code, plumbing, measurement).

## The direction we landed on

Not an encyclopedia — a **timeline**. cnmeme.wiki already has 6,000+ LLM-written entries
with no citations and substring-only search; we cannot and should not out-volume it. The
axis we can win on is evidence.

The extraction insight, found 2026-09-08: **explainer narration is nearly useless, the
screen is gold.** 梗百科 burns the BV id of every work it cites onto the canvas. OCR those,
resolve each against the platform, and a dated lineage falls out with nobody asserting a
date. Narration gives meaning only — across every episode annotated, none gave a source or
a date for the meme itself. So definitions are Tier C commentary and are recorded as such.

## The four-stage model

```
source ──→ popularized_by ──→ derivative videos ──→ derived memes
```

| stage | representation | notes |
|---|---|---|
| source | `derived_from → Source` | upstream material; may be years older |
| popularized by | `popularized_by → Source` | what made it spread; ≠ where it came from |
| derivative videos | `Event(remix, to_source_id)` | dated from platform metadata |
| derived memes | `derived_from → Meme` | target must already be published |

Two memes show *old material, sudden revival*: 狼王撕衣 (2021 → 2026-08) and 才是王道
(FNF 2021–2024 → 2026-08). Worth watching whether that generalises.

## Curation workflow

```bash
python evals/feasibility/prep.py derivatives <BV> --cookies bili-cookies.txt --no-resolve
python evals/feasibility/prep.py resolve --cookies bili-cookies.txt --sleep 20
python evals/feasibility/prep.py sheet          # -> lineage.csv
python evals/feasibility/origin_cues.py <EP>... -o cues.txt   # the origin sentences
#   model proposes origins -> origins.csv; --check verifies; --apply writes the sheet
python evals/feasibility/prep.py drafts         # -> one curation YAML per meme
# model drafts definition + usage_context from subtitle OCR; human reviews, sets confirmed_by
# (name-free gold queries go in evals/curation/_descriptions.yaml before any draft exists)
python evals/validate_curation.py evals/curation/
python evals/load_curation.py <files>           # submit → material → tier → draft → approve
                                                # no files = every record, re-revising all
python evals/build_gold.py && python evals/run.py evals/gold.jsonl
```

`role` values: `source | popularized_by | derivative | reference | irrelevant`.
`drafts` never overwrites an existing record — it matches on `canonical_name`, so files
renamed to pinyin slugs are still recognised.

## Hard-won operational facts

**Bilibili cookies were the root cause of every 412.** The jar had zero bilibili cookies
(browsing happened in Edge, extraction read Chrome). Anonymous → yt-dlp calls
`x/player/wbi/playurl` per video, the most risk-controlled endpoint. Authenticated → it
reads `__INITIAL_STATE__` and `__playinfo__` from the page HTML: **one request per video,
not three or four.** Use `--cookies bili-cookies.txt` (gitignored); reading a live browser
profile needs the browser *closed*, which conflicts with using it.

**Rate limiting is per-endpoint and IP-scoped**, roughly 30 consecutive requests, recovery
needs 20–30 minutes of quiet. Spacing does not move the wall — request *count* does. Verify
cookies before tuning any interval.

**The API rate-limits POST/PUT at 60/min per client IP.** Bulk tooling must pace;
`load_curation.py` sleeps 1.1s between calls.

**Timestamps normalise to UTC.** `2026-08-18T00:00+08:00` returns as `2026-08-17T16:00Z`.
The web UI will show the wrong day if it renders naively.

**SQLite (tests) and PostgreSQL (real) disagree on timezones** — SQLite drops the zone.
Assert on the instant, never the spelling. Anything timezone-sensitive is under-tested by
construction.

**Windows is cp1252.** Every script needs `sys.stdout.reconfigure(encoding="utf-8")` and
every `open()`/`write_text()` needs `encoding="utf-8"`. Five such bugs found so far.

**OCR misreads are self-verifying.** Every NOT FOUND id has been a one-character variant of
an id that did resolve (0/o, C/c, i/1, z/Z, **and letter case**: BV1XyJA6BEBN on screen for
BV1xyJA6BEBN). Search the screen case-insensitively before concluding an id is absent -
doing it case-sensitively once cost 大狗叫 a true popularized_by relation for a day, and
`materials_index.resolve_placeholder` now accepts a case variant after an exact match
fails. Bad OCR costs recall, never correctness.
Corpus accuracy 33/37 = 89% over answered requests. BLOCKED ≠ NOT FOUND: a refused request
says nothing about the id.

**About 4 in 10 episodes show no BV ids at all** - 6 of the first 16 - and for those the
title-card name guess is junk ("8/9", "便百科山山"). They give meaning but no timeline, and
`drafts` skips them. Plan corpus growth at roughly 60% yield per episode.

**The subtitle checker found where the curator knew more than the screen.** Run over the
14 hand-written records as if drafted, it refuses 5, and each is real: 狼王撕衣's twitter
origin, 轻松绷住's P42, 泥肘's gloss 你走, 牛来 (ASR-only), and 真人版HIM's quote
"神不会流血，但你会" - whose second half the OCR *had* but `build_materials.py` dropped,
because `MIN_CHARS = 6` discards short lines. Quoted lines are often short, so that filter
costs drafts their quotations. **Fixed 2026-09-18 for new episodes:** a 2-5 character line
now survives if it persists across 2+ frames (fragments flicker, subtitles stay up). It
recovered all three losses and more (子琪不吃, 周五夜放克, @handles) at the cost of some UI
chrome (分享, 回复). The 14 published episodes keep the old flat floor and must never be
rebuilt - evidence is keyed on content hash, so a rebuild posts a second piece of evidence.

**The narrator's subtitle is found by position, not guessed** (2026-09-19). OCR boxes
carry positions (`<EP>.boxes.json`; `prep.py boxes` re-OCRs a video on disk, `derivatives`
writes them for new episodes). 梗百科's narrator is one centred row at a fixed height per
episode - 86.6%, 89.4% or 92.0% of the frame across 21 episodes, box height 0.052-0.058 -
so the row is measured per episode, and height separates a clip's own bottom subtitles
sharing it (闹吃's rap lyrics: same row, 0.08-0.09 tall). New episodes get two materials:
`ocr-narration-<EP>` is the narrator only, `ocr-screen-<EP>` everything else shown. The 9
published episodes keep the old mixed layout. OCR runs ~3 s/frame here; dropping the angle
classifier saved 18% with identical narrator lines.

**ASR errs on the narrator too, not only on clip audio** (measured 2026-09-19 on
BV1xWtJ6iEGs, the one episode with both ASR and OCR). Clip audio is garbage (软弱烤一花 for
软糯烤地瓜), but in the narrator's clean stretches (0-41s, 68-77s) about half the lines differ
from the on-screen subtitle, including every name: 松珍/松针, 子奇/子琪, 肤腥/护心, 油煸/油边.
The errors are fluent, so judging "explanation vs messy clip sound" does not catch them, and
the sound does not carry the characters (子琪 and 子奇 are both zǐqí). The transcript also
held no narrator line the OCR lacked. ASR may be read for meaning; names, quotes and
evidence come from OCR. Whisper `small`; n = 1 episode.

**The origin is one sentence, and the id comes after it.** An episode cites about six
videos and says where the meme came from in one or two sentences - 32 sentences across
21 episodes against 117 cited ids - so the scarce thing is the sentence, not the id.
Asking a model to role each id failed (4 of 23 origins); asking it which sentence states
an origin puts 22 of 25 in front of the curator inside 50 rows of 117 - the other 3
being unreachable, not missed
(`origin_cues.py`, fitted on that set, so it is a description and not yet a result).
The narrator names the origin and *then* cuts to the clip, so the window runs -20s to
+45s around the sentence, not symmetrically. Position in the episode is not a signal:
only 8 of 27 memes have their origin as the first id shown. **5 of 21 episodes never
state an origin at all**, and an off-platform origin - a tweet, a screenshot - never
gets a BV id and so can never appear (ADR 0003). `reference` is not a role Vincent uses:
zero of 137 judged rows, and offering it to a model cost 7 origins.

**One episode can cover several memes.** BV1ii4C6QEk8 covers three. Split ids by the
`seen_at` column — it records when each appeared on screen, so the split is mechanical. The
one-draft-per-source constraint lives in `extract()` (the LLM path we don't use); the manual
loader has no such limit.

**`validate_curation.py` duplicates rules from `content.py` review().** The predicate map
and role vocabulary have already drifted once. A predicate added to one must be added to
the other.

## Current state (2026-09-13)

**Search works, slowly, and one at a time.** Reranker weights were fetched by hand into
the `models` volume (`ops/install_reranker.py`, `HF_HUB_OFFLINE=1`). A gold run takes
67-81 minutes; `RETRIEVAL_CANDIDATE_CAP=20` saved 20% and is recorded in
`evals/results-2026-09-13-cap.md` with its criteria committed before the run.

Reranking is serialised (`pr-rerank-concurrency`). Three simultaneous searches used to
finish none of them inside 30s while the container sat pegged and the Next **dev proxy**
answered a plain-text 500 - the API itself never returned a 5xx and never saw those
requests. It queues instead of degrading, because an uncalibrated run cannot enforce the
retrieval floor and the archive would answer where it should abstain. Verified after the
fix: three at once, all 200, 42/86/169s. A dev-only aggravator remains - React
StrictMode double-invokes the catalogue search, so a page load costs two reranks.

**14 memes published, one copy each.** 32 duplicates were retracted on 2026-09-13
(`evals/curation/_keep.csv` records which). The loader now passes `meme_id`, so reruns
revise instead of minting copies. Latest gold run: 40 cases, recall@10 1.00, MRR 1.00,
abstention 10/10 — of which 6 were real refusals by the score floor and 4 matched no
chunk at all.

- **Stack**: `docker compose --env-file .env -f ops/compose/compose.yml up -d`, API on :8100.
  Reranker enabled; embeddings and LLM deliberately off — hand curation must not be
  contaminated by model output.
- **Corpus**: 16 OCR'd episodes, 59 extracted ids (33 resolved — the newest batch is
  unresolved), **all 10 curation records published**, each at revision 2.
  才是王道 is the first meme derived from another meme, and 闹吃VS古振兴 the first
  carrying both a source and a popularized_by.
- **`lineage.csv`**: 59 rows, **52 judged; the role pass is done.** The 7 blank rows are
  exactly the 7 rows with no `upload_date` — ids that never resolved, so there is nothing
  to judge. Several are visibly OCR variants of a row that did resolve (`BV1v73w6fEBi` vs
  `BV1v73W6fEBi`; `BViesbf6wEkc` is `BV1esbf6wEkc` with i-for-1), which is the usual
  pattern and costs recall only.
- **Gold set**: 93 cases. **Recall on name queries is 1.00 and means nothing** - 54 of
  the 82 positives are the meme's own name or name + 的出处, all at rank 1. The
  informative bucket is the 28 name-free `description` queries Vincent wrote on
  2026-09-20: **recall@10 0.893, MRR 0.781**, rank 1 for 20 of the 25 it finds.
  Always split with `evals/score_buckets.py`; the 0.963 aggregate is mostly spelling.
  All three misses are vocabulary gaps and two returned *zero* candidates - with
  embeddings off, BM25 cannot cross a gap, and the archive then abstains on a question
  it could answer. The 11/11 abstention score only measures the other direction.
  Full baseline in `evals/results-2026-09-20-baseline.md`.
- **Branches**: **`main` now carries everything** - PR #5 merged `integration` into it on
  2026-09-15, with a merge commit, so every commit message survives. `integration` stays
  as the assembly point and is what the running stack is built from; keep making work on
  a PR branch and merging it there, then raise one PR to `main`. Never commit novel work
  on `integration` itself. Stacking is real where it exists - `pr-source-annotations`
  chains off `pr-event-source-link` for the migration order, and API branches sit on
  `pr-windows-encoding` because `make contracts` cannot run on Windows without it.
- **CI runs lint and tests on every push**, and it caught three things the dev machine
  could not: MinIO had vanished from Docker Hub so a fresh `compose up` died (now pulled
  from quay.io); the pacing gate refused the first fetch on a freshly booted host,
  invisible here under 5.7 days of uptime; and ruff was being run from the repo root,
  where it picks up the wrong config - CI runs it from `apps/backend`.
- **`test_backup.py` fails on Windows only** (`Unexpected artifact key in backup`); it
  passes in CI on Linux, so it looks like a path-separator bug in the artifact key
  rather than a broken backup path. Still worth chasing.

## Web UI — decided 2026-09-13

Two parts: search/answers as the baseline, and a **Universe of Memes** exhibition.
Universe level is every meme on a horizontal time axis; click one to zoom into its galaxy.

- **Position by date, colour by role.** Stage never decides where a star sits. The four
  stages are causal and the evidence breaks their order: 才是王道 (derived meme) is dated
  08-16, before 闹吃VS古振兴's popularized_by work at 08-20.
- **Milestones are the first star of each stage.**
- **Missing stages are visible empty slots** (无证据) — distinct from an evidenced star
  that lacks a date (无日期). Only 闹吃VS古振兴 has all four; most galaxies show 2-3 empty.
- **Time direction is always drawn**: "时间 →" on the universe axis, "早 → 晚" radially.
- **No takedown checking, ever.** `availability` is ingestion state, not whether a video
  is online, and nothing records that.

**Redesigned 2026-09-19 as a planetarium** (Vincent: more motion, a real-looking galaxy,
whole site dark; details in `PRODUCT.md`, the contract comment in `app/layout.tsx`, and
`DESIGN.md`). What changed and what must stay true:
- A meme's galaxy is a **two-armed spiral whose arms are time**. Radius is still date and
  nothing else (the e2e test measuring an undated star's distance from centre still
  holds); the arm only fixes the angle, which is itself a function of `t`
  (`universe-layout.ts`, `armAngle`). Quiet periods are dust lanes that thin the arms.
- **Colour belongs to evidence.** Dust, sky, motes are colourless; one mint "projector"
  colour marks controls; the four role colours mark evidence; diffraction spikes mark
  milestones only. Decoration is generated from a seed of the meme id, so it never
  reshuffles.
- Motion carries meaning: galaxies ignite as a sweep passes their first date; stars ignite
  outward in date order; motes drift outward along the arm (the direction of time); a
  time cursor on the universe axis dims what did not exist yet. Ambient sky rotation,
  twinkles and meteors are CSS transforms on a canvas drawn once.
- **Everything animated is skipped under `prefers-reduced-motion`**, and Playwright runs
  with `reducedMotion: "reduce"` - a moving target is never "stable" enough to click.
- **A guessed height overlaps something.** Both of the home page's overlays were
  sized by eye and both covered live text: the horizon floor was 420px deep with 164px
  of dome under it and printed 0.65 black over the first 220px of the memory index
  (the first record read as disabled), and the sky caption was 159px tall in a row
  reserving 118px and printed over the headline. Neither throws, neither changes a
  computed style, and the console is positioned, so it paints over the index whatever
  the source order says. `e2e/dome-layout.spec.ts` measures both, and each assertion
  was confirmed to fail against the code it describes.
- Fonts are self-hosted: Noto Serif SC 500 in two `unicode-range` slices (GB2312 level 1 +
  every character the UI and data use; the rest loads on demand), Jost for numerals. Windows
  had been rendering headings in SimSun. Adding a meme with rare characters needs no action:
  a missing glyph falls back to the system serif.

`GET /v1/universe` (`pr-universe`) serves all of it in one ~2s request. Quiet gaps over
21 days are compressed into bands that carry their true length; 21 came from measuring
29 gaps first (bursts ≤ 15 days, silences ≥ 30). Dates leave the server already in
Beijing time — `at` is UTC and must never be displayed.

**Corpus loop (from 2026-09-18):** DeepSeek and Vincent grow the corpus without Claude,
per `ai_context/work_loop.txt`; `ai_context/loop_state.txt` holds whose turn it is and
`loop_log.txt` one block per batch. Claude returns at the CHECKPOINT (30 published memes,
batch 3 done, or a stop) to audit drafts against OCR, run gold with `description` recall
reported apart from name queries, then refine the web UI. Phase 0 (4 blind drafts of
published memes) passed the checker but showed what it cannot see: 轻松绷住's usage was
drafted as "绷不住" - a real quote, the opposite meaning - and usage_context drifted into
describing spread. Rules D-10..D-15 in the loop file answer those.

**Split:** DeepSeek builds the UI; Claude owns the API and the time scale, and reviews.
Handoff lives in `ai_context/` (gitignored): `task_prompt.txt` is the spec with ten
numbered invariants, `universe.example.json` a real payload, DeepSeek writes
`deepseek_report.txt`, Claude writes `review_feedback.txt`. Review against the INV
numbers, and check real data on the live stack — the e2e harness only has synthetic data.

## Next

1. Grow the corpus - it is now the binding constraint on everything. 13 of 14 galaxies
   have 1-4 stars and 13 have no `popularized_by`, so the star map reads mostly as
   absence, and recall stays saturated. `gengbaike_catalogue.txt` has ~28 unprocessed
   episodes. Every round also retires `out_of_corpus` negatives, so Vincent owes a few
   new ones each time (`fabricated` ones do not perish).
2. Gold set positives all name their meme, so recall cannot see what the candidate cap
   (now 20) costs. It needs queries that do not contain the answer's name.
3. Atmosphere for the star map, if wanted: SVG/CSS glow first, a Canvas 2D starfield
   behind the SVG second. The data layer stays SVG - stars are focusable elements with
   aria-labels and e2e selectors. Decoration must never share the four stage shapes or
   colours, or a reader cannot tell ornament from evidence.
4. Re-measure platform pacing now that cookies work (`pr-ingest-pacing`, 300 s).
5. Reranker per-pair cost is 2.3-3.5 s. Serialisation fixed the collapse, not the speed;
   a rented server is the answer, not a smaller model.

## Open architecture gaps

- **ADR 0003 — off-platform origins.** 狼王撕衣's real origin is a 2022 tweet;
  `Source` requires a platform item id, so the archive can express the layer *below* the
  origin and the layers above, but not the origin itself. Proposed, unbuilt.
- **`Evidence.observed_at`** — when we saw it, distinct from publish and insert time.
  Exists only on `archive/bundled-all-six`, never split into a PR.
- **Fusion has no representation.** Observed twice (泥肘+老叟戏顽童 on 2026-08-13,
  肥嘟嘟+牛来). A derivative that merges memes appears on several timelines with nothing
  saying they merged.
- **A relation to a source renders as a bare UUID.** `content.detail()` returns
  relations as ids only, so the web UI shows 闹吃VS古振兴 as "衍生自 · 有证据支持 ·
  a3f1…" seven times. The timeline is unreadable until relations carry the target's
  title and URL.
- **Ingestion contract undecided.** Automated fetch works now that auth is fixed, but the
  OCR lineage pipeline still lives in `prep.py` on the host, not in the worker.

## Working agreements

- Models do not supply facts about memes. Names, aliases, roles, origin judgements and gold
  queries are Vincent's; an answer key written by a model cannot grade a model.
- **Amended 2026-09-18:** a model may *draft* `definition` and `usage_context` prose, from
  the on-screen subtitle OCR only (`ocr-narration-*`, never ASR, never its own knowledge).
  Every name and spoken line in a draft goes in 「」 or |...| and must be found verbatim in
  the cited OCR; digits and Latin words are checked marked or not. The record carries
  `curation.drafted_by`, the loader refuses it until `confirmed_by` is set, and the
  approved revision's `review_reason` says "模型起草、人工审定". Tier alone cannot carry
  this - hand-written and drafted definitions are both Tier C.
  **Limit:** an unmarked Chinese name is not checked; Vincent's review is the only net.
  **Precondition:** gold queries that do not name their meme must exist before the first
  drafted batch loads. Drafted text will be keyword-rich and uniform, which can inflate
  recall, and recall on self-naming queries is already 1.00 and cannot show it.
- Thresholds get written down *before* a test runs, never adjusted to fit the result.
- Report the caveat with the number. The score floor commit says 0.35 sits inside a wide
  safe margin rather than being validated — that honesty is the point of the project.
