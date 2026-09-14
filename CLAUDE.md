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
python evals/feasibility/prep.py sheet          # -> lineage.csv, fill `role` by hand
python evals/feasibility/prep.py drafts         # -> one curation YAML per meme
# human writes definition + usage_context
python evals/validate_curation.py evals/curation/
python evals/load_curation.py                   # submit → material → tier → draft → approve
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
an id that did resolve (0/o, C/c, i/1, z/Z). Bad OCR costs recall, never correctness.
Corpus accuracy 33/37 = 89% over answered requests. BLOCKED ≠ NOT FOUND: a refused request
says nothing about the id.

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
- **`lineage.csv`**: 59 rows, **26 with a blank `role`** — the newest OCR batch, awaiting
  the human role pass. The 26 also need resolving (`prep.py resolve`) for their dates.
- **Gold set**: 22 cases (14 positive, 8 negative). Baseline recall@10 1.00, MRR 1.00 — not
  impressive on 6 memes queried by their own names. The informative number was abstention:
  6/8 without the score floor, **8/8 with it**.
- **Branches**: 11 pushed to origin (`pr-popularized-by`, `pr-model-cache` and
  `pr-meme-by-name` are the new ones); `pr-ingest-pacing` is local only. `integration`
  is a local merge of all of them and is what the running stack is built from — no
  single branch carries both the migration chain and the newer API work, so nothing
  else will start. Never commit novel work on `integration`: make it on a PR branch and
  merge it in. Stacking is real where
  it exists — `pr-source-annotations` chains off `pr-event-source-link` for the migration
  order, and API branches sit on `pr-windows-encoding` because `make contracts` cannot run
  on Windows without it.
- **`test_backup.py` fails and always has** (`Unexpected artifact key in backup`), on `main`,
  unrelated to any of this work. The backup path is unverified.

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

`GET /v1/universe` (`pr-universe`) serves all of it in one ~2s request. Quiet gaps over
21 days are compressed into bands that carry their true length; 21 came from measuring
29 gaps first (bursts ≤ 15 days, silences ≥ 30). Dates leave the server already in
Beijing time — `at` is UTC and must never be displayed.

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

- Claude does not supply facts about memes. Definitions, names, roles and origin judgements
  are Vincent's; an answer key written by a model cannot grade a model.
- Thresholds get written down *before* a test runs, never adjusted to fit the result.
- Report the caveat with the number. The score floor commit says 0.35 sits inside a wide
  safe margin rather than being validated — that honesty is the point of the project.
