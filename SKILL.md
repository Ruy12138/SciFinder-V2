---
name: scifinder
description: Use for research-topic literature discovery and download workflows that combine Undermind, low-frequency visible Google Scholar searches, metadata deduplication, publisher-specific DOI batches, InstSci publisher PDF retrieval, closed-access verification, CloakBrowser evidence, CARSI, Shibboleth, OpenAthens, WebVPN, or InstSci CLI workflows.
---

# SciFinder

## Core Rule

Use this skill as the entry point for either:

- a research topic that should produce a deduplicated, relevance-screened set of papers and downloaded PDFs; or
- a known DOI list/publisher PDF task.

Do not change the InstSci Python package or its public CLI/MCP interfaces as part of a literature run. For repository development, work from the repository root and read `AGENTS.md` first.

## Route Selection

When the user supplies a research topic and asks to find, collect, or download related literature, read `references/literature-discovery.md` and run this order:

1. Undermind deep search.
2. Visible, low-frequency Google Scholar supplementation.
3. Deterministic normalization, deduplication, relevance filtering, and publisher batching with `scripts/merge_literature_results.py`.
4. Verified Undermind Open Access PDF retrieval.
5. One InstSci browser batch per publisher for the remaining DOI records.
6. Reconcile JSON, CSV, and Markdown reports from the same manifest.

Google Scholar is supplementary. Scholar failure must not block screening or downloading the Undermind results.

When the user already provides DOI files or asks about a publisher route, skip discovery and follow the publisher workflow in `references/publisher-pdf-workflow.md`.

## Discovery Defaults

- Read Undermind orientation before using it.
- Automatically select the sole writable Undermind workspace. Ask only when more than one writable workspace exists.
- Send the research question to one deep search as a self-contained natural-language goal, not a synthetic Boolean query.
- Unless the user explicitly says this is a continuation of the same search, create a new deep search.
- Inspect the first 30 ranked results and retain up to 20 directly relevant results from Undermind.
- Judge relevance from the research object/population, central variable or intervention, outcome, method, and whether the paper addresses the topic centrally. Save a short reason.
- Build 2–4 compact Scholar queries only after reviewing the high-relevance Undermind results.
- Use a normal visible Chrome session serially. Do not use CloakBrowser, headless mode, proxy rotation, automated CAPTCHA solving, or anti-detection techniques for Scholar.
- Read page 1 by default. Read page 2 only when a query adds fewer than five new candidates and there is no warning or challenge.
- Preserve a CAPTCHA page and pause for the user. Stop the Scholar branch after a second risk event in the same task or after two consecutive page timeouts.

## Run Layout

Create one run directory:

```text
~/.instsci/runs/<topic-slug>-<timestamp>/
├── discovery/
│   ├── undermind.json
│   ├── google_scholar.json
│   └── search_queries.json
├── doi_batches/<publisher>.txt
├── downloads/
└── reports/
    ├── search_manifest.json
    ├── search_manifest.csv
    └── final_report.md
```

Never overwrite a previous run. Keep discovery records in the unified input shape documented in `references/literature-discovery.md`.

## Merge and Batch

Run:

```bash
python3 scripts/merge_literature_results.py \
  --undermind "$RUN_DIR/discovery/undermind.json" \
  --scholar "$RUN_DIR/discovery/google_scholar.json" \
  --output-dir "$RUN_DIR" \
  --max-downloads 30
```

The script is the source of truth for DOI normalization, conservative deduplication, possible-duplicate flags, the 30-paper cap, publisher grouping, and initial reports. It must not access Scholar or download PDFs.

Only high-relevance records enter the default download scope. A DOI batch must contain one InstSci publisher profile only. Never send a mixed-publisher file to `instsci papers`.

## Download Order

1. Prefer Open Access PDF links already returned by Undermind.
2. Before marking success, verify the `%PDF` signature, plausible size, readable page count, and DOI or title match. An HTML login/challenge page saved with a `.pdf` suffix is not a PDF.
3. Skip PDFs already verified as `success`.
4. Route each remaining DOI through its generated `doi_batches/<publisher>.txt` file with `--concurrency 1` and the persistent browser/session broker.
5. If a high-relevance record has neither a DOI nor a lawful Open Access PDF, mark it `metadata_resolution_failed`; do not guess a download URL.
6. If a closed-access DOI has no InstSci publisher profile, mark it `profile_missing`, not `unsupported`.

## Elsevier Browser-First Rule

Elsevier downloads must use the visible institution-authenticated browser route by default:

```bash
instsci papers <doi-file> --publisher elsevier --institution "Beijing Normal University" --concurrency 1
```

For this default route, do not call MCP `fetch_paper`, `instsci fetch`, `instsci elsevier-setup`, or Elsevier XML/object full-text APIs. Preserve any configured API key, but do not use or validate it for downloads. Only enable an API path when the user explicitly asks for it in a later request.

The user completes institution credentials, passwords, 2FA, and CAPTCHA in the visible CloakBrowser. Never fill or record them.

## Publisher Evidence

Final closed-access PDF verdicts require the visible built-in CloakBrowser workflow. HTTP requests, DOI resolution, route construction, logs, DOM state, and cookies are preflight/supporting evidence only.

Before publisher work, read `instsci/data/institutional_identity_policy.json` or run `instsci identity-policy` when available. Resolve the institution in this order: explicit `--institution`, configured CARSI IdP name, configured school, then ask. Do not default to another institution.

Prefer publisher broker, Shibboleth, OpenAthens, CARSI, or configured WAYFless links before WebVPN. Use WebVPN only when configured and browser-verified for that publisher.

## Reporting

The final manifest must list, for every retained record: title, DOI, sources, relevance reason, duplicate relationship, publisher, download status, PDF path, and next action.

Use these download meanings:

- `success`: a PDF was downloaded and verified.
- `unverified`: a PDF exists but DOI/title/content verification is insufficient.
- `missing`: no valid PDF was captured, including `metadata_resolution_failed` and `profile_missing` reasons.
- `pending`: the record is still queued or awaiting browser/user action.

Derive JSON, CSV, and Markdown counts from the same record set so `success`, `unverified`, and `missing` are identical in all three outputs.

For direct publisher work, also report `publisher`, `doi`, `route_attempted`, `institution`, `result`, `evidence`, and `next_action`. Use `unsupported` only when visible browser evidence actually rules out a supported route.

## Detailed References

- Read `references/literature-discovery.md` for Undermind, Scholar, query cleaning, normalization, deduplication, batching, degradation, and report-reconciliation rules.
- Read `references/publisher-pdf-workflow.md` for publisher-specific browser procedures, recent gotchas, screenshots, verification commands, and UI fallbacks.

## Safety

- Keep publisher CloakBrowser visible for SSO, CAPTCHA, WAF, Cloudflare, and final verification.
- After clicking PDF, institutional access, OpenAthens/Shibboleth/CARSI, cookie prompts, or verification prompts, inspect a screenshot before concluding success or failure.
- Visible UI fallback may click public controls such as `Access through your organization`, institution search results, or PDF viewer `Download`, but never fill passwords, OTPs, or account credentials.
- Scholar automation must remain low-frequency and human-supervised; never attempt bulk extraction or challenge evasion.
- Never store API keys, tokens, credentials, cookies, or entitlement details in discovery files, reports, docs, logs, skills, or commits.
- Do not manually call Xiaozhi notification scripts or expose Xiaozhi MCP endpoints.
