#!/usr/bin/env python3
"""Invented mixed-language retrieval smoke test. No customer content."""

from __future__ import annotations

import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

PASSAGES = [
    {"id": "atlas-en", "cluster": "atlas", "text": "Project Atlas launch date moved to 25 September. The Drive brief still says 18 September."},
    {"id": "atlas-zh", "cluster": "atlas", "text": "阿特拉斯项目发布改到9月25日。Drive里的brief还写着9月18日。"},
    {"id": "atlas-ms", "cluster": "atlas", "text": "Tarikh pelancaran Projek Atlas ditunda ke 25 September. Brief di Drive masih tulis 18 September."},
    {"id": "atlas-sg", "cluster": "atlas", "text": "Atlas launch confirm shift to 25 Sep liao. Brief in Drive still say 18th."},
    {"id": "atlas-mix", "cluster": "atlas", "text": "Atlas launch 改到 25 Sep already, brief in Drive still say 18th."},
    {"id": "wo-en", "cluster": "wo4412", "text": "Use drawing Rev 3 for part WO-4412. Do not machine from Rev 2."},
    {"id": "wo-zh", "cluster": "wo4412", "text": "WO-4412 的图纸用 Rev 3，不要用 Rev 2 加工。"},
    {"id": "wo-mix", "cluster": "wo4412", "text": "WO-4412 drawing 用 Rev 3, 不要用 Rev 2."},
    {"id": "sku-en", "cluster": "sku", "text": "Northline Pte Ltd price list effective 1 August: SKU-A19 is $4.80 per unit."},
    {"id": "sku-ms", "cluster": "sku", "text": "Senarai harga Northline Pte Ltd berkuat kuasa 1 Ogos: SKU-A19 ialah $4.80 seunit."},
    {"id": "dist-en", "cluster": "distractor", "text": "The office will close at 3pm on Friday for the fire drill."},
    {"id": "dist-zh", "cluster": "distractor", "text": "下周一的供应商会议改到下午两点。"},
]

QUERIES = [
    {"id": "q-atlas-en", "cluster": "atlas", "text": "When did the Atlas launch move to?"},
    {"id": "q-atlas-zh", "cluster": "atlas", "text": "阿特拉斯什么时候发布"},
    {"id": "q-atlas-ms", "cluster": "atlas", "text": "tarikh baru pelancaran Atlas"},
    {"id": "q-atlas-sg", "cluster": "atlas", "text": "Atlas launch shift to when sia"},
    {"id": "q-atlas-mix", "cluster": "atlas", "text": "Atlas launch 改到 which date"},
    {"id": "q-wo-en", "cluster": "wo4412", "text": "WO-4412 which revision is current"},
    {"id": "q-wo-zh", "cluster": "wo4412", "text": "WO-4412 用哪一版图纸"},
    {"id": "q-wo-mix", "cluster": "wo4412", "text": "WO-4412 drawing which rev"},
    {"id": "q-sku-en", "cluster": "sku", "text": "current price of SKU-A19"},
    {"id": "q-sku-ms", "cluster": "sku", "text": "harga SKU-A19 sekarang"},
]


def prefixed(texts: list[str], kind: str, needs_prefix: bool) -> list[str]:
    if not needs_prefix:
        return texts
    return [f"{kind}: {t}" for t in texts]


def retrieve(model: SentenceTransformer, queries: list[dict], passages: list[dict], needs_prefix: bool, k: int = 3):
    p_emb = model.encode(prefixed([p["text"] for p in passages], "passage", needs_prefix), normalize_embeddings=True)
    q_emb = model.encode(prefixed([q["text"] for q in queries], "query", needs_prefix), normalize_embeddings=True)
    scores = q_emb @ p_emb.T
    rows = []
    hits_at_1 = hits_at_3 = 0
    for i, query in enumerate(queries):
        ranked = sorted(range(len(passages)), key=lambda j: float(scores[i][j]), reverse=True)
        top = ranked[:k]
        top_ids = [passages[j]["id"] for j in top]
        top_clusters = [passages[j]["cluster"] for j in top]
        hit1 = top_clusters[0] == query["cluster"]
        hit3 = query["cluster"] in top_clusters
        hits_at_1 += int(hit1)
        hits_at_3 += int(hit3)
        rows.append(
            {
                "query": query["id"],
                "query_text": query["text"],
                "want": query["cluster"],
                "top": [{"id": passages[j]["id"], "cluster": passages[j]["cluster"], "score": round(float(scores[i][j]), 3)} for j in top],
                "hit@1": hit1,
                "hit@3": hit3,
            }
        )
    n = len(queries)
    return {
        "recall@1": round(hits_at_1 / n, 3),
        "recall@3": round(hits_at_3 / n, 3),
        "queries": rows,
    }


def main() -> None:
    models = [
        ("sentence-transformers/all-MiniLM-L6-v2", False, 384),
        ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", False, 384),
        ("intfloat/multilingual-e5-small", True, 384),
    ]
    out = {"passages": PASSAGES, "queries": QUERIES, "models": {}}
    for name, needs_prefix, dims in models:
        print(f"loading {name}", flush=True)
        model = SentenceTransformer(name)
        result = retrieve(model, QUERIES, PASSAGES, needs_prefix)
        result["dimensions"] = dims
        result["query_prefix"] = needs_prefix
        out["models"][name] = result
        print(name, result["recall@1"], result["recall@3"], flush=True)
        del model

    path = Path(__file__).with_name("embedding-test-results.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
