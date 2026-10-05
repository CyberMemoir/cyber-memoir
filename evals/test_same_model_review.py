"""Targeted checks for truthful frozen review and evidence-bound batch scope."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_review as review
import vault_loop


class FrozenReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = {'EP': [{'text': 'unchanged evidence', 'kind': 'ocr', 'locator': {}}]}
        self.doc = {'definition': 'definition', 'resolved': False, 'evidence_map': {'ocr-narration-EP': None}, 'curation': {'drafted_by': 'codex'}}
        self.snapshot = self.root / 'draft.json'
        self.snapshot.write_text(json.dumps({'frozen_at': '2026-10-03T17:00:00+00:00', 'record': self.doc}), encoding='utf-8')
        self.doc['curation']['automated_review'] = {'reviewer': 'codex', 'decision': 'accept', 'method': 'same_model_frozen_passes', 'limitations': review.SAME_MODEL_LIMITATION, 'review_started_at': '2026-10-03T18:00:00+00:00', 'frozen_draft': {'path': 'draft.json', 'sha256': hashlib.sha256(self.snapshot.read_bytes()).hexdigest()}, 'checks': {k: 'Evidence-specific check' for k in ['identity', 'meaning', 'usage', 'origins', 'events', 'queries']}}
        self.doc['curation']['automated_review']['fingerprint'] = review.fingerprint(self.doc, self.index)
        self.patch = patch.object(review, 'ROOT', self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_accept_and_loader_id_fill(self):
        self.assertIsNone(review.review_error(self.doc, self.index))
        self.doc['resolved'] = True
        self.doc['evidence_map']['ocr-narration-EP'] = 'database-id'
        self.assertIsNone(review.review_error(self.doc, self.index))

    def test_reject_unfrozen_same_model_and_false_independence(self):
        for key in ['frozen_draft', 'limitations', 'method']:
            doc = copy.deepcopy(self.doc)
            del doc['curation']['automated_review'][key]
            self.assertIsNotNone(review.review_error(doc, self.index))

    def test_reject_changed_artifact_or_record_even_with_new_review_hash(self):
        doc = copy.deepcopy(self.doc)
        doc['definition'] = 'new unsupported claim'
        doc['curation']['automated_review']['fingerprint'] = review.fingerprint(doc, self.index)
        self.assertIsNotNone(review.review_error(doc, self.index))
        self.snapshot.write_text('{}')
        self.assertIsNotNone(review.review_error(self.doc, self.index))

    def test_reject_pre_freeze_review_and_changed_evidence(self):
        doc = copy.deepcopy(self.doc)
        doc['curation']['automated_review']['review_started_at'] = '2026-10-03T16:00:00+00:00'
        self.assertIsNotNone(review.review_error(doc, self.index))
        self.index['EP'][0]['text'] = 'different evidence'
        self.assertIsNotNone(review.review_error(self.doc, self.index))

    def test_batch_scope_includes_zero_lineage_only_with_bound_narration(self):
        import yaml
        (self.root / 'ai_context').mkdir()
        (self.root / 'evals/feasibility').mkdir(parents=True)
        records = self.root / 'curation'
        records.mkdir()
        (self.root / 'ai_context/batch9.txt').write_text('EP\n')
        (self.root / 'evals/feasibility/lineage.csv').write_text('episode_id,meme_name\nOTHER,Other\n')
        valid = records / 'zero.yaml'
        valid.write_text(yaml.safe_dump({'canonical_name': 'No citations', 'curation': {'source_episodes': ['EP']}, 'evidence_map': {'ocr-narration-EP': None}}))
        for name, payload in [('unbound', {'curation': {'source_episodes': ['EP']}}), ('foreign', {'curation': {'source_episodes': ['OTHER']}, 'evidence_map': {'ocr-narration-OTHER': None}})]:
            (records / (name + '.yaml')).write_text(yaml.safe_dump({'canonical_name': name, **payload}))
        with patch.object(vault_loop, 'ROOT', self.root), patch.object(vault_loop, 'CURATION', records):
            self.assertEqual(vault_loop.batch_paths(9), [valid])


if __name__ == '__main__':
    unittest.main()
