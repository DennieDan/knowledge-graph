# Which embedding model survives a mixed-language test

- **Date:** 2026-09-16
- **Ticket:** Which embedding model survives a mixed-language test
- **Pinned today:** `EMBEDDING_DIMENSIONS = 384`, `EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"` in `apps/api/app/models.py`
- **Constraint:** changing the vector width needs a schema migration; changing the model needs a full re-embed. Both are one-time. Width change is extra DDL on the pgvector column.

## Recommendation

Use **`intfloat/multilingual-e5-small`**, **384 dimensions**, self-hosted on the existing API CPU in the company’s own region (Singapore if the API already lives there).

It is the only retrieval-trained open model in this survey that keeps the current 384-wide column, is MIT-licensed for commercial self-host, claims Chinese and Malay in its language list, and has published Indonesian and Chinese retrieval numbers. Query and passage strings must be prefixed with `query: ` and `passage: `. Max length is 512 tokens.

Do not send Drive/WhatsApp chunk text to OpenAI, Google, or Jina for embeddings. OpenAI’s Singapore project stores embeddings at rest in Singapore but **does not run inference there**. Jina’s public model catalog lists v3 datacenters in the US. Self-hosting e5-small avoids that.

**If a later mixed-language retrieval test on a larger invented corpus shows e5-small missing Chinese or Malay paraphrases,** graduate to `intfloat/multilingual-e5-base` (768) or `BAAI/bge-m3` (1024). That is a width migration plus a re-embed, not a hosting-cost problem at this corpus size.

**Do not stay on `all-MiniLM-L6-v2` for product retrieval.** Hugging Face tags it `language: en`. It is not English-token-only — a WordPiece model will still emit vectors for Chinese or Malay — but it was not trained as a multilingual retriever, truncates at 256 word pieces, and in the smoke test below it ranked a *different fact* into Chinese and Malay top-3 while e5-small kept paraphrases of the same fact together.

**Order-of-magnitude hosting (10–100 people, tens of thousands of chunks, not millions):** ~**$0–40 / month**. e5-small is 118M parameters and fits in CPU RAM on the box that already runs the API. A dedicated 2-vCPU Singapore VM is tens of dollars a month if you isolate it. API embedding of the same corpus is cents, but the data leaves the company.

---

## Comparison table

| Model | Dim | ZH / MS / ID claimed | Published ZH / ID / MS retrieval | License | Params | Prefixes | Max tokens | Inference location | Cost at this scale |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sentence-transformers/all-MiniLM-L6-v2` (current) | 384 | `language: en` only | none (English-oriented) | Apache-2.0 | 22.7M | none | 256 word pieces | self-host (wherever you run it) | ~$0 on existing CPU |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | ZH-CN/TW, MS, ID in card | no MIRACL/MTEB retrieval numbers on the card | Apache-2.0 | 117.7M | none | 128 | self-host | ~$0–40 / mo CPU |
| **`intfloat/multilingual-e5-small`** | **384** | **100 XLM-R langs incl. zh, ms, id** | **MIRACL zh 45.9 / id 50.7 nDCG@10; Mr. TyDi id 63.2 MRR@10. No Malay MIRACL.** | **MIT** | **117.7M** | **`query:` / `passage:`** | **512** | **self-host** | **~$0–40 / mo CPU** |
| `intfloat/multilingual-e5-base` | 768 | same 100 langs | MIRACL zh 51.5 / id 51.1 nDCG@10; Mr. TyDi id 64.9 | MIT | 278.0M | `query:` / `passage:` | 512 | self-host | ~$0–80 / mo CPU |
| `Alibaba-NLP/gte-multilingual-base` | 768 (elastic 128–768) | 70+ langs; card lists zh, ms, id | MIRACL **average** 62.1 nDCG@10 (dense); C-MTEB zh 62.72. No per-lang MIRACL zh/id/ms table in the paper. No Malay MIRACL. | Apache-2.0 | 305M (paper: 304M) | none required | 8192 | self-host | CPU possible; GPU nicer |
| `BAAI/bge-m3` | 1024 | 100+ langs | MIRACL dense zh **61.7** / id **56.0**; MKQA ms Recall@100 **77.2**. No Malay in MIRACL. | MIT | 568M (paper) | none (unlike BGE 1.5) | 8192 | self-host | GPU preferred; CPU slow |
| `jinaai/jina-embeddings-v3` | 1024 (MRL 32…1024; **384 not listed**) | 30 tuned langs incl. Chinese + Indonesian; card also tags `ms` | MTEB Chinese STS on card (AFQMC). No MIRACL zh/id/ms table cited here. | **CC BY-NC 4.0** (commercial self-host needs a paid license) | 572M | task LoRA: `retrieval.query` / `retrieval.passage` | 8192 | HF self-host **or** Jina API (**US** datacenter in catalog) | API $0.05 / 1M tok; commercial on-prem is a license, not Apache/MIT |
| OpenAI `text-embedding-3-small` | 1536 default (shorten via `dimensions`) | “higher multilingual performance”; no ZH/MS list | MIRACL avg **44.0**; MTEB **62.3**. No per-lang ZH/MS. | API ToS | n/a | none | 8192 | OpenAI. Singapore project: **storage yes, processing no** | $0.02 / 1M tokens |
| OpenAI `text-embedding-3-large` | 3072 default | “english and non-english” | MIRACL avg **54.9**; MTEB **64.6**. Still below mE5/BGE-M3 on MIRACL avg. | API ToS | n/a | none | 8192 | same as small | $0.13 / 1M tokens |
| Google `gemini-embedding-001` | 3072 default (MRL 128–3072; rec. 768/1536/3072) | 100+ langs incl. Chinese, Malay, Indonesian | Vertex: “state-of-the-art across English, multilingual and code”. No MIRACL zh/ms numbers on the model page. | API ToS | n/a | `task_type` RETRIEVAL_QUERY / RETRIEVAL_DOCUMENT | 2048 | Google. Vertex region `asia-southeast1` exists; Gemini API is Google-hosted | $0.15 / 1M input tokens |
| Google `text-embedding-004` | n/a in 2026 docs | n/a | n/a | n/a | n/a | n/a | n/a | **Not the current documented model.** Docs now lead with `gemini-embedding-001` / `gemini-embedding-2`. Vertex English specialist is `text-embedding-005`. | — |

`thenlper/gte-multilingual` **does not exist**. `thenlper/gte-base` is English-only, 768-d, 512 tokens. The current multilingual GTE is `Alibaba-NLP/gte-multilingual-base`.

**384, no width migration:** all-MiniLM, paraphrase-multilingual-MiniLM, multilingual-e5-small. (GTE can *store* 384 via elastic/MRL output in `[128, 768]`; native width is still 768. OpenAI/Gemini can shorten to 384 via API parameters, but that is still a third-party API.)

**Need 768:** e5-base, GTE multilingual (native).

**Need 1024+:** bge-m3, jina-v3 native, OpenAI/Gemini defaults.

---

## 1. Current model: `sentence-transformers/all-MiniLM-L6-v2`

It is **English-oriented, not a hard English tokenizer lock.** Hugging Face will still encode non-English bytes; the card does not claim multilingual retrieval.

| Claim | Source |
| --- | --- |
| 384-dimensional dense vectors | [HF model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |
| `language: en`, `license: apache-2.0` | [card YAML](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/raw/main/README.md) |
| 22,713,728 parameters | Hugging Face `safetensors.total` via [model API](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2) |
| Intended use: sentence / short-paragraph encoder for retrieval, clustering, similarity | [HF card, “Intended uses”](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |
| Truncation: input longer than **256 word pieces** | same |
| Base checkpoint: `nreimers/MiniLM-L6-H384-uncased` (every-second-layer cut of Microsoft MiniLM) | [HF card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [nreimers card](https://huggingface.co/nreimers/MiniLM-L6-H384-uncased) |
| Microsoft MiniLM-L12-H384 is an **English** UniLM-v2 distillation, 33M params, evaluated on SQuAD/GLUE | [microsoft/MiniLM-L12-H384-uncased](https://huggingface.co/microsoft/MiniLM-L12-H384-uncased) |
| Fine-tune data is ~1.17B English-centric pairs (Reddit, S2ORC, MS MARCO, SNLI/MultiNLI, …) | [HF card training table](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |
| Sentence-Transformers docs place `all-MiniLM-L6-v2` under **Original Models** (general-purpose, 5× faster than `all-mpnet-base-v2`). **Multilingual Models** are a separate section with a 50+ language list that does **not** include `all-MiniLM-L6-v2`. | [sbert.net pretrained models](https://sbert.net/docs/sentence_transformer/pretrained_models.html) |
| No query/passage prefixes | card usage example encodes raw sentences |

**Is it English-only?** Official metadata says English. The WordPiece vocab will fragment Chinese characters and Malay agglutinative tokens rather than representing them as trained lexical units. There are **no** MIRACL/MTEB Chinese or Malay retrieval numbers on this card. Treat it as English-first, not as “will throw on 中文.”

---

## 2. Candidate models

### 2.1 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384)

Keep-384 multilingual **paraphrase** model, not a retrieval specialist.

| | |
| --- | --- |
| Dimensions | 384; architecture `max_seq_length: 128` ([card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)) |
| Languages | Card YAML lists 50+ ISO codes including **`id`, `ms`**, plus BCP-47 **`zh-cn`, `zh-tw`**. Sentence-Transformers docs: trained on parallel data for **ar, bg, …, id, …, ms, …, zh-cn, zh-tw** ([sbert.net multilingual section](https://sbert.net/docs/sentence_transformer/pretrained_models.html); paper [Reimers & Gurevych 2019](http://arxiv.org/abs/1908.10084) is the SBERT method citation on the card). |
| License | Apache-2.0 ([README YAML](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/blob/main/README.md)) |
| Params / speed | 117,654,272 params ([HF API](https://huggingface.co/api/models/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)). ~5× the current MiniLM; 12 BERT layers vs 6. |
| Prefixes | None. |
| Max tokens | **128** (too short for many Drive chunks). |
| Hosting | Self-host CPU. Inference is wherever you load weights. |
| Cost | Same order as e5-small (both ~118M). |

Docs describe it as a multilingual version of `paraphrase-MiniLM-L12-v2` for semantic similarity / cross-lingual paraphrase, not as a MIRACL retriever. **No Chinese or Malay nDCG on the card.**

### 2.2 `intfloat/multilingual-e5-small` (384) — recommended

| | |
| --- | --- |
| Dimensions | 384; 12 layers ([card](https://huggingface.co/intfloat/multilingual-e5-small)) |
| Init | `microsoft/Multilingual-MiniLM-L12-H384` (XLM-R tokenizer + BERT-like MiniLM). Microsoft: 21M transformer + 96M embedding params ([Microsoft card](https://huggingface.co/microsoft/Multilingual-MiniLM-L12-H384)). |
| Languages | “100 languages from xlm-roberta”; low-resource may degrade. Card language list includes **`zh`, `ms`, `id`**. XLM-R itself is trained on 100 languages including **Malay (`ms`, 8.5 GiB) and Indonesian (`id`, 148.3 GiB)** ([Conneau et al., ACL 2020](https://aclanthology.org/2020.acl-main.747/)). |
| License | MIT ([card YAML](https://huggingface.co/intfloat/multilingual-e5-small/raw/main/README.md)) |
| Params | 117,654,272 ([HF API](https://huggingface.co/api/models/intfloat/multilingual-e5-small)) |
| Prefixes | **Required:** `query: ` / `passage: ` even for non-English. Symmetric tasks use `query:` only. Skipping prefixes degrades retrieval ([card FAQ](https://huggingface.co/intfloat/multilingual-e5-small)). |
| Max tokens | 512 |
| Supervised data | Includes **DuReader Retrieval (Chinese, 86k)** and **Mr. TyDi / MIRACL** (11 / 16 languages). Mr. TyDi columns include **Indonesian (`id`)**, not Malay. |
| Hosting | Self-host CPU. Sentence-Transformers supported. |
| Paper | [Wang et al., arXiv:2402.05672](https://arxiv.org/pdf/2402.05672) |

**Published retrieval (same paper/card):**

- Mr. TyDi MRR@10 **Indonesian `id`: 63.2** (small), 64.9 (base).
- MIRACL nDCG@10 (paper Table 6): **zh 45.9 / 51.5 / 56.0** (small/base/large); **id 50.7 / 51.1 / 52.9**. Average over 16 langs: 60.8 / 62.3 / 66.5.
- English MTEB (56 datasets): small **57.9**, base **59.5** (weaker than English-only BGE-large 64.2 — expected tradeoff).
- **Malay `ms` is not a MIRACL language.** No Malay nDCG is published for e5. Closest lexical proxy is Indonesian.

### 2.3 `intfloat/multilingual-e5-base` (768)

Same recipe, initialized from `xlm-roberta-base`, embedding size **768**, 12 layers, **278,044,162 params**, MIT, 512 tokens, same prefixes ([card](https://huggingface.co/intfloat/multilingual-e5-base)). Better MIRACL Chinese (51.5 vs 45.9) for a width migration. Paper lists mE5-base at **279M** ([Table 4 in mGTE paper](https://arxiv.org/html/2407.19669v2) reports 279M / seq 514).

### 2.4 `BAAI/bge-m3` (1024)

Strongest **open** multilingual retrieval evidence in this set. Needs a 1024-d column.

| | |
| --- | --- |
| Dimensions / seq | 1024 / 8192 ([card specs table](https://huggingface.co/BAAI/bge-m3)) |
| Languages | “more than 100 working languages” |
| License | MIT ([card YAML](https://huggingface.co/BAAI/bge-m3/raw/main/README.md)) |
| Params | 568M ([Zhang et al. mGTE Table 4](https://arxiv.org/html/2407.19669v2), row “BGE-M3 Dense”) |
| Prefixes | **No query instructions** (unlike BGE 1.5). FAQ: “no longer requires adding instructions to the queries.” |
| Extra | Dense + learned sparse + ColBERT multi-vector. Hybrid is optional. |
| Paper | [Chen et al., arXiv:2402.03216](https://arxiv.org/html/2402.03216v3) |

**MIRACL dev nDCG@10 (paper Table 2, Dense row):** zh **61.7**, id **56.0**, en 56.9, avg 67.8. Hybrid “All” zh 63.9, id 59.1, avg 70.0.

**MKQA Recall@100 includes Malay:** `ms` BM25 55.9, mE5-large 76.3, OpenAI-3 73.3, **M3 Dense 77.2**, M3 All 77.4 (Table 3). This is the **only published Malay retrieval number** in this survey. MIRACL itself has **no Malay** ([Zhang et al., TACL 2023](https://doi.org/10.1162/tacl_a_00595): 18 languages, Indonesian and Chinese yes, Malay no).

CPU will run it; 568M is uncomfortable for tight API latency without a GPU. Fine for batch re-embed of tens of thousands of chunks on CPU overnight.

### 2.5 Alibaba GTE multilingual (current: `Alibaba-NLP/gte-multilingual-base`)

`thenlper/gte-multilingual` is not a Hub model. `thenlper/gte-base` “exclusively caters to English texts” and truncates at 512 ([thenlper/gte-base](https://huggingface.co/thenlper/gte-base)). The 2024 multilingual line is **`Alibaba-NLP/gte-multilingual-base`** ([card](https://huggingface.co/Alibaba-NLP/gte-multilingual-base); paper [Zhang et al., EMNLP 2024 Industry, mGTE](https://aclanthology.org/2024.emnlp-industry.103/)).

| | |
| --- | --- |
| Dimensions | **768** native; card: output dimension “should be in **[128, 768]**” (elastic / MRL). You *could* persist 384 without DDL, with some quality loss vs 768. |
| Languages | “over 70 languages.” Card language list includes **`zh`, `ms`, `id`**. Pretrain stats include Malay 0.39B tokens vs Indonesian 7.46B vs zh-cn 167B ([paper Appendix](https://arxiv.org/html/2407.19669v2)). |
| License | Apache-2.0 (card YAML) |
| Params | Card 305M; paper 304M |
| Prefixes | Dense usage examples use raw text. |
| Max tokens | 8192 |
| Hosting | Self-host; official TEI Docker snippet on the card. Commercial Alibaba Cloud embedding APIs are **not the same weights**. |

**Evidence:** MTEB Chinese overall **62.72** vs BGE-M3 dense 60.80 vs mE5-base 56.21 (paper Table 3). MIRACL **average** dense 62.1 (vs BGE-M3 67.7, mE5-base 62.3). **No per-language MIRACL zh/id/ms numbers in the paper tables pulled for this note.** Fine-tune mix includes DuReader, mMARCO-zh, T2-Ranking, Mr.TyDi, MIRACL, MLDR — Chinese yes, Malay as pretrain language yes, Malay retrieval benchmark **no**.

### 2.6 `jinaai/jina-embeddings-v3` (still current)

Still in Jina’s live catalog (`GET https://api.jina.ai/v1/models`, id `jina-ai/jina-embeddings-v3`, context 8192) alongside newer v5 models. Card last positioned as multilingual multi-task with 5 LoRA adapters ([HF card](https://huggingface.co/jinaai/jina-embeddings-v3); paper [arXiv:2409.10173](https://arxiv.org/abs/2409.10173)).

| | |
| --- | --- |
| Dimensions | Native 1024. Matryoshka sizes **32, 64, 128, 256, 512, 768, 1024**. **384 is not in that list.** Truncating to 384 would be unofficial. |
| Languages | Foundation 100 langs; **tuning focused on 30**, including **Chinese** and **Indonesian**. Card tags also include `ms`. **Malay is not in the 30-language tuning list.** |
| License | **CC BY-NC 4.0**. Card: listed on AWS & Azure; on-prem commercial use needs a license. Jina embeddings page (2026): commercial self-host via Elastic “Jina On-Prem” SKU; API use is covered by service terms ([jina.ai/embeddings](https://jina.ai/embeddings/)). |
| Params | 572,310,396 ([HF API](https://huggingface.co/api/models/jinaai/jina-embeddings-v3)); docs also say 570M. |
| Prefixes | Task argument: `retrieval.query` / `retrieval.passage` (asymmetric). Wrong side degrades retrieval ([Jina FAQ](https://jina.ai/embeddings/)). |
| Max tokens | 8192 |
| Hosting / cost | HF self-host only if license allows. **API `pricing.prompt = 0.00000005` → $0.05 / 1M tokens.** Catalog `datacenters: [{ "country_code": "US" }]`. |

Card reports MTEB Chinese STS (AFQMC cosine Spearman 43.473) — similarity, not MIRACL nDCG. **No Malay retrieval number found on the card or pricing catalog.**

### 2.7 OpenAI `text-embedding-3-small` / `3-large` (API)

Still the current embedding models on OpenAI’s 2026 model pages.

| | small | large |
| --- | --- | --- |
| Default dim | 1536 | 3072 |
| Shorten | `dimensions` parameter (MRL) | same |
| Max input | 8192 | 8192 |
| MTEB | 62.3% | 64.6% |
| MIRACL average | **44.0** | **54.9** |
| Price | **$0.02 / 1M** input tokens | **$0.13 / 1M** |
| Pages/$ (≈800 tok/page) | 62,500 | 9,615 |

Sources: [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings), [3-small model page](https://developers.openai.com/api/docs/models/text-embedding-3-small), [3-large model page](https://developers.openai.com/api/docs/models/text-embedding-3-large), [2024 launch blog](https://openai.com/index/new-embedding-models-and-api-updates/) ($0.00002 / 1k = $0.02 / 1M; large $0.00013 / 1k = $0.13 / 1M).

Languages: launch post says “higher multilingual performance.” Large card: “most capable … for both english and non-english tasks.” **No official ZH/MS language list. No per-language MIRACL.** BGE-M3 paper’s OpenAI-3 MIRACL average is 54.9 with **per-language cells blank**.

**Where inference happens:** Default `/v1/embeddings` is OpenAI-hosted. [Your data / data residency](https://developers.openai.com/api/docs/guides/your-data): Singapore `sg.api.openai.com` is **Storage Yes, Processing No**. “If your selected Region does not support regional processing … OpenAI may also process and temporarily store Customer Content **outside of the Region**.” Embeddings are eligible for residency *storage*; Singapore is **not** an embeddings processing region (US and EU are). **Chunk text still leaves the company and may be inferred in the US/EU.** `/v1/embeddings` is Zero Data Retention eligible in the endpoint table, but that is retention, not location.

### 2.8 Google Gemini embedding / `text-embedding-004`

**`text-embedding-004` is not the documented current model** as of 2026-09-16. [Gemini embeddings docs](https://ai.google.dev/gemini-api/docs/embeddings) lead with `gemini-embedding-001` (text) and `gemini-embedding-2` (multimodal). Some SDK snippets still pass the string `"text-embedding-004"`. Vertex’s English specialist is `text-embedding-005`; multilingual specialist `text-multilingual-embedding-002`; unified SOTA `gemini-embedding-001` ([Vertex text embeddings](https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings)).

**`gemini-embedding-001`** ([model card](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001), updated June 2025):

- Input limit **2,048** tokens (shorter than OpenAI/BGE-M3).
- Output **128–3072**; recommended **768, 1536, 3072**. Default 3072. 384 is *allowed* by the range, not recommended.
- Task types include `RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT` ([embeddings guide](https://ai.google.dev/gemini-api/docs/embeddings)).
- Languages: Vertex lists **Chinese (Simplified and Traditional), Malay, Indonesian**, plus 100+ others.
- Price: Gemini API paid **$0.15 / 1M input tokens**, batch $0.075 ([Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)). Vertex table: Gemini Embedding online **$0.00015 / 1,000 = $0.15 / 1M** ([Agent Platform pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)).
- `gemini-embedding-2` text input is **$0.20 / 1M** — multimodal, not needed here.

**Where inference happens:** Gemini API is Google-hosted (not your VPC). Vertex documents region **Singapore (`asia-southeast1`)** in the Asia Pacific location table ([Vertex locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)). The converted table in this research pass did not preserve per-cell availability marks, so **do not assume embeddings are enabled in Singapore without checking the live matrix.** Even in-region Vertex is still Google, not on-prem.

No MIRACL Chinese/Malay numbers on the Google model pages cited above.

---

## 3. Published evidence: Chinese, Indonesian, Malay

**MIRACL** ([Zhang et al., TACL 2023](https://doi.org/10.1162/tacl_a_00595)): 18 languages, same-language Wikipedia retrieval, nDCG@10. Includes **Chinese (`zh`) and Indonesian (`id`)**. **Does not include Malay (`ms`).** Anyone quoting “Malay MIRACL” is inventing it.

**Mr. TyDi** (on e5 cards): 11 languages including **Indonesian**, not Malay.

**MKQA** (cross-lingual): BGE-M3 paper Table 3 **does include Malay (`ms`)**.

| Model | ZH retrieval | ID retrieval | MS retrieval |
| --- | --- | --- | --- |
| all-MiniLM-L6-v2 | not reported | not reported | not reported |
| paraphrase-multilingual-MiniLM | not reported | not reported | not reported |
| mE5-small | MIRACL nDCG@10 **45.9** | MIRACL **50.7**; Mr. TyDi MRR@10 **63.2** | **not reported** |
| mE5-base | MIRACL **51.5** | MIRACL **51.1**; Mr. TyDi **64.9** | **not reported** |
| mE5-large | MIRACL **56.0** | MIRACL **52.9** | MKQA R@100 **76.3** |
| BGE-M3 Dense | MIRACL **61.7**; C-MTEB **60.80** | MIRACL **56.0** | MKQA R@100 **77.2** |
| mGTE-TRM Dense | C-MTEB **62.72**; MIRACL avg 62.1 (no zh cell) | not broken out | **not reported** |
| OpenAI-3-small | MIRACL **avg 44.0** (no zh cell) | not broken out | not broken out |
| OpenAI-3-large | MIRACL **avg 54.9** | not broken out | MKQA R@100 **73.3** (paper’s “OpenAI-3”) |
| Jina v3 | MTEB AFQMC STS only | not reported | not reported |
| Gemini embedding | not reported on model pages | not reported | not reported |

**Singlish and intra-sentence EN/ZH/MS code-switching have no public embedding leaderboard.** XLM-R/e5/BGE may transfer from related languages; that is a hypothesis, not a number.

Chinese is a **high-resource** training language for e5 (DuReader), GTE, and BGE-M3. Malay is **present in XLM-R / GTE pretraining at much lower volume than Indonesian**. Using Indonesian numbers as a Malay proxy is common and **must be labelled as a proxy**.

---

## 4. Dimension implication

Pinned schema: `Vector(384)`.

**No vector-width migration (still re-embed if the model id changes):**

- `intfloat/multilingual-e5-small` (native 384) — **recommended**
- `paraphrase-multilingual-MiniLM-L12-v2` (native 384, 128-token cap — reject for chunk retrieval)
- staying on `all-MiniLM-L6-v2` (reject for mixed-language product retrieval)

**Optional 384 storage from a wider native model (still a model change + re-embed; quality vs native width not free):**

- `Alibaba-NLP/gte-multilingual-base` elastic dim in `[128, 768]`
- OpenAI `dimensions=384` / Gemini `output_dimensionality=384` (API; Google does not recommend 384)

**Width migration required:**

- 768: `multilingual-e5-base`, GTE native
- 1024: `bge-m3`, jina-v3 native
- 1536 / 3072: OpenAI / Gemini defaults

pgvector: `ALTER` the `Vector(N)` column, then backfill. Do not mix models in one column.

---

## 5. Hosting cost (10–100 person company, tens of thousands of chunks)

Assumptions used only for order-of-magnitude, not a quote:

- ~50k chunks × ~200 tokens ≈ **10M tokens** one-time embed
- ongoing: a few million tokens/month of new chunks + queries

| Path | One-time embed of 10M tok | Monthly at a few M tok | Data location |
| --- | --- | --- | --- |
| **e5-small on existing API CPU (Singapore or wherever the API already runs)** | electricity / idle CPU | **~$0 extra** | in-process, your VPC |
| Dedicated small VM, Asia Pacific (Singapore) | same | **tens of USD/month** on-demand for a small general-purpose instance | [AWS On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/); region list [AWS regions](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/) (`ap-southeast-1`) |
| e5-base on CPU | slower batch; still fine overnight | same VM band, maybe one size up | same |
| bge-m3 on CPU | overnight batch OK; query latency worse | GPU if you care about p95 | same |
| OpenAI 3-small | 10M × $0.02/1M = **$0.20** | **cents** | **leaves company**; SG storage ≠ SG inference |
| OpenAI 3-large | 10M × $0.13/1M = **$1.30** | cents–dollars | same |
| Gemini embedding-001 | 10M × $0.15/1M = **$1.50** | similar | Google-hosted |
| Jina v3 API | 10M × $0.05/1M = **$0.50** | cents | **US** per catalog |

API token prices are negligible at this scale. **The product constraint is not money; it is whether WhatsApp/Drive text is sent to a US/EU GPU.** Prefer self-hosted MIT/Apache models.

e5-small (~470 MB weights, 118M params) is the same size class as paraphrase-multilingual-MiniLM. Hugging Face [Text Embeddings Inference](https://huggingface.co/Alibaba-NLP/gte-multilingual-base) documents CPU Docker for encoder models; e5-small does not need a GPU for tens of thousands of vectors.

Jina commercial on-prem is a **license SKU**, not a $0 Apache drop-in. Skip it unless there is a separate reason to pay Elastic.

---

## 6. Why this one model

1. **Quality vs MiniLM:** published Chinese + Indonesian retrieval; MiniLM has none. Same 384-d column.
2. **Quality vs paraphrase-multilingual-MiniLM:** retrieval-trained (MS MARCO, MIRACL, DuReader) vs paraphrase distillation; 512 vs 128 tokens.
3. **Quality vs e5-base / bge-m3:** those win MIRACL (especially BGE-M3 Chinese 61.7 vs e5-small 45.9). At tens of thousands of chunks the operational win of **no width migration + CPU** outweighs that gap **until a live test says otherwise**.
4. **Quality vs OpenAI/Gemini:** OpenAI-3 MIRACL average (44.0 small / 54.9 large) is **below** mE5-small’s 60.8 average. Paying to send private text off-box is a worse privacy/quality trade here.
5. **License:** MIT, commercial self-host, no CC-BY-NC.
6. **Integration:** Sentence-Transformers; must add prefixes in the embedder. Store `embedding_model = "intfloat/multilingual-e5-small"` next to the vector.

**Implementation notes (not a migration plan):**

- Prefix every query with `query: ` and every chunk with `passage: `.
- Normalize embeddings (card does).
- Cap chunks at 512 tokens (already likely for this product).
- Re-embed everything; do not mix MiniLM and e5 vectors.

---

## Retrieval test

Ran 2026-09-16 on CPU with `sentence-transformers==6.0.1`, **invented sentences only** (no customer data). Script: [`run_embedding_test.py`](run_embedding_test.py). Ranks: [`embedding-test-results.json`](embedding-test-results.json).

12 passages (Atlas launch in EN/ZH/MS/Singlish/code-switch; WO-4412 revision; SKU-A19 price; two distractors) and 10 paraphrased / code-switched queries. Metric: cluster recall (did the top hit belong to the same fact).

| Model | recall@1 | recall@3 | What the ranks actually show |
| --- | --- | --- | --- |
| all-MiniLM-L6-v2 | 1.0 | 1.0 | **Same-language / shared-token retrieval.** English Atlas query top-3: `atlas-en`, `atlas-mix`, `atlas-sg` — **not** `atlas-zh`. Chinese Atlas query top-3: `atlas-zh`, `dist-zh`, `wo-zh` (other Chinese rows). Codes like `WO-4412` carry MiniLM. |
| paraphrase-multilingual-MiniLM-L12-v2 | 1.0 | 1.0 | **Cross-lingual.** Chinese Atlas query retrieved `atlas-zh`, then `atlas-ms` and `atlas-en`. English WO query retrieved `wo-zh` first. Chinese scores are modest (0.466 on the ZH Atlas hit). |
| multilingual-e5-small | 1.0 | 1.0 | **Cross-lingual with higher margins.** Chinese Atlas: 0.934 on `atlas-zh`, 0.869 on `atlas-mix`. Malay Atlas query: 0.885 on `atlas-ms` then English/mix. |

The 1.0 recall on MiniLM is a **small-corpus artefact** (unique names and part numbers). The ranking pattern is the decision: MiniLM does not map “阿特拉斯什么时候发布” to the English Atlas passage. E5-small and the multilingual MiniLM do.

E5-small still pulls `dist-zh` as rank 3 for a Chinese Atlas query (0.832 vs 0.934). Script overlap is not gone; BM25 on codes remains the other half of search. This is a toy index, not MIRACL. It is enough to refuse staying on English MiniLM.

---

## Sources (primary)

- Hugging Face cards / raw README / model APIs: [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), [multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base), [bge-m3](https://huggingface.co/BAAI/bge-m3), [gte-multilingual-base](https://huggingface.co/Alibaba-NLP/gte-multilingual-base), [jina-embeddings-v3](https://huggingface.co/jinaai/jina-embeddings-v3), [thenlper/gte-base](https://huggingface.co/thenlper/gte-base), [microsoft/MiniLM-L12-H384-uncased](https://huggingface.co/microsoft/MiniLM-L12-H384-uncased), [microsoft/Multilingual-MiniLM-L12-H384](https://huggingface.co/microsoft/Multilingual-MiniLM-L12-H384), [nreimers/MiniLM-L6-H384-uncased](https://huggingface.co/nreimers/MiniLM-L6-H384-uncased)
- [Sentence-Transformers pretrained models](https://sbert.net/docs/sentence_transformer/pretrained_models.html)
- Papers: [Wang et al. 2024 mE5](https://arxiv.org/pdf/2402.05672), [Chen et al. 2024 BGE-M3](https://arxiv.org/html/2402.03216v3), [Zhang et al. 2024 mGTE](https://aclanthology.org/2024.emnlp-industry.103/), [Zhang et al. 2023 MIRACL](https://doi.org/10.1162/tacl_a_00595), [Conneau et al. 2020 XLM-R](https://aclanthology.org/2020.acl-main.747/), [Reimers & Gurevych 2019 SBERT](http://arxiv.org/abs/1908.10084), [Jina v3](https://arxiv.org/abs/2409.10173)
- OpenAI: [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings), [3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small), [3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large), [your data / residency](https://developers.openai.com/api/docs/guides/your-data), [launch blog](https://openai.com/index/new-embedding-models-and-api-updates/)
- Google: [gemini-embedding-001](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001), [embeddings](https://ai.google.dev/gemini-api/docs/embeddings), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [Vertex embeddings](https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings), [Vertex locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations), [Vertex/Agent pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
- Jina: [embeddings product](https://jina.ai/embeddings/), [GET /v1/models](https://api.jina.ai/v1/models)
- AWS: [On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/), [regions](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/)
