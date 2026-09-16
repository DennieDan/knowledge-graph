# How keyword search gets BM25 quality in this Postgres

- **Date:** 2026-09-16
- **Ticket:** How keyword search gets BM25 quality in this Postgres

This note compares in-Postgres keyword ranking options for a stack that already runs PostgreSQL 18 with pgvector only, and that later wants managed hosting in or near Singapore (`ap-southeast-1` / `asia-southeast1`). Claims are taken from first-party docs, GitHub READMEs, cloud extension lists, and Docker Hub image pages. If a provider’s published allowlist does not mention an extension, that extension is **not listed** — treat that as **not shippable today**, not as a permanent impossibility.

Local image today, confirmed in `compose.yaml`: `pgvector/pgvector:0.8.6-pg18` (PostgreSQL 18 + pgvector). No BM25 extension is installed.

## Recommendation

**Do not treat native `tsvector` / `ts_rank` as BM25.** PostgreSQL’s own ranking docs describe `ts_rank` (matching-lexeme frequency) and `ts_rank_cd` (cover density). Those functions **do not use global corpus statistics** (IDF / average document length). That is not BM25.

**For this product (names, codes, part numbers + vector merge, English / Chinese / Malay):**

1. **Local compose.** Replace `pgvector/pgvector:0.8.6-pg18` with an image that ships **pgvector and a real BM25 extension in the same container**. The two first-party images that do that on PostgreSQL 18 are:
   - `paradedb/paradedb:latest` (ParadeDB documents that `latest` is Postgres 18; Docker Hub also tags `pg18` / `0.25.9-pg18`). Pre-installed: `pg_search` + `pgvector`. CJK tokenizers: Jieba, Lindera, Chinese-compatible (per-character).
   - `tensorchord/vchord-suite:pg18-latest`. Includes `vchord_bm25`, `pg_tokenizer`, `vchord`, and `vector` (pgvector). CJK: jieba pre-tokenizer via `pg_tokenizer`.

2. **Managed Singapore.** `pg_search` and `vchord_bm25` are **not listed** on AWS RDS / Aurora, Google Cloud SQL, Azure Database for PostgreSQL, Aiven, or DigitalOcean Managed Postgres. Neon listed `pg_search` and then **deprecated it for new projects** (2026-03-19). ParadeDB Cloud is documented as “coming soon”. That is the main trap: a local ParadeDB or VectorChord image will not `CREATE EXTENSION` on RDS Singapore.

3. **Neon Singapore (`aws-ap-southeast-1`)** documents a different BM25 than ParadeDB: `lakebase_text` / `lakebase_bm25` on ordinary `tsvector` columns (Lakebase Search, changelog 26 Jun 2026). If Neon is the host, store `tsvector` locally and do **not** bind application SQL to ParadeDB’s `@@@` / `pdb.score`. CJK still uses Postgres parsers (no Jieba). Confirm `CREATE EXTENSION lakebase_text` on a fresh Singapore project before locking hosting.

4. **What *else* is listed as BM25 + vectors near Singapore today** is Timescale’s `pg_textsearch` (BM25 index, `USING bm25`, operator `<@>`), plus pgvector:
   - **Crunchy Bridge:** catalog lists `pg_textsearch` (PG 17 and 18) and `vector`. Regions include AWS `ap-southeast-1` (Singapore) and GCP `asia-southeast1` (Singapore).
   - **Tiger Cloud:** `pg_textsearch` v1.0.0 is GA; changelog also adds Azure `southeastasia` (Singapore) and documents AWS `ap-southeast-1`. Tiger docs also cover `pgvector`.
   - **AlloyDB:** `pg_textsearch` is listed (PG 17+); BM25 index docs are **Preview**. `vector` is listed. Region `asia-southeast1` is Singapore.
   - CJK on `pg_textsearch` uses a PostgreSQL `text_config`. The upstream README says to pair Chinese with **zhparser**. zhparser is **not listed** on Crunchy Bridge, AlloyDB, or the Cloud SQL / RDS allowlists fetched for this note. Treat CJK word segmentation on those managed BM25 offerings as **not shippable today** unless the provider later allowlists a CJK parser.

5. **If the team wants ParadeDB’s API and CJK tokenizers in production:** keep OLTP on a Singapore managed Postgres that already has pgvector (RDS/Aurora `ap-southeast-1`, Neon `aws-ap-southeast-1`, AlloyDB `asia-southeast1`, Cloud SQL `asia-southeast1`), and run ParadeDB as a **logical replica** (ParadeDB requires Postgres 17+ on the subscriber). ParadeDB BYOC is documented on AWS and GCP (so Singapore regions exist at the cloud-provider layer); access is via sales. ParadeDB Cloud is not GA.

6. **If the team wants VectorChord-bm25 in production:** the first-party managed list that actually names `vchord_bm25` + `pg_tokenizer` + `vector` is **pgEdge Cloud**. pgEdge deploys on AWS, Azure, or GCP into regions the customer’s cloud account can use; it does not publish a Singapore-only region table on the extensions page. VectorChord Cloud is AWS-only and its cluster docs describe **vector** extensions (`pgvecto.rs` / VectorChord), not `vchord_bm25`.

7. **External OpenSearch / Elasticsearch** is the honest fallback if the team must stay on RDS/Aurora allowlisted extensions only and will not run a ParadeDB replica or move to Crunchy/Tiger/AlloyDB/`pg_textsearch`. OpenSearch’s default similarity is BM25; Amazon OpenSearch Service documents Asia Pacific (Singapore) usage. That is a second system to sync.

**Compose implication:** today’s `pgvector/pgvector:0.8.6-pg18` cannot satisfy the BM25 product requirement. Pick ParadeDB or VectorChord-suite for local CJK+BM25+pgvector, *or* build a custom PG18 image with `pg_textsearch` + pgvector if the managed target is Crunchy / Tiger / AlloyDB (no first-party all-in-one Docker image for that pair was found on Docker Hub for this research).

## Comparison table

| Option | BM25? | Local Docker | PG18 | pgvector in same image / DB | Singapore managed (listed today) | CJK tokenizer | License | Migration cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Native FTS (`tsvector` / `tsquery` / `ts_rank` / GIN) | **No.** Frequency + optional cover-density; no global IDF | Yes: already in `pgvector/pgvector:0.8.6-pg18` | Yes | Yes (`vector` is separate; FTS is core) | Yes everywhere (core Postgres). RDS/Aurora also list `pg_trgm` / `pg_bigm` | Default parser splits on word boundaries; no Chinese/Malay stemmer. `simple` = lowercase + stopwords; `english` = Snowball `english_stem`. No `malay` dictionary in `\dFd` list | PostgreSQL | Lowest: already available. Ranking will not be BM25 |
| ParadeDB `pg_search` (formerly `pg_bm25`) | **Yes.** `pdb.score()` is BM25 | **Yes.** `paradedb/paradedb:latest` / `:pg18` / `:0.25.9-pg18` | Yes (`latest` = PG18) | **Yes.** Image pre-installs `pg_search` + `pgvector`. As of 0.25.0, `CREATE EXTENSION pg_search CASCADE` requires `vector` | **Trap.** Not listed on RDS, Aurora, Cloud SQL, AlloyDB, Azure, Aiven, DigitalOcean, Crunchy. Neon: listed but **deprecated for new projects**. ParadeDB Cloud: coming soon. Replica/BYOC possible | **Yes.** Jieba, Lindera (zh/ja/ko), Chinese-compatible (per CJK char). Malay: whitespace/unicode tokenizers; no dedicated Malay stemmer documented | AGPLv3 Community; Enterprise via sales | High if local ParadeDB then host on RDS-only: must add a ParadeDB subscriber or wait for Cloud |
| VectorChord-bm25 (`vchord_bm25`) | **Yes.** `<&>` is negative BM25 | **Yes.** `tensorchord/vchord-suite:pg18-latest` (also `tensorchord/vchord_bm25-postgres:pg18-v0.3.0`) | Yes | **Yes** in `vchord-suite` (`vector` + `vchord` + `vchord_bm25` + `pg_tokenizer`) | **Trap vs RDS.** Not listed on RDS/Aurora/Cloud SQL/AlloyDB/Azure/Neon/Aiven/DO/Crunchy. **Listed on pgEdge Cloud** (`vchord_bm25` 0.2.2 + `pg_tokenizer` + `vector`). VectorChord Cloud docs do not list `vchord_bm25` as the cluster extension | **Yes, via `pg_tokenizer`.** README has a jieba Chinese example and a Lindera Japanese example. Malay not specifically documented | Dual: AGPLv3 or Elastic License v2 | Medium–high: new types (`bm25vector`) and operators; pgEdge or self-host for managed |
| External index (OpenSearch / Elasticsearch / Typesense / Meilisearch) | OpenSearch & Elasticsearch: **yes, default BM25**. Typesense: proprietary `_text_match` (not documented as BM25). Meilisearch: ranking-rule bucket sort (not documented as BM25) | Yes (separate containers) | N/A (not in Postgres) | Hybrid in app: query Postgres pgvector + external BM25, merge ranks | Amazon OpenSearch Service documents Asia Pacific (Singapore). DigitalOcean OpenSearch is listed for `SGP1`. Elasticsearch Cloud region list not fetched here | Analyzer-dependent (CJK analyzers exist in Lucene/OpenSearch; confirm per product) | Product licenses vary | Highest ops: second system, sync, dual writes or CDC |

**Related managed BM25 (not one of the four options, but it is what Singapore managed Postgres actually lists):** `pg_textsearch` (Timescale / Tiger Data). BM25 yes; local Docker: **no first-party all-in-one image found** (binaries for PG17/18). PG18 yes. Coexists with pgvector (separate extension). Singapore: Crunchy Bridge, Tiger Cloud, AlloyDB (Preview). CJK: needs zhparser (not listed on those catalogs). License: PostgreSQL License.

---

## 1. Postgres native full-text search

**BM25: no.**

PostgreSQL 18 documents two ranking functions ([Controlling Text Search §12.3.3](https://www.postgresql.org/docs/18/textsearch-controls.html)):

- `ts_rank`: “Ranks vectors based on the **frequency of their matching lexemes**.”
- `ts_rank_cd`: cover density ranking, citing Clarke, Cormack, and Tudhope (1999). Proximity of matching lexemes is included.

The same page states: “the ranking functions **do not use any global information**,” so they cannot do corpus-wide IDF or average-length normalization. Length handling is a local bitmask (`0` ignore length, `1` log length, `2` divide by length, `8` unique words, `32` `rank/(rank+1)`, etc.). That is the opposite of BM25’s IDF + `k1`/`b` against collection statistics.

Function signatures and examples: [Text Search Functions and Operators](https://www.postgresql.org/docs/18/functions-textsearch.html).

Matching uses `tsvector` / `tsquery` and `@@` ([Introduction](https://www.postgresql.org/docs/18/textsearch-intro.html)). Indexes: GIN is the preferred inverted index for `tsvector`; GiST is the other option ([Preferred Index Types](https://www.postgresql.org/docs/18/textsearch-indexes.html)).

### Tokenization: English vs Chinese / Malay

There is **one built-in parser**, `pg_catalog.default` ([Parsers](https://www.postgresql.org/docs/18/textsearch-parsers.html)). It “identifies plausible **word boundaries**.” A “letter” is defined by `lc_ctype`. Token types include `asciiword`, `word` (all letters), `numword` (letters and digits — useful for part numbers like `beta1`), hyphenated forms, and `uint` / `version`. Consecutive CJK letters with **no whitespace** are typically one `word` token, not segmented words. That is why BM25 (or `ts_rank`) on whitespace tokens fails for Chinese.

Dictionaries ([Dictionaries](https://www.postgresql.org/docs/18/textsearch-dictionaries.html) and [`\dFd` listing](https://www.postgresql.org/docs/18/textsearch-psql.html)):

- **`simple`:** “just lower case and check for stopword.”
- **`english_stem`:** Snowball stemmer for English (used by the `english` configuration).
- **Malay:** **not listed**. Closest Snowball stemmer in the catalog is `indonesian_stem`. That is not a Malay tokenizer.
- **Chinese:** **no** `chinese_stem` / Chinese configuration in the built-in dictionary list.

`default_text_search_config` defaults to `pg_catalog.simple` unless initdb matched a locale ([Client Connection Defaults](https://www.postgresql.org/docs/18/runtime-config-client.html)).

Custom parsers require C and superuser install ([Introduction §12.1.3](https://www.postgresql.org/docs/18/textsearch-intro.html)). Extensions such as zhparser are a separate allowlist question (see `pg_textsearch` CJK below).

### Trap A — local Docker

**Runs.** FTS is core Postgres. Current image `pgvector/pgvector:0.8.6-pg18` ([compose.yaml](../../compose.yaml); [Docker Hub `pgvector/pgvector`](https://hub.docker.com/r/pgvector/pgvector)) already has it. pgvector is in the same image; FTS needs no extra extension.

### Trap B — Singapore managed

**Available** on every managed Postgres (it is core). That does not make it BM25. RDS/Aurora also list `pg_trgm` and `pg_bigm` (2-gram; useful for CJK *matching*, still not BM25) and `pgvector` ([RDS extension versions](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html); [Aurora extensions](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html)). AWS documents Aurora/RDS in `ap-southeast-1` ([Aurora regions](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.RegionsAndAvailabilityZones.html)).

---

## 2. ParadeDB `pg_search` (formerly `pg_bm25`)

**BM25: yes.**

ParadeDB’s README: ParadeDB “upgrades Postgres with a custom index for fast full-text and vector search, **BM25 scoring**, filtering, and aggregations” via the `pg_search` extension ([GitHub README](https://github.com/paradedb/paradedb/blob/main/README.md)). Scoring docs: `pdb.score(<key_field>)` “produces a **BM25 score**” ([BM25 Scoring](https://www.paradedb.com/docs/documentation/sorting/score.md)). Hybrid search “combines the strengths of **BM25 scoring and vector search**,” typically via Reciprocal Rank Fusion because the scales differ ([Hybrid Search](https://www.paradedb.com/docs/documentation/hybrid/overview.md)).

Rename: PR [#985](https://github.com/paradedb/paradedb/pull/985) “rename pg_bm25 to pg_search,” merged in [v0.6.0](https://github.com/paradedb/paradedb/releases/tag/v0.6.0).

Postgres versions: install docs say “ParadeDB supports **Postgres 15+**, and the `latest` tag ships with **Postgres 18**” ([Install](https://www.paradedb.com/docs/documentation/getting-started/install.md)). Extension install: prebuilt binaries for Postgres 15+ ([Extension](https://www.paradedb.com/docs/deploy/self-hosted/extension.md)). Dev README: supported on official PGDG Postgres starting at 15; pgrx targets 15–18 ([pg_search/README.md](https://github.com/paradedb/paradedb/blob/main/pg_search/README.md)).

pgvector coexistence: Docker image **pre-installs** `pg_search` and `pgvector` ([Third Party Extensions](https://www.paradedb.com/docs/deploy/third-party-extensions.md)). As of `0.25.0`, `pg_search` requires pgvector’s `vector` type; `CREATE EXTENSION pg_search CASCADE` creates `vector` if needed ([Extension](https://www.paradedb.com/docs/deploy/self-hosted/extension.md), [Logical replication getting started](https://www.paradedb.com/docs/deploy/logical-replication/getting-started.md)).

License: Community is **AGPLv3** ([LICENSE](https://github.com/paradedb/paradedb/blob/main/LICENSE); README). Enterprise licensing: sales ([README](https://github.com/paradedb/paradedb/blob/main/README.md)).

### Trap A — local Docker

**Yes.** Official image:

```bash
docker run ... -d paradedb/paradedb:latest
```

([Install](https://www.paradedb.com/docs/documentation/getting-started/install.md); [Docker Hub `paradedb/paradedb`](https://hub.docker.com/r/paradedb/paradedb)).

Tags on Docker Hub include `latest`, `pg18`, `latest-pg18`, `0.25.9-pg18`, and `pg15` / `pg16` / `pg17`. Image includes **pgvector** (same container).

### Trap B — Singapore managed

**pg_search is not listed** on:

| Provider | Extension list fetched | `pg_search` |
| --- | --- | --- |
| AWS RDS | [postgresql-extensions.html](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html) | not listed |
| AWS Aurora | [AuroraPostgreSQL.Extensions.html](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html) | not listed |
| Cloud SQL | [extensions](https://cloud.google.com/sql/docs/postgres/extensions) | not listed |
| AlloyDB | [extensions](https://docs.cloud.google.com/alloydb/docs/reference/extensions) | not listed (`pg_textsearch` is listed instead) |
| Azure Flexible Server | [extensions-by-engine](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine) | not listed |
| Aiven | [list-of-extensions](https://aiven.io/docs/products/postgresql/reference/list-of-extensions.md) | not listed |
| DigitalOcean Managed Postgres | [supported-extensions](https://docs.digitalocean.com/products/databases/postgresql/details/supported-extensions/) | not listed |
| Crunchy Bridge | [extensions-and-languages](https://docs.crunchybridge.com/extensions-and-languages) | not listed (`pg_textsearch` is listed) |

**Neon:** listed, then deprecated. “As of **March 19, 2026**, `pg_search` is no longer available for **new** Neon projects.” Existing projects keep it until **September 21, 2026**. AWS regions only (not Azure). Alternatives named: native FTS, `pg_trgm`, pgvector, and `lakebase_text` ([Neon pg_search](https://neon.com/docs/extensions/pg_search); [Neon extension table](https://github.com/neondatabase/website/blob/main/content/docs/extensions/pg-extensions.md)). Neon **does** have Singapore: `aws-ap-southeast-1` ([Regions](https://neon.com/docs/introduction/regions)).

**Neon `lakebase_text` (separate from ParadeDB).** Neon’s 26 Jun 2026 changelog says Lakebase Search is available to all users on Postgres 16+, via `lakebase_vector` and `lakebase_text` ([changelog](https://neon.com/docs/changelog/2026-06-26)). The `lakebase_text` page: `CREATE EXTENSION lakebase_text` adds a `lakebase_bm25` index on standard `tsvector` columns; operator `<@>` with `to_bm25query(...)` ([lakebase_text](https://neon.com/docs/extensions/lakebase-text)). That **is** BM25 in Singapore-region Neon. It is **not** ParadeDB’s API (`@@@` / `pdb.score`), and CJK still depends on Postgres `tsvector` configs (no Jieba). If the production host is Neon Singapore, store `tsvector` now and do not couple migrations to `pg_search`. The extension table still labelled an older `lakebase_text` row `0.1.0-dev` / “Requires enablement”; the dedicated docs and changelog are the stronger first-party signal that it ships. Confirm `CREATE EXTENSION lakebase_text` on a fresh `aws-ap-southeast-1` project before locking hosting.

**ParadeDB Cloud:** “coming soon. Join the waitlist.” ([Deploy overview](https://www.paradedb.com/docs/deploy/overview.md); [Install](https://www.paradedb.com/docs/documentation/getting-started/install.md)). Marketing site also says Cloud is “Currently in private beta” ([paradedb.com](https://www.paradedb.com/)). Not a public Singapore region to buy today.

**Logical replica of RDS / Neon / Cloud SQL / AlloyDB / Azure:** **yes, documented.** ParadeDB as subscriber needs **Postgres 17+**. Publisher can be “AWS RDS, Aurora, Cloud SQL, AlloyDB, or Azure Database for PostgreSQL.” Logical replication copies **rows, not indexes**; ParadeDB indexes are built on the subscriber. Azure Cosmos DB for PostgreSQL does **not** support logical replication ([Logical replication getting started](https://www.paradedb.com/docs/deploy/logical-replication/getting-started.md)).

**BYOC:** managed ParadeDB inside the customer’s **AWS or GCP** account (GovCloud and airgapped mentioned). Azure/Oracle on request. Sales access ([BYOC](https://www.paradedb.com/docs/deploy/byoc.md)). Singapore would be the cloud provider’s `ap-southeast-1` / `asia-southeast1`, not a ParadeDB-named region.

**PaaS (not managed Postgres):** Railway, Render, Fly.io, DigitalOcean **Droplet**, Dokku — these run the ParadeDB **container**, not DigitalOcean Managed Databases ([Deploy overview](https://www.paradedb.com/docs/deploy/overview.md)).

**Tembo:** Neon’s migration guide states Tembo Cloud instance creation ended **May 5, 2025** and paid instances had a **June 27, 2025** deadline ([migrate-tembo-to-neon.md](https://github.com/neondatabase/website/blob/main/content/guides/migrate-tembo-to-neon.md)). Not shippable.

### CJK

Documented tokenizers:

- [Jieba](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/jieba.md) — Chinese, dictionary + statistical models.
- [Lindera](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/lindera.md) — Chinese (CC-CEDICT), Japanese (IPADIC), Korean (KoDic).
- [Chinese compatible](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/chinese-compatible.md) — each CJK character is a token.

Malay / Singlish: no dedicated tokenizer page. Whitespace / Unicode tokenizers apply to space-separated English-derived tokens; treat Malay stemming as **not documented**.

### Local ≠ managed trap

Local `paradedb/paradedb:pg18` is **not** the same as RDS/Aurora Singapore. Shipping on `pg_search` locally and expecting `CREATE EXTENSION pg_search` on RDS will fail the allowlist.

---

## 3. VectorChord-bm25 (TensorChord)

**BM25: yes.**

Upstream README: “PostgreSQL extension for **bm25 ranking**” with Block-WeakAnd; recommended with `pg_tokenizer.rs` ([tensorchord/VectorChord-bm25 README](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/README.md)). Suite docs: VectorChord-bm25 “implements the sophisticated **BM25 ranking algorithm** directly inside PostgreSQL” ([VectorChord Suite](https://docs.vectorchord.ai/vectorchord/getting-started/vectorchord-suite.html)).

Scoring: operator `<&>` returns a **negative** BM25 score (more negative = more relevant) so default `ORDER BY` works ([README](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/README.md)).

pgvector coexistence: `tensorchord/vchord-suite` is based on official Postgres and includes `vchord`, `pg_tokenizer`, `vchord_bm25`, and `vector` ([Suite](https://docs.vectorchord.ai/vectorchord/getting-started/vectorchord-suite.html); [VectorChord-images](https://github.com/tensorchord/VectorChord-images)). Example `\dx` shows `vector | 0.8.1` alongside `vchord_bm25 | 0.3.0`.

Postgres 18: suite command uses `tensorchord/vchord-suite:pg18-latest`. Dedicated image tags include `tensorchord/vchord_bm25-postgres:pg18-v0.3.0` ([Docker Hub](https://hub.docker.com/r/tensorchord/vchord_bm25-postgres/tags)).

License: dual **AGPLv3 or Elastic License v2** ([LICENSE](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/LICENSE); README).

README limitation: “We currently have only tested against **English**.” Other languages “can be supported with bpe tokenizer…” — while the same README **does** include jieba/Lindera examples. Treat English as the tested path; CJK as documented examples, not a tested-language claim.

### Trap A — local Docker

**Yes.**

```bash
docker run \
  --name vchord-suite \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -d tensorchord/vchord-suite:pg18-latest
```

Also `ghcr.io/tensorchord/vchord-suite:pg18-latest` ([Suite](https://docs.vectorchord.ai/vectorchord/getting-started/vectorchord-suite.html); [Docker Hub `tensorchord/vchord-suite`](https://hub.docker.com/r/tensorchord/vchord-suite)).

Then:

```sql
CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_tokenizer CASCADE;
CREATE EXTENSION IF NOT EXISTS vchord_bm25 CASCADE;
```

`vchord CASCADE` pulls in `vector` (pgvector) in the documented `\dx` output. Same image, PG18.

### Trap B — Singapore managed

**Not listed** on RDS, Aurora, Cloud SQL, AlloyDB, Azure Flexible Server, Neon’s public extension table (no `vchord_bm25`), Aiven, DigitalOcean, or Crunchy Bridge (same URLs as section 2).

**pgEdge Cloud: listed.** Extensions table: `vchord_bm25` 0.2.2 “BM25 ranking for full-text vector search”; `pg_tokenizer` 0.1.1; `vector` 0.8.1 ([pgEdge supported extensions](https://docs.pgedge.com/cloud/database_admin/supported_extensions/)). Product page: VectorChord-bm25 “alongside semantic vector search”; deploy “via pgEdge Cloud managed service”; infrastructure on **AWS, Azure or Google Cloud** ([Agentic AI Toolkit](https://www.pgedge.com/products/agentic-ai-postgres); [pgEdge Cloud](https://www.pgedge.com/products/pgedge-cloud)). Cluster create: pick regions/AZs from the **customer’s cloud account** ([Creating a Cluster](https://docs.pgedge.com/cloud/cluster/create_cluster/)). Singapore is **not named** on the extensions page; BYOA on AWS `ap-southeast-1` / GCP `asia-southeast1` is consistent with “regions you have access to” but is **not an explicit Singapore SKU** in the fetched docs. Confirm at signup.

**VectorChord Cloud:** AWS only; region is a dropdown (“Don’t see the Region… contact us”) ([Regions](https://docs.vectorchord.ai/cloud/manage/regions.html)). Cluster “Extension Settings” document **pgvecto.rs and VectorChord** (vector search), including a note about RDS/Supabase FDW schema placement — **not** `vchord_bm25` ([Quick Start](https://docs.vectorchord.ai/cloud/getting-started/quick-start.html)). Do not assume VectorChord Cloud = BM25.

**Alibaba AnalyticDB for PostgreSQL** documents a `pgsearch` BM25 index (`pgsearch.create_bm25`, operator `@@@`, jieba mentioned in tokenizer config) ([usage-guide](https://www.alibabacloud.com/help/en/analyticdb/analyticdb-for-postgresql/user-guide/usage-guide)). That is a different product and API from `vchord_bm25`. Singapore region for AnalyticDB was **not confirmed** in the pages fetched; treat as **not listed** for this hosting preference.

### CJK

README section “Using jieba for Chinese text” uses `[pre_tokenizer.jieba]`. Japanese: Lindera example. Malay: not documented. Tokenizer language notes: non-space-separated languages need specialized pre-tokenizers ([README](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/README.md)).

### Local ≠ managed trap

`vchord-suite:pg18-latest` locally does **not** mean RDS Singapore can load `vchord_bm25`. The only mainstream DBaaS allowlist found that names the extension is **pgEdge Cloud**.

---

## 4. External index (OpenSearch / Elasticsearch / Typesense / Meilisearch)

Use this only if in-Postgres BM25 cannot be hosted on the chosen Singapore managed Postgres.

**OpenSearch:** default scoring is **Okapi BM25** ([Keyword search](https://docs.opensearch.org/latest/search-plugins/keyword-search/); [Similarity](https://docs.opensearch.org/latest/im-plugin/similarity/)). Amazon OpenSearch Service: “OpenSearch uses a probabilistic ranking framework called **BM-25**” ([Learning to Rank](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/learning-to-rank.html)). Region abbreviations include **APS1 = Asia Pacific (Singapore)** ([What is Amazon OpenSearch Service?](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html)). DigitalOcean documents **OpenSearch** available in **SGP1** (Singapore) ([Regional availability](https://docs.digitalocean.com/platform/regional-availability/)).

**Elasticsearch:** default similarity is **Okapi BM25** ([similarity mapping](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/similarity); [index similarity module](https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity)).

**Typesense:** ranks with a proprietary `_text_match` (token frequency, typos, field weights) — **not documented as BM25** ([Ranking and relevance](https://typesense.org/docs/guide/ranking-and-relevance.html)).

**Meilisearch:** ordered **ranking rules** with bucket sort (`words`, `typo`, `proximity`, …) — **not documented as BM25** ([Ranking rules](https://www.meilisearch.com/docs/capabilities/full_text_search/relevancy/ranking_rules)).

### Trap A — local Docker

Yes, as **separate** services (not inside the current pgvector image). Hybrid merge (keyword + vector → one list) happens in the application or via a query that unions two backends.

### Trap B — Singapore managed

OpenSearch/Elasticsearch can be hosted in Singapore independently of Postgres extension allowlists. Cost is operational: dual write or CDC, consistency, and a second SLA. AlloyDB lists a **Preview** `external_search_fdw` for “OpenSearch, Elasticsearch, and Solr” ([AlloyDB extensions](https://docs.cloud.google.com/alloydb/docs/reference/extensions)) — shallow read-only integration, not a replacement for a BM25 extension inside Postgres.

---

## Managed BM25 that Singapore actually lists: `pg_textsearch`

This is not ParadeDB or VectorChord. It is the BM25 extension several managed catalogs **do** name.

Upstream: [timescale/pg_textsearch](https://github.com/timescale/pg_textsearch) — “PostgreSQL extension for **BM25** relevance-ranked full-text search.” Postgres **17 and 18**. `CREATE INDEX ... USING bm25 (content) WITH (text_config='english')`. Operator `<@>`. Must set `shared_preload_libraries = 'pg_textsearch'` when self-hosting ([README](https://raw.githubusercontent.com/timescale/pg_textsearch/main/README.md)). License: **PostgreSQL License** ([NOTICE](https://github.com/timescale/pg_textsearch/blob/main/NOTICE)). No official `pg_textsearch` all-in-one Docker image was found on Docker Hub for this research; install is binaries or `make install`.

Chinese: README “Chinese Full-Text Search” — use **zhparser** as `text_config`. Without it, built-in Postgres parsing applies (CJK not word-segmented).

### Where it is listed (with pgvector / `vector`)

| Provider | BM25 extension | Vectors | Singapore |
| --- | --- | --- | --- |
| **Crunchy Bridge** | `pg_textsearch` “BM25 ranked full-text search (PG 17 and 18)” ([catalog](https://docs.crunchybridge.com/extensions-and-languages)) | `CREATE EXTENSION vector;` in same catalog | AWS `ap-southeast-1`, GCP `asia-southeast1` ([plans and pricing](https://docs.crunchybridge.com/concepts/plans-pricing)) |
| **Tiger Cloud** | `pg_textsearch` v1.0.0 **GA**, PG 17–18 ([changelog](https://docs.tigerdata.com/about/latest/changelog); [optimize FTS](https://www.tigerdata.com/docs/use-timescale/latest/extensions/pg-textsearch)) | [pgvector on Tiger](https://docs.tigerdata.com/use-timescale/latest/extensions/pgvector); hybrid with pgvector/pgvectorscale documented | Azure `southeastasia` (Singapore) in changelog; AWS `ap-southeast-1` in CloudWatch exporter region table ([changelog](https://docs.tigerdata.com/about/latest/changelog); [CloudWatch](https://docs.tigerdata.com/use-timescale/latest/metrics-logging/aws-cloudwatch/)) |
| **AlloyDB** | `pg_textsearch` “Best Matching 25 (BM25) scoring and indexing”, PG 17+ ([extensions](https://docs.cloud.google.com/alloydb/docs/reference/extensions)). Index how-to is **Preview** ([create BM25 index](https://docs.cloud.google.com/alloydb/docs/ai/create-bm25-index)). `k1` default 1.2, `b` default 0.75; `<@>` is negative BM25 | `vector` 0.8.2.google-1 in same catalog | `asia-southeast1` Singapore ([locations](https://cloud.google.com/alloydb/docs/locations)) |

zhparser: **not listed** on Crunchy Bridge catalog, AlloyDB extension list, Cloud SQL list, or RDS list (searched). CJK word segmentation on these managed BM25 offerings is a **second trap**: BM25 yes, Chinese segmentation no (unless you space-insert characters in the application — that workaround is not a first-party AlloyDB BM25 feature).

---

## Provider allowlist summary (BM25-related names)

“Not listed” = not in the fetched official list = **not shippable today**.

| Provider | Singapore region (docs) | `vector` / pgvector | `pg_search` | `vchord_bm25` | `pg_textsearch` |
| --- | --- | --- | --- | --- | --- |
| AWS RDS / Aurora | `ap-southeast-1` | listed (`pgvector`) | not listed | not listed | not listed |
| Google Cloud SQL | `asia-southeast1` ([locations](https://cloud.google.com/sql/docs/postgres/locations)) | listed (`pgvector`) | not listed | not listed | not listed |
| AlloyDB | `asia-southeast1` | listed (`vector`) | not listed | not listed | **listed** (PG17+; BM25 how-to Preview) |
| Azure Database for PostgreSQL | Flexible Server regions vary; Singapore not verified on the extension page | listed (`vector`) ([extensions-by-engine](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine)) | not listed | not listed | not listed |
| Neon | `aws-ap-southeast-1` | listed | listed but **deprecated** for new projects | not listed | not listed as `pg_textsearch`; **`lakebase_text` / `lakebase_bm25` is Neon’s BM25** ([lakebase_text](https://neon.com/docs/extensions/lakebase-text); [changelog 2026-06-26](https://neon.com/docs/changelog/2026-06-26)) |
| Supabase | not confirmed in the extensions overview fetched | listed (`vector`) ([pgvector](https://supabase.com/docs/guides/database/extensions/pgvector)) | not on the overview page; native extensions are a **fixed image** ([custom extensions](https://supabase.com/docs/guides/self-hosting/custom-postgres-extensions)) | not listed | not listed |
| Aiven | `aws-ap-southeast-1`, `do-sgp` ([clouds](https://aiven.io/docs/platform/reference/list_of_clouds)) | listed (`pgvector`) | not listed | not listed | not listed (search section: `pg_trgm`, `rum`, …) |
| Tiger Cloud | AWS `ap-southeast-1`; Azure `southeastasia` | listed | not listed | not listed | **listed (GA)** |
| Crunchy Bridge | AWS `ap-southeast-1`; GCP `asia-southeast1` | listed | not listed | not listed | **listed (PG17–18)** |
| DigitalOcean Managed Postgres | `SGP1` | listed (`vector`) | not listed | not listed | not listed |
| ParadeDB Cloud | n/a | n/a | Cloud coming soon / waitlist | n/a | n/a |
| VectorChord Cloud | AWS dropdown; Singapore **not named** | VectorChord / pgvecto.rs | not listed | **not listed** on cluster extension docs | not listed |
| Tembo Cloud | n/a | historical ParadeDB stack | sunset 2025 | n/a | n/a |
| pgEdge Cloud | AWS/Azure/GCP; Singapore **not named** on extensions page | listed | not listed | **listed** | not listed |

Azure: you cannot bring your own extension; only `SHOW azure.extensions` ([create extensions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-create-extensions)).

---

## CJK / Malay / Singlish (all options)

| Mechanism | Chinese | Malay / Singlish | Part numbers / codes |
| --- | --- | --- | --- |
| Postgres default parser | Unsegmented `word` if no spaces | Space-separated; no `malay` Snowball dictionary | `numword` / `uint` / `version` token types exist |
| `english` / `simple` | Wrong granularity | `simple` lowercases; `english` stems English (may mangle Malay) | `simple` keeps tokens after lowercase |
| ParadeDB | Jieba / Lindera / per-character | Unicode/whitespace; no Malay page | Literal tokenizer indexes raw text |
| VectorChord-bm25 + pg_tokenizer | jieba example | not documented | custom model / bert / unicode |
| `pg_textsearch` | zhparser (extension **not listed** on Crunchy/AlloyDB/RDS) | `text_config` like `simple` | `simple` config |
| OpenSearch / Elasticsearch | Lucene CJK analyzers (configure per index) | Standard analyzers | `keyword` fields for exact codes |

RDS/Aurora/AlloyDB/Cloud SQL **do** list `pg_bigm` (2-gram FTS) — CJK *matching* without BM25 ([RDS extensions](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html); [Cloud SQL pg_bigm](https://cloud.google.com/sql/docs/postgres/extensions); [AlloyDB pg_bigm](https://docs.cloud.google.com/alloydb/docs/reference/extensions)).

---

## Sources (primary)

Postgres 18: [textsearch-controls](https://www.postgresql.org/docs/18/textsearch-controls.html), [functions-textsearch](https://www.postgresql.org/docs/18/functions-textsearch.html), [textsearch-intro](https://www.postgresql.org/docs/18/textsearch-intro.html), [textsearch-parsers](https://www.postgresql.org/docs/18/textsearch-parsers.html), [textsearch-dictionaries](https://www.postgresql.org/docs/18/textsearch-dictionaries.html), [textsearch-indexes](https://www.postgresql.org/docs/18/textsearch-indexes.html), [textsearch-psql](https://www.postgresql.org/docs/18/textsearch-psql.html), [runtime-config-client](https://www.postgresql.org/docs/18/runtime-config-client.html).

ParadeDB: [GitHub README](https://github.com/paradedb/paradedb/blob/main/README.md), [LICENSE](https://github.com/paradedb/paradedb/blob/main/LICENSE), [install](https://www.paradedb.com/docs/documentation/getting-started/install.md), [third-party-extensions](https://www.paradedb.com/docs/deploy/third-party-extensions.md), [score](https://www.paradedb.com/docs/documentation/sorting/score.md), [hybrid](https://www.paradedb.com/docs/documentation/hybrid/overview.md), [jieba](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/jieba.md), [lindera](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/lindera.md), [chinese-compatible](https://www.paradedb.com/docs/documentation/tokenizers/available-tokenizers/chinese-compatible.md), [extension install](https://www.paradedb.com/docs/deploy/self-hosted/extension.md), [logical replication](https://www.paradedb.com/docs/deploy/logical-replication/getting-started.md), [deploy overview](https://www.paradedb.com/docs/deploy/overview.md), [BYOC](https://www.paradedb.com/docs/deploy/byoc.md), [Docker Hub](https://hub.docker.com/r/paradedb/paradedb), [rename PR](https://github.com/paradedb/paradedb/pull/985).

VectorChord: [suite](https://docs.vectorchord.ai/vectorchord/getting-started/vectorchord-suite.html), [README](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/README.md), [LICENSE](https://raw.githubusercontent.com/tensorchord/VectorChord-bm25/main/LICENSE), [VectorChord-images](https://github.com/tensorchord/VectorChord-images), [vchord-suite Docker Hub](https://hub.docker.com/r/tensorchord/vchord-suite), [vchord_bm25-postgres tags](https://hub.docker.com/r/tensorchord/vchord_bm25-postgres/tags), [Cloud quick start](https://docs.vectorchord.ai/cloud/getting-started/quick-start.html), [Cloud regions](https://docs.vectorchord.ai/cloud/manage/regions.html).

`pg_textsearch`: [GitHub](https://github.com/timescale/pg_textsearch), [README](https://raw.githubusercontent.com/timescale/pg_textsearch/main/README.md), [NOTICE](https://github.com/timescale/pg_textsearch/blob/main/NOTICE), [Tiger docs](https://www.tigerdata.com/docs/use-timescale/latest/extensions/pg-textsearch), [AlloyDB BM25](https://docs.cloud.google.com/alloydb/docs/ai/create-bm25-index), [AlloyDB FTS overview](https://docs.cloud.google.com/alloydb/docs/ai/full-text-search-overview).

Providers: RDS, Aurora, Cloud SQL, AlloyDB, Azure, Neon, Aiven, Crunchy Bridge, DigitalOcean, pgEdge, Tembo sunset, OpenSearch, Elasticsearch — URLs in the tables above.

Local compose: `compose.yaml` image `pgvector/pgvector:0.8.6-pg18`; [pgvector Docker Hub](https://hub.docker.com/r/pgvector/pgvector).
