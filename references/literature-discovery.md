# Literature Discovery and Download Workflow

Use this reference only for a topic-led literature run. Direct DOI and publisher-only tasks use `publisher-pdf-workflow.md`.

## 1. Run Initialization

Create a new directory under `~/.instsci/runs/` using a short ASCII topic slug and a local timestamp. Never reuse a directory from an earlier run.

Create these subdirectories before discovery:

```text
discovery/
doi_batches/
downloads/
reports/
```

Save all machine-readable text as UTF-8 JSON. Do not write cookies, credentials, API keys, tokens, or browser storage into the run.

## 2. Undermind-First Discovery

1. Read Undermind orientation before calling search tools.
2. List workspaces and retain only writable workspaces.
3. If exactly one is writable, use it automatically. If several are writable, ask the user which one to use. If none are writable, report the connection problem and stop discovery rather than guessing.
4. Treat the user's research topic as a natural-language research objective. Make the deep-search prompt self-contained: describe the question, scope, and any explicit exclusions or date/language limits supplied by the user. Do not manufacture a traditional Boolean string for Undermind.
5. Reuse an existing deep search only when the user explicitly identifies the run as a continuation. Otherwise launch a new deep search.
6. Inspect the first 30 ranked results. Obtain title, abstract, authors, year, DOI, cite key, source rank, landing URL, and Open Access PDF status where available.
7. Retain at most 20 papers that directly address the question. Save `relevance: "high"` and a one- or two-sentence `relevance_reason` for retained papers. Keep screened-out candidates only when useful for an audit, with lower relevance.

Judge relevance across these dimensions, adapting them to the discipline:

- research object, population, material, setting, or system;
- central variable, mechanism, exposure, or intervention;
- outcome, phenomenon, or dependent variable;
- method or study design when method is part of the question;
- topic centrality: the issue is studied directly rather than mentioned incidentally.

Do not require every dimension when the research question does not contain it. A flexible evidence-based judgment is preferable to a mechanical score.

Save records to `discovery/undermind.json`. A top-level `records` array is recommended.

## 3. Scholar Query Construction

Use the original topic plus high-relevance Undermind titles and abstracts to derive 2–4 concept groups. Typical groups represent the object/population, mechanism or intervention, outcome, and method. Omit groups that would overconstrain the search.

For each group:

1. Generate English synonyms, abbreviations, spelling variants, and common natural-language expressions.
2. Keep no more than six terms after cleaning.
3. Normalize Unicode with NFKC, trim whitespace, compare case-insensitively, normalize punctuation, and remove trivial singular/plural duplicates.
4. Remove a shorter term when it is merely contained in a longer term and adds no independent meaning. Retain both when they have distinct search behavior.
5. Put multiword phrases in straight double quotes.
6. Do not use `*` truncation.
7. Do not require MeSH. For a biomedical topic, consult MeSH only when it materially improves terminology; convert inverted headings such as `Neoplasms, Lung` into natural English before using them.

Generate 2–4 compact queries. Prefer several interpretable queries over one long Boolean expression. Each query should combine only the concept groups needed to cover a distinct facet or terminology variant.

Save the plan to `discovery/search_queries.json`, including concept groups, cleaned terms, the final query strings, and a short rationale for each query.

## 4. Human-Supervised Google Scholar

Google Scholar explicitly disallows bulk automated extraction; follow the [official Scholar help](https://scholar.google.com/intl/uk/scholar/help.html). Use it only as a small, supplementary, human-supervised source.

- Use normal, visible Chrome and keep one persistent session for the task.
- Reuse one tab and execute queries serially.
- Read only the fields visible in standard result cards: title, displayed authors/venue/year, result URL, snippet, and any visible PDF link.
- Read page 1 by default.
- Open page 2 only if that query produced fewer than five candidates not already present in the Undermind set and there is no CAPTCHA, unusual-traffic warning, or timeout signal.
- Do not run queries in parallel tabs, auto-refresh, expand `Cited by` lists in bulk, or traverse deep result pages.
- Do not use CloakBrowser, headless browsers, proxy rotation, browser-fingerprint changes, CAPTCHA solvers, or other techniques intended to evade detection.

When a CAPTCHA or explicit challenge appears:

1. Leave the page open and unchanged.
2. Tell the user exactly which visible page needs manual completion.
3. Wait for the user; do not click the CAPTCHA or enter account credentials.
4. After manual completion, continue at the same conservative rate.
5. If a second challenge/risk event occurs in the same run, stop Scholar and continue with Undermind-only results.

Count a page timeout only after a normal page load has had a reasonable opportunity to complete. Retry once without refreshing repeatedly. Two consecutive timeouts stop Scholar for the run. Empty results are not retried with rapid query variations; proceed to the next planned query or finish.

Save collected records to `discovery/google_scholar.json`. Scholar failure never invalidates `undermind.json`.

## 5. Unified Record Shape

Every discovery record must contain these keys, using an empty string or empty list when unavailable:

```json
{
  "source": "undermind",
  "title": "Article title",
  "authors": ["First Author", "Second Author"],
  "year": 2024,
  "doi": "10.xxxx/xxxxx",
  "url": "https://example.org/article",
  "cite_key": "workspace-key-if-any",
  "source_rank": 1,
  "relevance": "high",
  "relevance_reason": "Directly studies the target mechanism and outcome."
}
```

Optional useful keys include `abstract`, `pdf_url`, `pdf_path`, `download_status`, `status_reason`, and `publisher`. The merge script preserves recognized optional download fields.

Use `source: "google_scholar"` for Scholar. Publisher or DOI metadata added later may use `doi_metadata` or `publisher_metadata`; it has higher field priority than discovery metadata.

## 6. Deterministic Merge and Deduplication

Run `scripts/merge_literature_results.py` after both discovery branches finish or immediately after Scholar stops.

The script applies these rules:

1. Normalize a DOI to lowercase; remove `doi:`, `https://doi.org/`, `http://dx.doi.org/`, surrounding whitespace, query/fragment suffixes, and terminal citation punctuation.
2. Merge records with the same non-empty normalized DOI.
3. When either record lacks a DOI, auto-merge only if normalized titles are exactly equal, normalized first authors are equal, and both years exist with an absolute difference no greater than one.
4. Never use fuzzy title similarity as an automatic merge rule.
5. Mark highly similar unresolved pairs as `possible_duplicate` while retaining both records. This is especially important for preprint, conference, accepted-manuscript, and journal versions.
6. Prefer metadata fields from publisher/DOI metadata, then Undermind, then Scholar.
7. Preserve a `sources` array and all source ranks/cite keys that survive the merge.
8. Prefer a DOI-bearing formal version for download when a non-DOI possible duplicate exists, but keep both records in the manifest.
9. Select only high-relevance records for default download, capped at 30 after deduplication.

Do not manually edit publisher batches to combine unknown or different publishers. Rerun the script after correcting source metadata.

## 7. Open Access First

For selected Undermind papers with an Open Access `pdf_url`:

1. Download only from the returned lawful link.
2. Confirm that the file begins with `%PDF` rather than HTML.
3. Reject implausibly small or empty files unless manually inspected.
4. Confirm a readable page count.
5. Extract text from early pages and compare the DOI or normalized title.
6. Mark `success` only after verification; use `unverified` when a real PDF exists but identity cannot be established.

Do not guess PDF URLs for records without a DOI or an explicit lawful PDF link.

## 8. Publisher Batches and InstSci

The merge script uses InstSci's installed publisher-profile inference and writes one file per recognized profile under `doi_batches/`. A DOI with no inferred profile stays out of all batches.

Run publishers serially with `--concurrency 1`, a persistent browser profile, and the session broker. Use the configured Beijing Normal University route unless the user explicitly supplies another institution.

Elsevier must use:

```bash
instsci papers <doi-file> --publisher elsevier --institution "Beijing Normal University" --concurrency 1
```

Do not try Elsevier API full text first. The configured key may return metadata while institutional full-text API entitlement is absent; this does not prevent the browser workflow from succeeding through institutional authentication.

The user, not the skill, enters passwords, 2FA codes, and CAPTCHA responses in visible CloakBrowser. Keep the browser page available while waiting.

## 9. Failure and Degradation Rules

- Undermind unavailable before any results: report the connection failure; do not silently substitute Scholar as the primary source.
- Scholar challenge repeated or two consecutive timeouts: stop Scholar, record the reason, and continue with Undermind-only results.
- Scholar empty: record an empty list and continue.
- No DOI and no lawful OA PDF: `download_status: "missing"`, `status_reason: "metadata_resolution_failed"`.
- DOI but no InstSci publisher profile and no verified OA PDF: `download_status: "missing"`, `status_reason: "profile_missing"`.
- Login, 2FA, or CAPTCHA pending: `download_status: "pending"` with a precise next action.
- PDF exists but identity verification is insufficient: `download_status: "unverified"`.
- Below-threshold, over-cap, or deprioritized duplicate: `download_status: "not_selected"` with the precise reason.
- Never translate `profile_missing` into `unsupported`. `unsupported` requires browser evidence described in the publisher reference.

## 10. Final Reconciliation

After downloads, update the canonical record statuses and regenerate or reconcile:

- `reports/search_manifest.json`
- `reports/search_manifest.csv`
- `reports/final_report.md`

Every format must list title, DOI, sources, relevance reason, duplicate relationship, publisher, status, PDF path, and next action. Derive `success`, `unverified`, and `missing` counts from the same in-scope records. Check that the three values agree across all formats before reporting completion.

Do not claim a batch is complete while any record remains `pending`; report the pending user action or resumable next command instead.
