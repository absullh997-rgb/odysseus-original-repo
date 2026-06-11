#!/usr/bin/env python3
"""
github_research_worker.py
=========================
Runs inside GitHub Actions to offload deep-research jobs from Hugging Face Spaces.
Reads RESEARCH_QUERY, SESSION_ID, CALLBACK_URL from environment variables.
Uses free LLM APIs (Groq, Cerebras, HF Router) for summarization.
Posts results back to the HF Space callback URL if provided.
"""

import asyncio
import json
import os
import pathlib
import sys
import time

import httpx

# ──────────────────────────────────────────────────────────────────────────────
# Configuration from environment
# ──────────────────────────────────────────────────────────────────────────────
RESEARCH_QUERY = os.getenv("RESEARCH_QUERY", "")
SESSION_ID = os.getenv("SESSION_ID", f"gh_{int(time.time())}")
CALLBACK_URL = os.getenv("CALLBACK_URL", "")

# Free LLM API keys (set as GitHub Secrets)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

OUTPUT_DIR = pathlib.Path("research_output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# LLM Summarization via Groq (free, ultra-fast)
# ──────────────────────────────────────────────────────────────────────────────
def call_groq(prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    """Call Groq free API for text generation."""
    if not GROQ_API_KEY:
        return "[Groq API key not set]"
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Groq error: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# Web Search via Serper (free tier) or Tavily
# ──────────────────────────────────────────────────────────────────────────────
def web_search(query: str, num_results: int = 5) -> list[dict]:
    """Search the web using Serper or Tavily API."""
    results = []

    # Try Serper first
    if SERPER_API_KEY:
        try:
            r = httpx.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": num_results},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
        except Exception as e:
            print(f"Serper error: {e}", file=sys.stderr)

    # Fallback to Tavily
    if TAVILY_API_KEY:
        try:
            r = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "max_results": num_results,
                    "search_depth": "basic",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            for item in data.get("results", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                })
            return results
        except Exception as e:
            print(f"Tavily error: {e}", file=sys.stderr)

    # Fallback: DuckDuckGo HTML scraping (no API key needed)
    try:
        r = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; OdysseusResearch/1.0)"},
            timeout=15,
            follow_redirects=True,
        )
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for result in soup.select(".result")[:num_results]:
            title_el = result.select_one(".result__title")
            url_el = result.select_one(".result__url")
            snippet_el = result.select_one(".result__snippet")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": url_el.get_text(strip=True) if url_el else "",
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
        return results
    except Exception as e:
        print(f"DuckDuckGo fallback error: {e}", file=sys.stderr)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Main research pipeline
# ──────────────────────────────────────────────────────────────────────────────
def run_research(query: str) -> dict:
    """Execute a full deep research pipeline."""
    print(f"🔍 Starting research for: {query}", flush=True)
    start = time.time()

    # Step 1: Web search
    print("📡 Searching the web...", flush=True)
    search_results = web_search(query, num_results=8)
    print(f"   Found {len(search_results)} results", flush=True)

    # Step 2: Build context from search results
    context_parts = []
    for i, r in enumerate(search_results, 1):
        context_parts.append(
            f"[Source {i}] {r['title']}\nURL: {r['url']}\n{r['snippet']}\n"
        )
    context = "\n---\n".join(context_parts)

    # Step 3: LLM synthesis
    print("🤖 Synthesizing with LLM...", flush=True)
    synthesis_prompt = f"""You are a research assistant. Based on the following web search results, 
provide a comprehensive, well-structured research report on the topic: "{query}"

Search Results:
{context}

Instructions:
- Write a detailed report with clear sections
- Cite sources by their [Source N] numbers
- Be factual and objective
- Include a summary at the beginning
- Format in Markdown

Research Report:"""

    report = call_groq(synthesis_prompt)

    elapsed = round(time.time() - start, 2)
    print(f"✅ Research completed in {elapsed}s", flush=True)

    return {
        "query": query,
        "session_id": SESSION_ID,
        "report": report,
        "sources": search_results,
        "elapsed_seconds": elapsed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Post results back to HF Space
# ──────────────────────────────────────────────────────────────────────────────
def post_callback(result: dict) -> None:
    """POST research results back to the HF Space callback URL."""
    if not CALLBACK_URL:
        print("ℹ️  No callback URL set, skipping POST.", flush=True)
        return
    try:
        r = httpx.post(
            CALLBACK_URL,
            json=result,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if r.is_success:
            print(f"✅ Results posted to callback: {CALLBACK_URL}", flush=True)
        else:
            print(f"⚠️  Callback returned {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"❌ Callback error: {e}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not RESEARCH_QUERY:
        print("❌ RESEARCH_QUERY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    result = run_research(RESEARCH_QUERY)

    # Save to file
    output_file = OUTPUT_DIR / f"research_{SESSION_ID}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"💾 Results saved to: {output_file}", flush=True)

    # Save markdown report
    md_file = OUTPUT_DIR / f"research_{SESSION_ID}.md"
    md_content = f"# Research Report\n\n**Query:** {result['query']}\n\n**Date:** {result['timestamp']}\n\n---\n\n{result['report']}\n\n---\n\n## Sources\n\n"
    for i, src in enumerate(result["sources"], 1):
        md_content += f"{i}. [{src['title']}]({src['url']})\n"
    md_file.write_text(md_content, encoding="utf-8")
    print(f"📄 Markdown report saved to: {md_file}", flush=True)

    # Post callback
    post_callback(result)

    print("🎉 Research worker finished successfully!", flush=True)
