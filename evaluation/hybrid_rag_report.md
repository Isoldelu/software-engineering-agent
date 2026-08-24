# Hybrid RAG Evaluation Report

## Setup

- Corpus: 2 simulated Markdown documents, 6 standard chunks
- Cases: 30 total, including 24 answerable and 6 no-answer cases
- Compared methods: Legacy overlap, weighted BM25, BM25/Legacy RRF plus deterministic reranker
- External API: none

## Results

| Method | Recall@3 | Recall@5 | MRR | No-answer Accuracy | Citation Correctness |
|---|---:|---:|---:|---:|---:|
| Legacy | 83.33% | 83.33% | 79.17% | 100% | 100% |
| BM25 | 100% | 100% | 95.83% | 100% | 100% |
| Hybrid | 100% | 100% | 95.83% | 100% | 100% |

## Findings

- Legacy missed four Chinese or mixed-language queries.
- Query expansion recovered `openssl`, `ethtool`, `nginx`, and `tcpdump` domain intents.
- Deterministic reranking moved the software manual above the release note for the ambiguous management-plane query.
- Version and source filters are applied before ranking.
- All six no-answer cases returned an empty result instead of weak unrelated evidence.
- Hybrid did not regress any measured core metric against Legacy.

## Acceptance

All thresholds passed: Recall@3 >= 90%, Recall@5 >= 95%, MRR >= 0.85, Citation correctness >= 95%, no-answer accuracy >= 90%, and no core regression against Legacy.
