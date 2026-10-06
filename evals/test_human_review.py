"""Publication risks: missing consent, stale evidence and direct-loader bypass."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import human_review
import load_curation
import vault_loop
from automation_review import fingerprint


class HumanReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "example.yaml"
        self.doc = {"canonical_name": "example", "definition": "original",
                    "curation": {"automated_review": {"decision": "accept"}},
                    "evidence_map": {"ocr-narration-EP": None}}
        self.index = {"EP": [{"text": "original evidence", "locator": {}}]}
        self.patch = patch.object(human_review, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def approve(self):
        target = self.root / "ai_context/human_approvals/example.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"reviewer": "Vincent", "decision": "approve",
            "canonical_name": "example", "fingerprint": fingerprint(self.doc, self.index),
            "approved_at": "2026-10-06T12:00:00+00:00", "authorization": "第1条通过"}))

    def test_explicit_approval_and_database_id_fill(self):
        self.assertIsNotNone(human_review.approval_error(self.doc, self.index, self.path))
        self.approve()
        self.assertIsNone(human_review.approval_error(self.doc, self.index, self.path))
        self.doc["resolved"] = True
        self.doc["evidence_map"]["ocr-narration-EP"] = "database-id"
        self.assertIsNone(human_review.approval_error(self.doc, self.index, self.path))

    def test_changed_claim_or_evidence_invalidates_consent(self):
        self.approve()
        self.doc["definition"] = "changed"
        self.assertIsNotNone(human_review.approval_error(self.doc, self.index, self.path))
        self.doc["definition"] = "original"
        self.index["EP"][0]["text"] = "changed evidence"
        self.assertIsNotNone(human_review.approval_error(self.doc, self.index, self.path))

    def test_direct_loader_refuses_before_api_client(self):
        self.path.write_text(yaml.safe_dump(self.doc))
        with patch.object(sys, "argv", ["load_curation", str(self.path)]), \
             patch.object(load_curation, "load_material_index", return_value=self.index), \
             patch.object(load_curation, "load_platform_index", return_value={}), \
             patch.object(load_curation, "Loader") as loader:
            self.assertEqual(load_curation.main(), 1)
            loader.assert_not_called()

    def test_batch_publish_waits_and_cards_show_real_usage(self):
        self.doc['usage_context'] = 'actual usage'
        self.path.write_text(yaml.safe_dump(self.doc))
        output = self.root / 'cards.md'
        human_review.write_cards([{'path': str(self.path), 'record': self.doc,
            'fingerprint': fingerprint(self.doc, self.index),
            'materials': {'ocr-narration-EP': ('EP', self.index['EP'][0])}}], 18, output)
        self.assertIn('actual usage', output.read_text(encoding='utf-8'))
        self.assertIn('original evidence', output.read_text(encoding='utf-8'))
        with patch.object(sys, 'argv', ['vault_loop', 'publish', '--batch', '18']), \
             patch.object(vault_loop, 'batch_paths', return_value=[self.path]), \
             patch.object(vault_loop, 'load_material_index', return_value=self.index), \
             patch.object(vault_loop, 'validate', return_value=SimpleNamespace(errors=[])), \
             patch.object(vault_loop, 'review_error', return_value=None), \
             patch.object(vault_loop.subprocess, 'call') as publish:
            self.assertEqual(vault_loop.main(), 1)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
