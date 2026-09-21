#!/usr/bin/env python3
"""Merge discovery results and create safe publisher-specific DOI batches.

This script is offline: it does not query Scholar, call publisher APIs, or
download PDFs. It normalizes metadata, applies conservative deduplication,
uses the installed InstSci environment for publisher inference, and writes
JSON/CSV/Markdown manifests plus one DOI file per publisher.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit


SOURCE_PRIORITY = {
    "publisher_metadata": 30,
    "doi_metadata": 30,
    "crossref": 30,
    "undermind": 20,
    "google_scholar": 10,
    "scholar": 10,
}
RELEVANCE_PRIORITY = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
TRAILING_DOI_PUNCTUATION = ".,;:)]}>\"'"
CSV_FIELDS = [
    "record_id",
    "title",
    "authors",
    "year",
    "doi",
    "url",
    "cite_keys",
    "sources",
    "source_ranks",
    "relevance",
    "relevance_reason",
    "possible_duplicate",
    "possible_duplicate_of",
    "publisher",
    "selected_for_download",
    "download_status",
    "status_reason",
    "pdf_path",
    "next_action",
    "summary_success",
    "summary_unverified",
    "summary_missing",
]


def normalize_doi(value: Any) -> str:
    """Return a comparison-safe DOI, or an empty string for invalid input."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = unquote(text).strip()
    if "?" in text or "#" in text:
        parsed = urlsplit(f"https://doi.org/{text}")
        text = parsed.path.lstrip("/")
    text = text.rstrip(TRAILING_DOI_PUNCTUATION).strip()
    match = re.search(r"10\.\d{4,9}/\S+", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(TRAILING_DOI_PUNCTUATION).lower()


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_version_title(value: Any) -> str:
    """Normalize only for possible-version detection, never auto-merging."""
    text = normalize_title(value)
    version_markers = {
        "preprint",
        "postprint",
        "manuscript",
        "accepted",
        "version",
        "author",
        "authors",
        "a",
        "an",
        "the",
    }
    return " ".join(token for token in text.split() if token not in version_markers)


def normalize_author(value: Any) -> str:
    original = str(value or "")
    text = unicodedata.normalize("NFKC", original).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    # Exact-title merging can tolerate display-order changes such as
    # "Li, Ming" versus "Ming Li", but not a different token set.
    return " ".join(sorted(text.split()))


def parse_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part for part in re.split(r"\s*;\s*|\s+and\s+", value.strip()) if part]
    return []


def parse_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    match = re.search(r"(?:19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def normalize_relevance(value: Any) -> str:
    if isinstance(value, (int, float)):
        return "high" if value >= 0.75 else "medium" if value >= 0.4 else "low"
    text = str(value or "").strip().casefold()
    if text in {"high", "highly relevant", "high_relevance", "relevant", "3"}:
        return "high"
    if text in {"medium", "moderate", "2"}:
        return "medium"
    if text in {"low", "irrelevant", "1"}:
        return "low"
    return "unknown"


def source_names(value: Any, fallback: str) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    names = [str(item).strip().casefold() for item in raw if str(item or "").strip()]
    return names or [fallback]


def source_priority(record: dict[str, Any]) -> int:
    return max((SOURCE_PRIORITY.get(name, 0) for name in record["sources"]), default=0)


def first_author(record: dict[str, Any]) -> str:
    authors = record.get("authors") or []
    return normalize_author(authors[0]) if authors else ""


def year_close(left: dict[str, Any], right: dict[str, Any], tolerance: int = 1) -> bool:
    a, b = left.get("year"), right.get("year")
    return isinstance(a, int) and isinstance(b, int) and abs(a - b) <= tolerance


def exact_metadata_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(
        left["normalized_title"]
        and left["normalized_title"] == right["normalized_title"]
        and first_author(left)
        and first_author(left) == first_author(right)
        and year_close(left, right)
    )


def clean_record(raw: dict[str, Any], fallback_source: str, ordinal: int) -> dict[str, Any]:
    sources = source_names(raw.get("sources", raw.get("source")), fallback_source)
    rank = raw.get("source_rank", ordinal)
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        rank = ordinal
    cite_keys = raw.get("cite_keys")
    if not isinstance(cite_keys, list):
        cite_keys = [raw.get("cite_key")] if raw.get("cite_key") else []
    source_ranks = raw.get("source_ranks")
    if not isinstance(source_ranks, dict):
        source_ranks = {name: rank for name in sources}
    record = {
        "title": str(raw.get("title") or "").strip(),
        "authors": parse_authors(raw.get("authors")),
        "year": parse_year(raw.get("year")),
        "doi": normalize_doi(raw.get("doi")),
        "url": str(raw.get("url") or "").strip(),
        "cite_keys": sorted({str(key).strip() for key in cite_keys if str(key or "").strip()}),
        "sources": sorted(set(sources)),
        "source_ranks": source_ranks,
        "relevance": normalize_relevance(raw.get("relevance")),
        "relevance_reason": str(raw.get("relevance_reason") or "").strip(),
        "abstract": str(raw.get("abstract") or "").strip(),
        "pdf_url": str(raw.get("pdf_url") or "").strip(),
        "pdf_path": str(raw.get("pdf_path") or "").strip(),
        "download_status": str(raw.get("download_status") or "").strip().casefold(),
        "status_reason": str(raw.get("status_reason") or "").strip(),
        "publisher": str(raw.get("publisher") or "").strip().casefold(),
        "next_action": str(raw.get("next_action") or "").strip(),
        "possible_duplicate": False,
        "possible_duplicate_of": [],
    }
    record["normalized_title"] = normalize_title(record["title"])
    return record


def load_records(path: Path | None, fallback_source: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = next(
            (payload[key] for key in ("records", "results", "papers") if isinstance(payload.get(key), list)),
            None,
        )
        if raw_records is None:
            raise ValueError(f"{path}: expected a list or a records/results/papers array")
    else:
        raise ValueError(f"{path}: expected a JSON object or array")
    cleaned = []
    for ordinal, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: record {ordinal} is not an object")
        cleaned.append(clean_record(raw, fallback_source, ordinal))
    return cleaned


def choose_value(records: list[dict[str, Any]], field_name: str) -> Any:
    candidates = [record for record in records if record.get(field_name) not in (None, "", [])]
    if not candidates:
        return [] if field_name in {"authors", "cite_keys"} else ""
    candidates.sort(
        key=lambda record: (
            source_priority(record),
            -min(record.get("source_ranks", {}).values(), default=999999),
            len(str(record.get(field_name) or "")),
        ),
        reverse=True,
    )
    return candidates[0][field_name]


def merge_cluster(records: list[dict[str, Any]]) -> dict[str, Any]:
    best = max(records, key=lambda record: (source_priority(record), bool(record["doi"])))
    merged = dict(best)
    for field_name in (
        "title",
        "authors",
        "year",
        "doi",
        "url",
        "abstract",
        "pdf_url",
        "pdf_path",
        "publisher",
        "download_status",
        "status_reason",
        "next_action",
    ):
        value = choose_value(records, field_name)
        if value not in (None, "", []):
            merged[field_name] = value
    merged["sources"] = sorted({source for record in records for source in record["sources"]})
    merged["cite_keys"] = sorted({key for record in records for key in record["cite_keys"]})
    merged["source_ranks"] = {
        source: min(
            record["source_ranks"].get(source, 999999)
            for record in records
            if source in record["sources"]
        )
        for source in merged["sources"]
    }
    merged["relevance"] = max(
        (record["relevance"] for record in records),
        key=lambda value: RELEVANCE_PRIORITY[value],
    )
    reasons = []
    for record in sorted(records, key=source_priority, reverse=True):
        reason = record["relevance_reason"]
        if reason and reason not in reasons:
            reasons.append(reason)
    merged["relevance_reason"] = " | ".join(reasons)
    merged["normalized_title"] = normalize_title(merged["title"])
    merged["possible_duplicate"] = False
    merged["possible_duplicate_of"] = []
    return merged


def deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doi_groups: dict[str, list[dict[str, Any]]] = {}
    without_doi: list[dict[str, Any]] = []
    for record in records:
        if record["doi"]:
            doi_groups.setdefault(record["doi"], []).append(record)
        else:
            without_doi.append(record)
    clusters = [group for _, group in sorted(doi_groups.items())]
    for record in without_doi:
        matching = next(
            (cluster for cluster in clusters if all(exact_metadata_match(record, member) for member in cluster)),
            None,
        )
        if matching is None:
            clusters.append([record])
        else:
            matching.append(record)
    return [merge_cluster(cluster) for cluster in clusters]


def assign_record_ids(records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for record in records:
        seed = record["doi"] or "|".join(
            [record["normalized_title"], first_author(record), str(record.get("year") or "")]
        )
        base = "doi:" + record["doi"] if record["doi"] else "meta:" + hashlib.sha1(seed.encode()).hexdigest()[:12]
        record_id = base
        suffix = 2
        while record_id in seen:
            record_id = f"{base}:{suffix}"
            suffix += 1
        record["record_id"] = record_id
        seen.add(record_id)


def mark_possible_duplicates(records: list[dict[str, Any]]) -> None:
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            if not left["normalized_title"] or not right["normalized_title"]:
                continue
            left_version_title = normalize_version_title(left["title"])
            right_version_title = normalize_version_title(right["title"])
            ratio = SequenceMatcher(None, left_version_title, right_version_title).ratio()
            authors_match = first_author(left) and first_author(left) == first_author(right)
            years_plausible = year_close(left, right, tolerance=2)
            if ratio >= 0.9 and authors_match and years_plausible:
                left["possible_duplicate"] = True
                right["possible_duplicate"] = True
                left["possible_duplicate_of"].append(right["record_id"])
                right["possible_duplicate_of"].append(left["record_id"])


def instsci_profile_data(dois: Iterable[str]) -> tuple[dict[str, str], set[str]]:
    unique = sorted({doi for doi in dois if doi})
    if not unique:
        return {}, set()
    code = (
        "import json,sys; "
        "from instsci.publisher_profiles import infer_publisher_profile,list_publisher_profiles,get_publisher_profile; "
        "profiles={k:get_publisher_profile(k) for k in list_publisher_profiles()}; "
        "mapping={d:next((k for k,p in profiles.items() if p==infer_publisher_profile(d)),'' ) for d in sys.argv[1:]}; "
        "print(json.dumps({'mapping':mapping,'profiles':sorted(profiles)}))"
    )
    interpreters: list[str] = [sys.executable]
    executable = shutil.which("instsci")
    if executable:
        try:
            first_line = Path(executable).read_text(encoding="utf-8").splitlines()[0]
            if first_line.startswith("#!"):
                interpreters.append(first_line[2:].strip())
        except (OSError, UnicodeError, IndexError):
            pass
    for interpreter in dict.fromkeys(interpreters):
        try:
            result = subprocess.run(
                [interpreter, "-c", code, *unique],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            mapping = {key: value for key, value in payload["mapping"].items() if value}
            return mapping, set(payload["profiles"])
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            continue
    return {}, set()


def minimum_source_rank(record: dict[str, Any]) -> int:
    return min(record.get("source_ranks", {}).values(), default=999999)


def prepare_download_scope(records: list[dict[str, Any]], max_downloads: int) -> None:
    inferred, available_profiles = instsci_profile_data(record["doi"] for record in records)
    for record in records:
        supplied = record["publisher"]
        record["publisher"] = supplied if supplied in available_profiles else inferred.get(record["doi"], "")

    candidates = [record for record in records if record["relevance"] == "high"]
    candidates.sort(
        key=lambda record: (
            0 if record["doi"] else 1,
            0 if "undermind" in record["sources"] else 1,
            minimum_source_rank(record),
            record["title"].casefold(),
        )
    )
    selected_ids: set[str] = set()
    for record in candidates:
        if len(selected_ids) >= max_downloads:
            break
        doi_preferred = any(
            other["doi"]
            and other["record_id"] in record["possible_duplicate_of"]
            and other["relevance"] == "high"
            for other in records
        )
        if doi_preferred and not record["doi"]:
            record["next_action"] = record["next_action"] or "Review possible duplicate; DOI-bearing version is preferred."
            continue
        selected_ids.add(record["record_id"])

    for record in records:
        record["selected_for_download"] = record["record_id"] in selected_ids
        if not record["selected_for_download"]:
            record["download_status"] = record["download_status"] or "not_selected"
            if record["relevance"] != "high":
                record["status_reason"] = record["status_reason"] or "relevance_below_high"
                record["next_action"] = record["next_action"] or "Not selected: relevance is below high."
            elif any(
                other["doi"] and other["record_id"] in record["possible_duplicate_of"]
                for other in records
            ):
                record["status_reason"] = record["status_reason"] or "doi_version_preferred"
                record["next_action"] = record["next_action"] or "Review possible duplicate; DOI-bearing version is preferred."
            else:
                record["status_reason"] = record["status_reason"] or "download_cap_reached"
                record["next_action"] = record["next_action"] or "Not selected: download cap reached."
            continue
        status = record["download_status"]
        if status == "success":
            record["next_action"] = record["next_action"] or "None; verified PDF already exists."
        elif record["pdf_url"]:
            record["download_status"] = status or "pending"
            record["next_action"] = record["next_action"] or "Download and verify the lawful Open Access PDF first."
        elif not record["doi"]:
            record["download_status"] = "missing"
            record["status_reason"] = "metadata_resolution_failed"
            record["next_action"] = record["next_action"] or "Resolve DOI or locate a lawful Open Access PDF."
        elif not record["publisher"]:
            record["download_status"] = "missing"
            record["status_reason"] = "profile_missing"
            record["next_action"] = record["next_action"] or "Add or verify an InstSci publisher profile."
        else:
            record["download_status"] = status or "pending"
            record["next_action"] = record["next_action"] or f"Run the {record['publisher']} DOI batch in visible InstSci browser mode."


def report_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    scoped = [record for record in records if record["selected_for_download"]]
    return {
        "success": sum(record["download_status"] == "success" for record in scoped),
        "unverified": sum(record["download_status"] == "unverified" for record in scoped),
        "missing": sum(record["download_status"] == "missing" for record in scoped),
        "pending": sum(record["download_status"] in {"", "pending"} for record in scoped),
        "selected": len(scoped),
        "total_records": len(records),
        "possible_duplicates": sum(record["possible_duplicate"] for record in records),
    }


def output_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "normalized_title"}


def write_batches(records: list[dict[str, Any]], batch_dir: Path) -> dict[str, list[str]]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    for stale_batch in batch_dir.glob("*.txt"):
        stale_batch.unlink()
    batches: dict[str, list[str]] = {}
    for record in records:
        if not record["selected_for_download"] or record["download_status"] == "success":
            continue
        if not record["doi"] or not record["publisher"] or record["pdf_url"]:
            continue
        batches.setdefault(record["publisher"], []).append(record["doi"])
    for publisher, dois in sorted(batches.items()):
        unique = sorted(set(dois))
        (batch_dir / f"{publisher}.txt").write_text("\n".join(unique) + "\n", encoding="utf-8")
        batches[publisher] = unique
    return batches


def write_json(path: Path, records: list[dict[str, Any]], summary: dict[str, int], batches: dict[str, list[str]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "publisher_batches": batches,
        "records": [output_record(record) for record in records],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv_row(record: dict[str, Any], summary: dict[str, int]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "title": record["title"],
        "authors": "; ".join(record["authors"]),
        "year": record["year"] or "",
        "doi": record["doi"],
        "url": record["url"],
        "cite_keys": "; ".join(record["cite_keys"]),
        "sources": "; ".join(record["sources"]),
        "source_ranks": json.dumps(record["source_ranks"], ensure_ascii=False, sort_keys=True),
        "relevance": record["relevance"],
        "relevance_reason": record["relevance_reason"],
        "possible_duplicate": str(record["possible_duplicate"]).lower(),
        "possible_duplicate_of": "; ".join(record["possible_duplicate_of"]),
        "publisher": record["publisher"],
        "selected_for_download": str(record["selected_for_download"]).lower(),
        "download_status": record["download_status"],
        "status_reason": record["status_reason"],
        "pdf_path": record["pdf_path"],
        "next_action": record["next_action"],
        "summary_success": summary["success"],
        "summary_unverified": summary["unverified"],
        "summary_missing": summary["missing"],
    }


def write_csv(path: Path, records: list[dict[str, Any]], summary: dict[str, int]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_row(record, summary) for record in records)


def md_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def write_markdown(path: Path, records: list[dict[str, Any]], summary: dict[str, int], batches: dict[str, list[str]]) -> None:
    lines = [
        "# Literature Search and Download Report",
        "",
        f"- Total records: {summary['total_records']}",
        f"- Selected for download: {summary['selected']}",
        f"- success: {summary['success']}",
        f"- unverified: {summary['unverified']}",
        f"- missing: {summary['missing']}",
        f"- pending: {summary['pending']}",
        "",
        "## Publisher batches",
        "",
    ]
    if batches:
        lines.extend(f"- `{publisher}`: {len(dois)} DOI(s)" for publisher, dois in sorted(batches.items()))
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Records",
            "",
            "| Title | DOI | Sources | Relevance reason | Duplicate relation | Publisher | Status | PDF path | Next action |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for record in records:
        duplicate = "; ".join(record["possible_duplicate_of"]) if record["possible_duplicate"] else ""
        status = record["download_status"]
        if record["status_reason"]:
            status = f"{status} ({record['status_reason']})"
        lines.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    record["title"],
                    record["doi"],
                    "; ".join(record["sources"]),
                    record["relevance_reason"],
                    duplicate,
                    record["publisher"],
                    status,
                    record["pdf_path"],
                    record["next_action"],
                )
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--undermind", type=Path, help="Undermind discovery JSON")
    parser.add_argument("--scholar", type=Path, help="Google Scholar discovery JSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="Run directory")
    parser.add_argument("--max-downloads", type=int, default=30, help="Maximum high-relevance records to select")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.undermind and not args.scholar:
        raise SystemExit("At least one of --undermind or --scholar is required")
    if args.max_downloads < 1:
        raise SystemExit("--max-downloads must be at least 1")
    records = load_records(args.undermind, "undermind") + load_records(args.scholar, "google_scholar")
    merged = deduplicate(records)
    assign_record_ids(merged)
    mark_possible_duplicates(merged)
    prepare_download_scope(merged, args.max_downloads)
    merged.sort(
        key=lambda record: (
            not record["selected_for_download"],
            minimum_source_rank(record),
            record["title"].casefold(),
        )
    )

    reports_dir = args.output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "downloads").mkdir(parents=True, exist_ok=True)
    batches = write_batches(merged, args.output_dir / "doi_batches")
    summary = report_summary(merged)
    write_json(reports_dir / "search_manifest.json", merged, summary, batches)
    write_csv(reports_dir / "search_manifest.csv", merged, summary)
    write_markdown(reports_dir / "final_report.md", merged, summary, batches)
    print(json.dumps({"summary": summary, "publisher_batches": batches}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
