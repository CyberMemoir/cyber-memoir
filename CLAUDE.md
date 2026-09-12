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

## Current state (2026-09-12)

**Search hangs until the reranker weights are installed by hand.** INSTALL_MODELS
bakes the model libraries into the image, not the 2.3GB of weights, so the first
request needing the reranker downloads them - and huggingface.co runs at roughly 40
bytes/second from here, inside a request that dies before it finishes, so no client
timeout is long enough. Anything through `/v1/search` hangs, the gold-set run
included.

Decided 2026-09-12: fetch the weights by hand, rather than disabling the reranker
(which would change the configuration the gold numbers were taken under) or trusting
a third-party mirror. Download the six files of BAAI/bge-reranker-v2-m3 into a local
directory, then `python ops/install_reranker.py <dir>` - it checks them, copies them
into the `models` volume where the worker sees them too, and prints the .env lines.
Set `RERANKER_MODEL` to the container path and `HF_HUB_OFFLINE=1` so nothing retries
the hub.

**The archive holds 42 published memes for 10 curated records.**
`/v1/reviews/drafts` creates a new meme unless given `meme_id`, and the loader never
gave it one, so every rerun published another copy - five 牛来, four 大葱哥. The
loader is fixed; the copies are still there, and the gold-set numbers on record were
measured over this corpus, duplicates included.

Which copy survives is a real choice, because a later run carries evidence an earlier
run had no builder for. `python evals/dedupe_memes.py report` writes
`evals/curation/_keep.csv`, one row per copy with its evidence, claim, event and
relation counts, and marks the one its stated rule would pick; edit the `keep` column,
then `python evals/dedupe_memes.py retract`. Run it before the next load - the loader
revises the *oldest* copy of a name, which need not be the one you keep.

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

## Next

Order agreed 2026-09-12: weights, then dedupe, then corpus. **UI last.**

1. Install the reranker weights (above). Nothing that touches search runs until then,
   and that includes every retrieval number.
2. Dedupe the 42 memes down to 10 (above). Do this before the next load.
3. Role pass on the 26 blank rows in `lineage.csv`, then `prep.py resolve` for their
   dates, then `drafts` / `load_curation.py`. This is the corpus growth that makes
   retrieval measurable at all - recall is 1.00 today from exact-alias matching alone,
   and nothing about pgvector or OpenSearch is answerable until lexical matching has a
   chance to fail. `gengbaike_catalogue.txt` has ~28 unprocessed videos behind that.
4. Re-measure pacing now that cookies work - `platform_fetch_interval_seconds: 300` on
   `pr-ingest-pacing` was measured under anonymous conditions and is likely far too
   conservative.
5. The web UI, once the data is worth showing. Relations render as bare UUIDs today;
   see the gap below.

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
