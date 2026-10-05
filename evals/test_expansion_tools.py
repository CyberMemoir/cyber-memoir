"""Regression tests for the expansion tooling; no services or corpus mutations."""
import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "feasibility"))
import build_gold
import build_materials
import prep
import validate_curation
from automation_review import fingerprint, review_error


class ExpansionToolsTests(unittest.TestCase):
    def test_loader_stops_after_a_failed_http_publication(self):
        import httpx
        import yaml
        from unittest.mock import MagicMock
        import load_curation
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("first.yaml", "second.yaml")]
            for path in paths:
                path.write_text(yaml.safe_dump({"canonical_name": path.stem, "evidence_map": {"key": None}}), encoding="utf-8")
            original = [path.read_bytes() for path in paths]
            loader = MagicMock()
            loader.sources = {"EP": "source-id"}
            loader.source_for.return_value = "source-id"
            loader.material.return_value = "evidence-id"
            response = httpx.Response(503, text="service unavailable", request=httpx.Request("POST", "http://example.test/approve"))
            loader.publish.side_effect = httpx.HTTPStatusError("unavailable", request=response.request, response=response)
            draft = {"claims": [{"evidence_ids": ["evidence-id"]}], "events": [], "relations": []}
            with patch.object(sys, "argv", ["load_curation", *map(str, paths)]), patch.object(load_curation, "Loader", return_value=loader), patch.object(load_curation, "load_material_index", return_value={}), patch.object(load_curation, "load_platform_index", return_value={}), patch.object(load_curation, "resolve_placeholder", return_value=("EP", {"text": "unchanged evidence"})), patch.object(load_curation, "build_draft", return_value=draft):
                self.assertEqual(load_curation.main(), 1)
            self.assertEqual(loader.publish.call_count, 1)
            self.assertEqual(loader.material.call_count, 1)
            self.assertEqual([path.read_bytes() for path in paths], original)

    def test_drafts_preserve_existing_files_and_have_stable_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sheet = root / "lineage.csv"
            names = ["XX做了噩梦", "XX的实力并不强", "纯中文", "另一个中文"]
            def write_sheet(items):
                with sheet.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["meme_name", "role", "upload_date", "bv_id", "episode_id", "title"])
                    writer.writeheader()
                    for name in items:
                        writer.writerow(dict(meme_name=name, role="derivative", upload_date="20260101", bv_id="BV1234567890", episode_id="BV0987654321", title="视频"))
            existing = root / "xx.yaml"
            existing.write_text('canonical_name: "已发布"\nslug: xx\n', encoding="utf-8")
            write_sheet(names + ["已发布"])
            prep.build_drafts(sheet, root)
            before = {p.name: p.read_bytes() for p in root.glob("*.yaml")}
            self.assertEqual(len(before), 5)
            write_sheet(["更早排序的梗"] + names + ["已发布"])
            prep.build_drafts(sheet, root)
            for name, content in before.items():
                self.assertEqual((root / name).read_bytes(), content)

    def test_drafts_refuse_an_occupied_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = "中文"
            slug = "meme-" + hashlib.sha256(name.encode()).hexdigest()[:16]
            occupied = root / (slug + ".yaml")
            occupied.write_text("canonical_name: 别的梗\n", encoding="utf-8")
            sheet = root / "lineage.csv"
            sheet.write_text("meme_name,role,upload_date,bv_id,episode_id,title\n中文,derivative,20260101,BV1234567890,BV0987654321,视频\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                prep.build_drafts(sheet, root)
            self.assertEqual(occupied.read_text(encoding="utf-8"), "canonical_name: 别的梗\n")

    def test_long_timestamps_sort_numerically(self):
        streams = ({"text": "1001.0s 长视频\n999.0s 较早"}, {"text": "1000.0s 画面"})
        with patch.object(build_materials, "narration_by_position", return_value=streams):
            self.assertEqual(build_materials.timeline([]), ["999.0s 解说｜较早", "1000.0s 画面｜画面", "1001.0s 解说｜长视频"])

    def test_quote_containing_name_stays_intact(self):
        self.assertEqual(validate_curation.literals('「未来的自己看到过去的自己时」', ["看到过去的自己"]), ["未来的自己看到过去的自己时"])
        self.assertEqual(validate_curation.literals('「看到过去的自己」', ["看到过去的自己"]), [])

    def test_scalar_description_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "_descriptions.yaml").write_text("梗: -查询\n", encoding="utf-8")
            self.assertIsNone(prep.load_descriptions(root))

    def test_review_invalidated_by_record_or_material_change(self):
        import copy
        index = {"EP": [{"text": "原文", "kind": "ocr", "locator": {}}]}
        doc = {"definition": "解释", "resolved": False, "evidence_map": {"ocr-narration-EP": None}, "curation": {"drafted_by": "deepseek"}}
        review = {"decision": "accept", "reviewer": "gpt", "checks": {k: "Checked original evidence" for k in ["identity", "meaning", "usage", "origins", "events", "queries"]}}
        doc["curation"]["automated_review"] = review
        review["fingerprint"] = fingerprint(doc, index)
        self.assertIsNone(review_error(doc, index))
        doc["resolved"] = True
        doc["evidence_map"]["ocr-narration-EP"] = "database-id"
        self.assertIsNone(review_error(doc, index))
        modified = copy.deepcopy(doc)
        modified["definition"] = "另一个解释"
        self.assertIsNotNone(review_error(modified, index))
        index["EP"][0]["text"] = "改动过的证据"
        self.assertIsNotNone(review_error(doc, index))

    def test_self_review_and_incomplete_review_rejected(self):
        doc = {"curation": {"drafted_by": "deepseek", "automated_review": {"reviewer": "deepseek", "decision": "accept"}}}
        self.assertIsNotNone(review_error(doc, {}))
        doc["curation"]["automated_review"]["reviewer"] = "gpt"
        self.assertIsNotNone(review_error(doc, {}))

    def test_gold_excludes_unpublished_and_separates_model_queries(self):
        import json

        import yaml
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, published, source in [("human", True, "human"), ("model", True, "model"), ("pending", False, "human")]:
                doc = {"canonical_name": name, "resolved": published, "definition": "text", "gold": {"description": ["query-" + name], "description_source": source}}
                (root / (name + ".yaml")).write_text(yaml.safe_dump(doc), encoding="utf-8")
            (root / "_negatives.yaml").write_text("negatives: []\n", encoding="utf-8")
            output = root / "gold.jsonl"
            with patch.object(build_gold, "CURATION", root), patch.object(sys, "argv", ["build_gold", "--out", str(output)]):
                build_gold.main()
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({r["bucket"] for r in rows}, {"description", "description_model"})
            self.assertNotIn("query-pending", {r["query"] for r in rows})


if __name__ == "__main__":
    unittest.main()
