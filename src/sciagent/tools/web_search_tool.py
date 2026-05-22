from __future__ import annotations

import os
import requests
from smolagents import Tool


class WebSearchTool(Tool):
    name = "web_search"
    description = """Search scientific literature and knowledge bases for ground truth facts.

    Args:
        query: Search query (e.g., "beer foam stability long chain fatty acids")

    Returns:
        str: Search results with relevant scientific facts
    """
    inputs = {"query": {"type": "string", "description": "The search query for scientific facts"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        """Search using Perplexity API (fallback to Tavily/Semantic Scholar)."""
        # Try Perplexity first (best for scientific reasoning)
        perplexity_key = os.environ.get("PERPLEXITY_API_KEY")
        if perplexity_key:
            return self._search_perplexity(query, perplexity_key)

        # Fallback to Tavily (good for general web search)
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            result = self._search_tavily(query, tavily_key)
            if result and "[Error" not in result:
                return result

        # Final fallback to Semantic Scholar
        return self._search_semantic_scholar(query)

    def _search_perplexity(self, query: str, api_key: str) -> str:
        """Search using Perplexity API."""
        try:
            response = requests.post("https://api.perplexity.ai/chat/completions",
                                     headers={"Authorization": f"Bearer {api_key}"},
                                     json={
                                         "model": "llama-3.1-sonar-small-128k-online",
                                         "messages": [{
                                             "role": "user",
                                             "content": f"Scientific fact check: {query}"
                                         }],
                                         "max_tokens": 500
                                     },
                                     timeout=30)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            return f"[Perplexity Error: {response.status_code}]"
        except Exception as e:
            return f"[Perplexity Error: {str(e)}]"

    def _search_tavily(self, query: str, api_key: str) -> str:
        """Search using Tavily API (good for general web + scientific content)."""
        try:
            response = requests.post("https://api.tavily.com/search",
                                     headers={"Content-Type": "application/json"},
                                     json={
                                         "api_key": api_key,
                                         "query": query,
                                         "max_results": 3
                                     },
                                     timeout=15)
            if response.status_code == 200:
                data = response.json()
                results = []
                for r in data.get("results", []):
                    title = str(r.get('title', ''))
                    content = str(r.get('content', ''))[:300]
                    url = str(r.get('url', ''))
                    results.append(f"{title}: {content}\nSource: {url}")
                result_str = "\n\n".join(results) if results else "[No results found]"
                return str(result_str)
            return f"[Tavily Error: {response.status_code}]"
        except Exception as e:
            return f"[Tavily Error: {str(e)}]"

    def _search_semantic_scholar(self, query: str) -> str:
        """Search using Semantic Scholar API (free, no key required)."""
        try:
            response = requests.get("https://api.semanticscholar.org/graph/v1/paper/search",
                                    params={
                                        "query": query,
                                        "limit": 3,
                                        "fields": "title,abstract,year"
                                    },
                                    timeout=30)
            if response.status_code == 200:
                papers = response.json().get("data", [])
                results = []
                for p in papers:
                    results.append(f"[{p.get('year')}] {p.get('title')}: {p.get('abstract', 'N/A')[:200]}")
                return "\n\n".join(results) if results else "[No results found]"
            return f"[Semantic Scholar Error: {response.status_code}]"
        except Exception as e:
            return f"[Semantic Scholar Error: {str(e)}]"
