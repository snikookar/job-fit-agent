# Support Copilot

Side project, 2024. An LLM agent that drafts replies to customer support tickets.

## What it does

- Classifies incoming tickets into 14 categories with a fine-tuned DistilBERT model (macro F1 0.91).
- Retrieves similar resolved tickets with hybrid search (BM25 + dense embeddings) and reciprocal rank fusion.
- Drafts a reply with an LLM and cites the tickets it used, so agents can check the source.

## Stack

Python, LangGraph, FastAPI, PostgreSQL with pgvector, sentence-transformers, Docker Compose.

## Results

- Evaluated on 500 historical tickets: 68% of drafts were accepted with minor edits by support agents in a two-week pilot.
- Added a human approval step before any reply is sent, implemented with LangGraph interrupts.
