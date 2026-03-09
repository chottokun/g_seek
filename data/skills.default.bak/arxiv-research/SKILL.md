---
name: Academic Research (Arxiv)
description: Specialized patterns for searching and extracting information from Arxiv and other academic repositories. Use this for highly technical, scientific, or cutting-edge AI topics.
---

## Updated Instructions
- Improved Skill Definition – Consolidated Guidance (1‑5 bullet points)
- Robust arXiv Retrieval & Rate‑Limiting
- Use the official arXiv API (`http://export.arxiv.org/api/query`) with a **`submittedDate` ≥ 2024‑01‑01** filter; enforce **≥ 1 s between requests** and implement **exponential back‑off with jitter** (max 5 retries).
- Accept **DOI**, **arXiv ID**, or plain keyword searches (e.g., “paper”, “preprint”, “arXiv”) and always prepend `site:arxiv.org` when falling back to web search.
- Store raw API responses and the final normalized metadata in **JSONL** (one paper per line) for downstream pipelines.
- Metadata Completion & Domain Guardrails
- When any field (authors, abstract, version, citation count) is missing from arXiv, query **OpenAlex** and **Crossref** (via their public APIs) to fill gaps.
- Rigorously filter results to the **`arxiv.org` domain**; discard any entries originating from bioRxiv, medRxiv, or other pre‑print servers even if they appear in search results.
- Deep Content Extraction & Structured Summarization
- Parse PDFs with a **hybrid pipeline**: first `PyMuPDF` for text, then `pdfminer.six` for layout‑preserving extraction; fall back to **Tesseract OCR** for scanned pages.
- Extract **Abstract, Methodology, Experiments, Results, Conclusion, Limitations, Future Work** sections. Summarize each section into concise bullet points and explicitly list **implementation details (algorithms, hyper‑parameters, hardware used)**.
- Detect and record any **code repository links** (GitHub, GitLab, Zenodo, etc.) and **appendix snippets**; if a repository is absent, note “No public code found”.
- Impact, Reproducibility & Risk Assessment
- Pull **citation counts** (Semantic Scholar, Google Scholar) and **version numbers** (v1, v2, …) to rank papers by impact and recency.
- From Limitations/Future Work, extract constraints on **data scale, compute resources, hardware dependencies, and regulatory considerations**; surface these as “⚠️ Potential risks / applicability notes”.
- For each paper, map the proposed evaluation to the **What/How taxonomy** (What: behavior, capability, safety, reliability; How: interaction modality, benchmark datasets, metrics, tools). Flag missing elements (e.g., no safety assessment) for the user.
- Production‑Ready Pipeline & Automation
- Containerize the entire workflow (search → API fetch → metadata enrichment → PDF download → OCR → extraction → summarization) in a **Docker image**; expose a single entry‑point script that can be scheduled (cron, CI/CD) to run nightly.
- Log all API responses, retry attempts, and rate‑limit violations; store logs alongside the JSONL output for auditability.
- Pitfalls to avoid:
- Over‑reliance on a single source*: always cross‑validate with OpenAlex/Crossref.
- Missing rate‑limit handling*: API bans silently stop the pipeline.
- Ignoring versioning*: newer versions may contain critical corrections.
- Assuming OCR‑free PDFs*: many arXiv submissions are scanned images; failing to OCR will lose entire sections.
- These five consolidated points capture the proven patterns from earlier sessions, introduce the newest best‑practice methods, and highlight common failure modes to ensure a reliable, high‑quality arXiv literature‑mining skill.