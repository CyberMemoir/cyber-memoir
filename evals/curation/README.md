# Portable reviewed vault

This export contains 116 published records and their cited OCR/ASR text, source locators, resolved platform metadata and review provenance. The seven uncertain local records are excluded. Raw downloaded videos, cookies, credentials and personal automation/checkpoints are not included.

`vault_manifest.json` pins the portable files and record/evidence review fingerprints. Export resets `resolved` and evidence database IDs so another instance can create its own IDs. Claims, uncertainty, original author attribution and human description bytes are retained. Frozen same-Codex review artifacts are copied byte for byte into `evals/reviews`; these are separate passes with limited independence, not human or independent-model confirmation.

From the repository root, install the documented development dependencies and run:

```powershell
python evals/load_curation.py --dry-run
```

For a live import, start the documented local stack, configure your own `REVIEWER_TOKEN` in the ignored `.env`, then run `python evals/load_curation.py`. Importing creates reviewed revisions; it is separate from committing files to GitHub. The API deduplicates source submissions, and the loader orders named meme dependencies. The import is not a fresh semantic or factual evaluation.

Human descriptions and model descriptions retain separate provenance. The completed retrieval audit covered the earlier 104-record snapshot (338 cases); its results do not establish retrieval metrics or factual correctness for this 116-record export. No current price, trading advice, unsupported first-origin claim or human confirmation is added by the export.
