#!/usr/bin/env python3
"""Offline regression tests for merge_literature_results.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("merge_literature_results.py")
SKILL_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merge_literature_results", SCRIPT)
assert SPEC and SPEC.loader
MERGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE)


class MergeLiteratureResultsTests(unittest.TestCase):
    def test_doi_normalization(self) -> None:
        variants = [
            "DOI: 10.1016/J.TEST.2024.1.",
            "https://doi.org/10.1016/J.TEST.2024.1",
            "http://dx.doi.org/10.1016/j.test.2024.1)",
        ]
        self.assertEqual({MERGE.normalize_doi(item) for item in variants}, {"10.1016/j.test.2024.1"})

    def test_end_to_end_merge_batch_and_reports(self) -> None:
        undermind = {
            "records": [
                {
                    "source": "undermind",
                    "title": "Learning in Complex Systems",
                    "authors": ["Li, Ming", "Wang, Qi"],
                    "year": 2024,
                    "doi": "https://doi.org/10.1016/J.TEST.2024.1.",
                    "cite_key": "um-1",
                    "source_rank": 1,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                },
                {
                    "source": "undermind",
                    "title": "A Distinct Springer Study",
                    "authors": ["Smith, Ana"],
                    "year": 2023,
                    "doi": "10.1007/s00100-023-00001-1",
                    "source_rank": 2,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                },
                {
                    "source": "undermind",
                    "title": "Unmapped Publisher Study",
                    "authors": ["Jones, Kai"],
                    "year": 2022,
                    "doi": "10.99999/example.1",
                    "source_rank": 3,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                },
                {
                    "source": "undermind",
                    "title": "Low Relevance Paper",
                    "authors": ["Other, O"],
                    "year": 2020,
                    "doi": "10.1016/low.1",
                    "source_rank": 4,
                    "relevance": "low",
                    "relevance_reason": "Peripheral.",
                },
                {
                    "source": "undermind",
                    "title": "Already Downloaded",
                    "authors": ["Done, Dana"],
                    "year": 2021,
                    "doi": "10.1016/done.1",
                    "source_rank": 5,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                    "download_status": "success",
                    "pdf_path": "/tmp/already.pdf",
                },
                {
                    "source": "undermind",
                    "title": "No Identifier Study",
                    "authors": ["Noid, Nora"],
                    "year": 2024,
                    "source_rank": 6,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                },
                {
                    "source": "undermind",
                    "title": "Effects of Intervention in Children: A Preprint",
                    "authors": ["Chen, Lin"],
                    "year": 2023,
                    "source_rank": 7,
                    "relevance": "high",
                    "relevance_reason": "Direct match.",
                },
            ]
        }
        scholar = {
            "records": [
                {
                    "source": "google_scholar",
                    "title": "Learning in Complex Systems",
                    "authors": ["Li, Ming"],
                    "year": 2023,
                    "doi": "doi:10.1016/j.test.2024.1",
                    "source_rank": 1,
                    "relevance": "high",
                    "relevance_reason": "Corroborating result.",
                },
                {
                    "source": "google_scholar",
                    "title": "No Identifier Study",
                    "authors": ["Noid, Nora"],
                    "year": 2023,
                    "source_rank": 2,
                    "relevance": "high",
                    "relevance_reason": "Same title and author.",
                },
                {
                    "source": "google_scholar",
                    "title": "Effects of an Intervention in Children",
                    "authors": ["Chen, Lin"],
                    "year": 2024,
                    "doi": "10.1007/s00200-024-00002-2",
                    "source_rank": 3,
                    "relevance": "high",
                    "relevance_reason": "Published version candidate.",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            undermind_path = root / "undermind.json"
            scholar_path = root / "scholar.json"
            undermind_path.write_text(json.dumps(undermind), encoding="utf-8")
            scholar_path.write_text(json.dumps(scholar), encoding="utf-8")
            exit_code = MERGE.main(
                [
                    "--undermind",
                    str(undermind_path),
                    "--scholar",
                    str(scholar_path),
                    "--output-dir",
                    str(root / "run"),
                    "--max-downloads",
                    "30",
                ]
            )
            self.assertEqual(exit_code, 0)
            manifest = json.loads((root / "run/reports/search_manifest.json").read_text(encoding="utf-8"))
            records = manifest["records"]

            merged = [record for record in records if record["doi"] == "10.1016/j.test.2024.1"]
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["sources"], ["google_scholar", "undermind"])
            self.assertEqual(len([record for record in records if record["title"] == "No Identifier Study"]), 1)

            version_records = [record for record in records if record["authors"] and record["authors"][0] == "Chen, Lin"]
            self.assertEqual(len(version_records), 2)
            self.assertTrue(all(record["possible_duplicate"] for record in version_records))
            no_doi_version = next(record for record in version_records if not record["doi"])
            self.assertFalse(no_doi_version["selected_for_download"])

            self.assertEqual(
                (root / "run/doi_batches/elsevier.txt").read_text().splitlines(),
                ["10.1016/j.test.2024.1"],
            )
            springer_batch = (root / "run/doi_batches/springer.txt").read_text().splitlines()
            self.assertEqual(
                springer_batch,
                ["10.1007/s00100-023-00001-1", "10.1007/s00200-024-00002-2"],
            )
            self.assertFalse((root / "run/doi_batches/unknown.txt").exists())
            self.assertNotIn("10.1016/done.1", (root / "run/doi_batches/elsevier.txt").read_text())
            self.assertNotIn("10.1016/low.1", (root / "run/doi_batches/elsevier.txt").read_text())

            unknown = next(record for record in records if record["doi"] == "10.99999/example.1")
            self.assertEqual(unknown["status_reason"], "profile_missing")
            no_identifier = next(record for record in records if record["title"] == "No Identifier Study")
            self.assertEqual(no_identifier["status_reason"], "metadata_resolution_failed")

            with (root / "run/reports/search_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_records = list(csv.DictReader(handle))
            self.assertTrue(csv_records)
            for row in csv_records:
                self.assertEqual(int(row["summary_success"]), manifest["summary"]["success"])
                self.assertEqual(int(row["summary_unverified"]), manifest["summary"]["unverified"])
                self.assertEqual(int(row["summary_missing"]), manifest["summary"]["missing"])
            report = (root / "run/reports/final_report.md").read_text(encoding="utf-8")
            for key in ("success", "unverified", "missing"):
                self.assertIn(f"- {key}: {manifest['summary'][key]}", report)

    def test_download_cap_and_high_relevance_only(self) -> None:
        records = [
            MERGE.clean_record(
                {
                    "source": "undermind",
                    "title": f"High {index}",
                    "authors": [f"Author {index}"],
                    "year": 2024,
                    "doi": f"10.1016/test.{index}",
                    "relevance": "high",
                },
                "undermind",
                index,
            )
            for index in range(35)
        ]
        records.append(
            MERGE.clean_record(
                {
                    "source": "undermind",
                    "title": "Medium",
                    "authors": ["Author M"],
                    "year": 2024,
                    "doi": "10.1016/test.medium",
                    "relevance": "medium",
                },
                "undermind",
                99,
            )
        )
        MERGE.assign_record_ids(records)
        MERGE.mark_possible_duplicates(records)
        MERGE.prepare_download_scope(records, 30)
        self.assertEqual(sum(record["selected_for_download"] for record in records), 30)
        medium = next(record for record in records if record["title"] == "Medium")
        self.assertFalse(medium["selected_for_download"])
        self.assertEqual(medium["download_status"], "not_selected")

    def test_same_metadata_more_than_one_year_apart_does_not_merge(self) -> None:
        left = MERGE.clean_record(
            {
                "source": "undermind",
                "title": "Stable Exact Title",
                "authors": ["Ming Li"],
                "year": 2020,
                "relevance": "high",
            },
            "undermind",
            1,
        )
        right = MERGE.clean_record(
            {
                "source": "google_scholar",
                "title": "Stable Exact Title",
                "authors": ["Li, Ming"],
                "year": 2022,
                "relevance": "high",
            },
            "google_scholar",
            1,
        )
        self.assertEqual(len(MERGE.deduplicate([left, right])), 2)

    def test_documented_scholar_and_elsevier_safety_contract(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        discovery_text = (SKILL_ROOT / "references/literature-discovery.md").read_text(encoding="utf-8")
        implementation_text = SCRIPT.read_text(encoding="utf-8")
        browser_command = (
            'instsci papers <doi-file> --publisher elsevier '
            '--institution "Beijing Normal University" --concurrency 1'
        )
        self.assertIn(browser_command, skill_text)
        self.assertIn(browser_command, discovery_text)
        self.assertIn("second challenge/risk event", discovery_text)
        self.assertIn("Two consecutive timeouts stop Scholar", discovery_text)
        self.assertIn("Scholar empty", discovery_text)
        for forbidden in ("fetch_paper", "instsci fetch", "elsevier-setup", "api.elsevier.com"):
            self.assertNotIn(forbidden, implementation_text)


if __name__ == "__main__":
    unittest.main()
