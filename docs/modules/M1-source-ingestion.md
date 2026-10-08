# M1 — Source Ingestion

## Purpose
Turn uploaded artefacts into normalised, located, embedded text chunks that extraction can cite precisely.

## Responsibilities
- Accept uploads (UI, API, later: SharePoint/Teams connectors).
- Store originals immutably in object storage (`sources/{process_id}/{source_id}/original.<ext>`).
- Detect kind and parse to a normalised **document model**.
- Chunk with **locators** so every excerpt can be traced back (page, line range, timestamp, message, cell).
- Optional PII redaction pass (configurable per process).
- Embed chunks (pgvector) for retrieval by M2, M5 and M6.
- Emit `source.parsed`.

## Not responsible for
Interpreting content (M2), deciding what's a process step.

## Supported inputs

| Kind | Extensions | Parser | Locator kind | Phase |
|---|---|---|---|---|
| `sop`, `document` | .docx .pdf .md .txt | python-docx / pypdf / markdown | `page` + `paragraph` | P8 |
| `transcript` | .vtt .srt .txt (Teams export) | webvtt-py / custom | `timestamp` (+ speaker) | P8 |
| `email` | .eml .msg | mail-parser / extract-msg | `message` (index in thread) | P8 |
| `spreadsheet` | .xlsx .csv | openpyxl | `cell` (`Sheet!A1:D20`) | P10 |
| `recording` | .mp4 .webm | ASR + keyframe OCR → transcript-like doc | `timestamp` | P10 |

Kind is guessed from extension + content sniffing; the BA can override at upload. Authority weight defaults from
kind (IR spec §8.1) and is editable.

## Normalised document model

```python
class Block(BaseModel):
    block_id: str              # stable within source
    text: str
    locator: Locator           # kind + value, e.g. ("timestamp", "00:14:32-00:15:10")
    speaker: str | None        # transcripts, emails (from)
    heading_path: list[str]    # e.g. ["4 Risk assessment", "4.2 High risk"]

class ParsedSource(BaseModel):
    source_id: str
    kind: SourceKind
    title: str
    blocks: list[Block]
    metadata: dict             # author, date, participants, subject
```

## Chunking
- Chunk = consecutive blocks up to ~1,200 tokens, never splitting a block, overlap of 1 block.
- Each chunk stores the list of block locators it covers, so an excerpt can map to the most specific locator.
- Transcripts: additionally strip filler ("um", "you know") into a `clean_text` field used for extraction while
  keeping raw text for excerpts.

## Email specifics
- Thread de-duplication: strip quoted replies; keep each message once with `message` locator `#n`.
- Signatures and disclaimers removed via heuristics.

## PII redaction (optional)
- Detect names of private individuals, emails, phone numbers, account-like numbers using a configurable
  recogniser (Presidio). Replace in `clean_text` with typed placeholders (`<PERSON_1>`), keep mapping in an
  encrypted table accessible only to process admins. Excerpts shown in UI respect the user's permission.

## API
- `POST /processes/{pid}/sources` (multipart; fields: `kind?`, `title?`, `authority_weight?`) → `202 {source_id}`
- `GET /processes/{pid}/sources` / `GET /sources/{sid}` / `GET /sources/{sid}/blocks?locator=`
- `DELETE /sources/{sid}` → soft delete; triggers re-reconciliation (M2) which marks provenance refs from this
  source as removed and recomputes confidence.

## Errors
- Unsupported / corrupt file → source `status=failed` with reason; nothing emitted.
- Partial parse (e.g. scanned PDF pages) → `status=parsed_with_warnings`; OCR fallback for image-only pages.

## Acceptance tests
- **AC-M1-1** Given `samples/sources/sop_client_onboarding.md`, when ingested, then blocks carry `heading_path`
  and the block containing "Engagement Partner" has a locator `paragraph` under heading `4.2`.
- **AC-M1-2** Given `samples/sources/workshop_transcript.vtt`, when ingested, then each block has a timestamp
  locator and speaker, and the MLRO statement at `00:14:32` is retrievable by locator.
- **AC-M1-3** Given `samples/sources/email_docs_chase.eml`, when ingested, then quoted replies are not duplicated
  and messages are indexed `#1..#3`.
- **AC-M1-4** Re-uploading an identical file (same SHA-256) returns the existing `source_id` and emits nothing.
