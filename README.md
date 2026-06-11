---
title: Odysseus AI
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Odysseus AI — Distributed Architecture

> **An open-source AI assistant with distributed inference across free platforms.**
> Runs on Hugging Face Spaces (16GB RAM) by routing heavy LLM inference to free external APIs.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                USER BROWSER                     │
└──────────────────┬──────────────────────────────┘
                   │ HTTPS
┌──────────────────▼──────────────────────────────┐
│    HUGGING FACE SPACES (16GB RAM - Free Tier)   │
│  FastAPI + HTML/JS UI (app.py)                  │
│  ├── Auth & Session Management                  │
│  ├── Chat Interface                             │
│  ├── Notes / Calendar / Email / Tasks           │
│  ├── MCP Server Manager                         │
│  └── Multi-Provider LLM Router                 │
└──────────┬──────────────────────────────────────┘
           │
    ┌──────┴────────────────────────────────────┐
    │     EXTERNAL FREE APIs (No RAM cost)      │
    │                                           │
    │  Groq (30 RPM)   Cerebras (30 RPM)        │
    │  GitHub Models   HF Router (100K/mo)      │
    │  Cloudflare AI   OpenRouter (free models) │
    └──────┬────────────────────────────────────┘
           │
    ┌──────┴────────────────────────────────────┐
    │   GITHUB ACTIONS (Heavy Tasks Offload)    │
    │  Deep Research Worker (7GB, 30min/job)    │
    │  CI/CD Pipeline + Auto-sync to HF Spaces  │
    └───────────────────────────────────────────┘
```

## Why This Architecture?

| Problem | Solution |
|---------|----------|
| HF Spaces free tier: **16GB RAM only** | Route LLM inference to free external APIs |
| Running local models needs **230GB+ RAM** | Use Groq/Cerebras (free, ultra-fast) |
| Deep Research jobs are memory-intensive | Offload to GitHub Actions (7GB, free) |
| ChromaDB needs significant RAM | Use SQLite-based vector storage |
| Scheduled tasks consume background RAM | Offload to GitHub Actions workflows |

## Quick Start

### 1. Fork & Deploy to Hugging Face

1. Fork this repository on GitHub
2. Create a new Space on Hugging Face (Docker SDK, port 7860)
3. Add the following **Secrets** in your HF Space settings:

| Secret | Description | Required |
|--------|-------------|----------|
| `GROQ_API_KEY` | [Groq free API key](https://console.groq.com/keys) | Recommended |
| `CEREBRAS_API_KEY` | [Cerebras free API key](https://cloud.cerebras.ai/) | Optional |
| `GITHUB_TOKEN` | GitHub PAT for research offloading | Optional |
| `HF_TOKEN` | Hugging Face token for HF Router | Optional |
| `OPENAI_API_KEY` | OpenAI API key (paid) | Optional |
| `TAVILY_API_KEY` | Tavily search API key | Optional |
| `SERPER_API_KEY` | Serper search API key | Optional |

4. Set `GITHUB_REPO` to `your-username/odysseus-original-repo` for research offloading.

### 2. Local Development

```bash
git clone https://github.com/absullh997-rgb/odysseus-original-repo.git
cd odysseus-original-repo
cp .env.example .env
# Edit .env and add your API keys
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860 --reload
```

### 3. Docker (Full Stack with Local LLM)

For local deployment with full hardware (GPU/high RAM):

```bash
docker compose up -d
```

## Free API Keys Setup

### Groq (Recommended — Fastest)
1. Sign up at [console.groq.com](https://console.groq.com)
2. Create an API key (free, no credit card)
3. Add as `GROQ_API_KEY` in HF Space secrets

### Cerebras (Ultra-fast alternative)
1. Sign up at [cloud.cerebras.ai](https://cloud.cerebras.ai)
2. Create an API key (free tier: 1M tokens/day)
3. Add as `CEREBRAS_API_KEY`

### GitHub Models (Free with GitHub account)
1. Go to [github.com/marketplace/models](https://github.com/marketplace/models)
2. Generate a token with `models:read` scope
3. Add as `GITHUB_TOKEN`

## Features

- **Multi-Provider LLM Routing** — Automatically routes to the best available free API
- **Deep Research** — Offloads to GitHub Actions for memory-intensive research jobs
- **Memory & RAG** — Semantic memory with lightweight SQLite vector storage
- **MCP Integration** — Model Context Protocol servers for extended capabilities
- **Email, Calendar, Tasks** — Full productivity suite
- **Image Generation** — Via OpenAI-compatible image APIs
- **Shell Access** — Secure sandboxed shell execution
- **Voice (STT/TTS)** — Speech-to-text and text-to-speech

## Resource Usage (HF Free Tier)

| Component | RAM Usage |
|-----------|-----------|
| FastAPI + UI | ~200MB |
| SQLite + Sessions | ~100MB |
| FastEmbed (embeddings) | ~300MB |
| MCP Servers | ~200MB |
| **Total** | **~800MB** (well within 16GB) |

## License

GNU Affero General Public License v3.0 (AGPL-3.0)
