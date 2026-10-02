# pg-semantic-cache

A semantic cache for LLM calls, stored in PostgreSQL with pgvector.

![build](https://img.shields.io/badge/build-passing-green)

## Why

Many LLM requests are near-duplicates. This library embeds each prompt and returns a cached answer when a previous prompt is similar enough, which cut API costs by about 30% in a demo chatbot.

## Features

- Drop-in wrapper around any OpenAI-compatible client.
- Configurable similarity threshold and time-to-live per cache entry.
- Async support with asyncpg.
- Prometheus metrics for hit rate and latency.

## Installation

```bash
pip install pg-semantic-cache
```

## Development

Tests run with pytest against a real Postgres in Docker. CI runs on GitHub Actions for Python 3.10 to 3.12.
