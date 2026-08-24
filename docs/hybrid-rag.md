# Step 20: Hybrid RAG Retrieval

## Purpose

The original retriever used sparse token overlap and a small source-name boost. It was deterministic, but it did not expose stable Chunk IDs, BM25 scores, fusion details, or retrieval metrics.

Step 20 adds an offline, reproducible retrieval stack without external APIs:

```text
Markdown documents
-> standard DocumentChunk
-> Legacy top 20 + BM25 top 20
-> Reciprocal Rank Fusion (RRF, k=60)
-> deterministic domain reranker
-> final top 3 or top 5
-> Evidence and Citation
```

## Standard Chunk

Each chunk contains:

```text
chunk_id, document_id, source, title, section,
content, version, metadata
```

Chunk IDs are deterministic, for example `software_manual:tcpdump` and `release_note:release-1214`. RAG Evidence now uses the Chunk ID as `source_id`.

## Retrieval Modes

`DocumentRetriever` supports `legacy`, `bm25`, and `hybrid`.

```python
DocumentRetriever(mode="hybrid").retrieve("抓包工具", top_k=3)
RAGRetrieverTool(mode="hybrid").run("抓包工具")
```

The runtime default remains `legacy` to protect the Step 17 response baseline. Enable Hybrid for an Agent/API deployment before startup:

```powershell
$env:SOFTWARE_AGENT_RAG_MODE = "hybrid"
uvicorn app.api.server:app --reload
```

The output preserves `source`, `title`, `content`, `score`, and `matched_terms`, and adds Chunk metadata plus a `scores` breakdown for legacy, BM25, RRF, reranker, and final scores.

## Deterministic Reranking

The reranker uses auditable domain features:

- exact package match
- exact release match
- title overlap
- source intent (`manual` or `release note`)
- section overlap

Chinese engineering aliases such as `抓包`, `安全通信`, `网口`, and `管理面` are expanded into English domain terms before BM25 retrieval.

## Evaluation

`evaluation/rag_cases.json` contains 30 labeled cases: 24 answerable and 6 no-answer cases. It covers English, Chinese aliases, noisy queries, source/version filters, conflicts, empty input, and out-of-domain questions.

Run:

```bash
python -B evaluation/eval_runner.py --suite rag
```

| Mode | Recall@3 | Recall@5 | MRR | No-answer | Citation |
|---|---:|---:|---:|---:|---:|
| Legacy | 83.33% | 83.33% | 79.17% | 100% | 100% |
| BM25 | 100% | 100% | 95.83% | 100% | 100% |
| Hybrid | 100% | 100% | 95.83% | 100% | 100% |

Hybrid has no core-metric regression against Legacy and passes all Step 20 thresholds. These figures describe the current small simulated corpus and should not be generalized to production data.

## Files

- `app/rag/chunker.py`: stable Chunk schema and Markdown chunking
- `app/rag/bm25.py`: weighted BM25
- `app/rag/hybrid.py`: RRF fusion
- `app/rag/reranker.py`: deterministic reranking
- `app/rag/retriever.py`: mode selection and compatible output
- `evaluation/rag_eval.py`: Recall/MRR/no-answer/Citation metrics
- `tests/test_hybrid_rag.py`: normal, boundary, filter, and regression tests
