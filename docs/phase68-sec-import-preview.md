# Phase 6.8: SEC financial import approval preview

Status: **explicitly approved and applied to local development on 23 October
2026; post-import installed acceptance passes after the authorized ordering repair**.
Revision: `0005_financial_import_batches`. Batch:
`sec-f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d`.
The exact planned row additions committed and original-row preservation passed.
The initial O snapshot check stopped on JSONB-induced warning ordering. Stable
normalization traversal now reproduces all eight original hashes without a row
or audit change. Read-only receipt verification and the actual installed MSFT
FastAPI route pass; no second import or migration was executed. See
[the final report](phase68-real-financial-data-and-valuation.md#181-warning-order-root-cause-and-correction).
The verified 35,744,826-byte pre-import backup and full
isolated restore are retained under ignored access-restricted `.phase68.local/`.
The following preview and approval boundaries preserve the original reviewed
22 October checkpoint; they do not authorize additional writes.

Branch: `feature/phase-6-8-financial-data-and-valuation`.
Starting commit: `413a5580ce91577dbce0616fccda5955e9e9804a`.
Preview calculation clock: **22 October 2026, 06:51:30 UTC**.

Read-only revalidation completed on **22 October 2026 at 15:22 UTC**. Rebuilding
the full preview from all eight original SEC sources, the archived MSFT package
and the current development PostgreSQL state produced an **exact match**,
including the digest and database fingerprints. `migration_required` remains
true and `apply_blocked` is false; neither flag authorizes a write. The frozen
06:51:30 audit clock and every original source/proof clock remain unchanged.
A changed baseline still requires a new preview and explicit review.

Final before/after read-only audits matched every row count and full-row hash
across **all twelve existing application tables**, including cache and registry
history. The development revision remains `0004_financial_issuer_ownership` and
the audit table is absent. No application writes, provider requests or broker
connections occurred. All final checks passed: 2,082 backend tests (including
four native PostgreSQL tests), 95 unit tests, 198 desktop/mobile browser tests,
lint, build and offline dependency checks. The full results and retained warnings
are in Section 18 of the [Phase 6.8 report](phase68-real-financial-data-and-valuation.md).

The complete read-only manifest is in ignored
`.phase68.local/sec-import-preview.json`. Its exact digest is:

```text
f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d6282314b6828ef36
```

The digest binds original source hashes, original acquisition clocks, exact
registered issuer/instrument/listing targets, proposed normalized snapshot
hashes, normalization version, SEC cache-age policy and a full-row database
baseline. Any source, ownership, interpretation or baseline change requires a
new reviewed preview. The durable audit-table migration is an explicit
prerequisite; it does not itself authorize the import.

## Proposed database writes

| Table / operation | Before | Planned addition | Expected after |
| --- | ---: | ---: | ---: |
| Company owners | 5 | 4 | 9 |
| Financial facts | 165,486 | 107,569 | 273,055 |
| Financial snapshots | 9 | 8 | 17 |
| Market snapshots | 14 | 0 | 14 |
| Cache entries | 64 | 8 immutable source-SHA entries | 72 |
| Import audit batches | Table not installed | Add empty table, then 1 batch | 1 |

The four new reporting owners are **AMZN, Alphabet, O and PGR**. Alphabet has one
issuer-owned consolidated statement set; GOOG and GOOGL remain separate selected
securities and do not receive duplicate issuer owners. Existing company IDs,
metadata, tickers, facts and snapshots are not reassigned or updated. All 64 old
cache rows remain unchanged; the new source records use
`sec:import:facts:{CIK}:{source_sha256}` keys.

There are **247,920 unique incoming observations**, including **140,351 already
persisted observations**. The three generic JPM review flags compare offering
prices across different `424B2` filings; they are not confirmed annual financial
restatements. Every original observation remains preserved. There are zero
same-accession conflicts and no approved fact updates/deletes. This operation
grants no model eligibility or currentness.

The installed registry has 19 October source proofs, including a legacy missing
issuer-reference retrieval clock. Financial import alone would therefore not
reproduce the 21 October dated test. The preview additionally includes **one
MSFT-only archived reference attachment**, stored in the new batch's audit
metadata. It does not update the registry or any existing proof date. The
attachment is validated from exactly two previously retained 21 October files:

| Archived source | Bytes | Original SHA-256 |
| --- | ---: | --- |
| Nasdaq `nasdaqlisted.txt` | 348,727 | `3a66dfb733cb67c2c9be8a83890be1121cd6fd49847f76c1c22426902ca2ed39` |
| SEC issuer-symbol directory | 523,851 | `6c29e2e3db973d4479875164603c2434f81ad22e14c9f1694999aca9cca246cb` |

Their original retrievals are **21 October 2026 07:49:40.169888 UTC** and
**07:49:43.854147 UTC**. Their independent one-day proofs expire at
**22 October 2026 00:00 UTC**; only an explicitly selected historical clock within
that original interval is eligible. The package retains exact selected source
rows, row/full-file hashes, original clocks and stable MSFT issuer/instrument/
listing IDs. It grants no present-day verification. The original acquisition
receipt is rechecked as source provenance, not reused as import authorization.

| Issuer | Existing duplicates | New facts |
| --- | ---: | ---: |
| MSFT | 32,671 | 0 |
| NVDA | 27,281 | 0 |
| ORCL | 26,350 | 0 |
| JPM | 54,049 | 51 |
| AMZN | 0 | 29,761 |
| Alphabet | 0 | 20,907 |
| O | 0 | 21,723 |
| PGR | 0 | 35,127 |

## JPM cross-filing review flags

All three flags concern taxonomy/concept **`ffd:NrrtvMaxAggtOfferingPric`**,
unit **USD**, an instant ending **14 October 2026** with no start date, and form
**`424B2`**. The generic audit compares observations sharing this concept, unit
and period across filing accessions. Those fields alone do not establish that
one offering filing restates or supersedes another. These are offering-price
cross-filing comparisons, not confirmed annual statement restatements or
approved corrections to valuation inputs.

The exact incoming observations, all filed **15 October 2026**, are:

| Incoming accession | Reported value (USD) |
| --- | ---: |
| `0001213900-26-109718` | 546,000 |
| `0001213900-26-109762` | 1,000,000 |
| `0001213900-26-109778` | 3,205,000 |

The existing comparison set contains these twelve observations, all filed
**14 October 2026**, with the same concept, unit, instant and form:

| Existing accession | Original reported value (USD) |
| --- | ---: |
| `0001213900-26-109344` | 6,961,600 |
| `0001213900-26-109450` | 6,223,400 |
| `0001918704-26-031364` | 1,224,000 |
| `0001918704-26-031366` | 1,124,000 |
| `0001918704-26-031368` | 1,813,000 |
| `0001918704-26-031371` | 906,000 |
| `0001918704-26-031372` | 1,576,000 |
| `0001918704-26-031374` | 700,000 |
| `0001918704-26-031375` | 1,468,000 |
| `0001918704-26-031383` | 565,000 |
| `0001918704-26-031386` | 1,393,000 |
| `0001918704-26-031387` | 287,000 |

Each incoming value differs from this existing set. There is **no unique
original-to-replacement pairing**. The proposed import appends the three original
incoming filing observations and leaves every prior accession/value unchanged;
it does not resolve the flags by overwriting a value or inventing restatement
precedence. Existing reviewed normalization and conflict quarantine still apply.

## Exact retained sources

These are the eight previously approved Phase 6.7 companyfacts downloads, not
new acquisitions. Source URL pattern:
`https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json`.

| Issuer / CIK | Original bytes | Original SHA-256 |
| --- | ---: | --- |
| MSFT / 0000789019 | 4,881,196 | `f8aae2965b20ad0df44bdf7ccbedf797d275b6b8dc030154a7a311361bb7246f` |
| NVDA / 0001045810 | 4,092,966 | `19ef503a5770f5660964b3c3aea6937579d9b359da344afe6a9adf59c63d26ff` |
| ORCL / 0001341439 | 3,962,105 | `65523545f040abaea1dfcf321da2a5aec85e7f34387244b0ffcb26e4c8707f7d` |
| JPM / 0000019617 | 7,988,348 | `284d6f3ce6364f94216dddb45172203a825475f0bd75b633a2036b903181e902` |
| AMZN / 0001018724 | 4,478,611 | `7549fb68446eee40e1f50a166fa06b2d2ee6349e07c8553a4828757e032d3cd4` |
| Alphabet / 0001652044 | 3,164,517 | `a017f26ee88cb4a639d1c1ddb06d53b4afe22f0ac89cabec7cd67c88919fe1c5` |
| O / 0000726728 | 3,235,550 | `676caac36e22f0d1087ec209f80728d2ab38536a1851d1f226daf27aaef44acb` |
| PGR / 0000080661 | 5,157,763 | `36a3229d38dd5d6c67968c481a413230070c351002f06350995a9cb113cf4d37` |

Original retrievals span **20 October 2026, 12:01:53.080073–12:02:07.064937 UTC**.
Their original financial/filing dates and six-hour source-cache bounds remain
dated. Importing now does not make them fresh. The new AAPL acquisition is not
part of this eight-issuer import proposal.

## Transaction and preservation

The proposed additive migration `0005_financial_import_batches`, following
`0004_financial_issuer_ownership`, creates only a durable batch audit table.
The reviewed migration file is
`backend/alembic/versions/0005_financial_import_batches.py`, with SHA-256:

```text
a245f61d58f6fa043a959aad5c66e5c56f17a47fe1912dbc9345fb3eb2ce6106
```

Its PostgreSQL table-creation SQL is:

```sql
CREATE TABLE financial_import_batches (
    id VARCHAR(64) NOT NULL,
    preview_digest VARCHAR(64) NOT NULL,
    source_inventory JSONB NOT NULL,
    summary JSONB NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (preview_digest)
);
```

Alembic also records the completed schema revision in its existing version
table:

```sql
UPDATE alembic_version
SET version_num = '0005_financial_import_batches'
WHERE alembic_version.version_num = '0004_financial_issuer_ownership';
```

Existing financial tables/data are not rebuilt or reset. No database or volume
is created. These statements describe the proposed migration; they have not
been executed against the application database.

User analyses and assumptions are not import targets. The migration adds no
analysis column or rewrite; apply only appends the reviewed issuer/fact/snapshot/
source-cache/audit records. Current market, identity and financial eligibility
checks remain independent of source installation.

Downgrade to revision `0004_financial_issuer_ownership` is allowed only while the
new audit table is empty; it drops that empty table and records the preceding
revision. If any applied batch is present, downgrade deliberately raises an
error rather than discard its durable provenance. It does not delete imported
facts or provide an automatic undo of a successful import.

Apply reopens and verifies every original file, checks the exact preview and
confirmation, locks relevant tables under a serializable PostgreSQL transaction,
revalidates ownership and hashes again before each write, and checks the exact
expected changes. Every original financial row and cache record is verified
unchanged. Any failure rolls back the complete import transaction. A migration
committed separately before the import remains installed if that later import
rolls back; the import does not automatically downgrade the schema. PostgreSQL
sequence allocations can also leave ID gaps after rollback, while financial
rows and values remain unchanged. Reapplying the same intact source/preview
returns the original batch without duplicate writes.

After a successful import there is no automatic destructive reversal. Any later
restoration or removal would require its own reviewed plan and authorization;
this approval does not authorize deleting financial history or audit records.

Imported reads independently bind the batch source inventory, immutable raw
source, original clocks, normalization version and recomputed normalized hash to
the selected snapshot. No newer-source provenance can be attached to an older
unrelated snapshot. Imported source availability remains separate from financial
scope, selected share class, listing freshness and model eligibility.

No private credentials, API keys, SEC contact information, broker data or new
provider acquisition is involved. Raw originals, detailed manifests and generated
reports remain ignored local artifacts. No commit or push is included.

## Approval boundary

Section 5 of the Phase 6.8 brief requires explicit user approval **before** the
application migration/import. The permission requested is limited to adding the
audit table and applying the exact digest and write plan above to the existing
configured Fairworth application database. No IBKR access, external request,
database reset, formula change, deployment or public data redistribution is
included.

After approval, the CLI requires the literal confirmation
`APPLY f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d6282314b6828ef36`.
That operator receipt is not a substitute for the user approval. The importer
must refuse if the database changed while approval was pending.
