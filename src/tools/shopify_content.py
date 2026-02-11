"""Shopify content analysis and generation tools.

Used by the Signal Generator workflow to A/B test product descriptions.
Scores descriptions on readability, keyword density, and structure.
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Scoring helpers ──────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len(text.split())


def _sentence_count(text: str) -> int:
    return max(1, len(re.split(r'[.!?]+', text.strip())) - 1 or 1)


def _avg_sentence_length(text: str) -> float:
    return _word_count(text) / _sentence_count(text)


def _flesch_reading_ease(text: str) -> float:
    """Simplified Flesch score (0-100, higher = easier to read)."""
    words = _word_count(text)
    sentences = _sentence_count(text)
    # Rough syllable count: count vowel groups
    syllables = len(re.findall(r'[aeiouyAEIOUY]+', text))
    if words == 0 or sentences == 0:
        return 0.0
    return max(0, min(100, 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)))


def _keyword_density(text: str, keywords: list[str]) -> float:
    """Fraction of words that are keywords (0.0-1.0)."""
    words = text.lower().split()
    if not words:
        return 0.0
    kw_set = {k.lower() for k in keywords}
    matches = sum(1 for w in words if w.strip(".,!?;:\"'()") in kw_set)
    return matches / len(words)


def _has_html_structure(text: str) -> bool:
    """Check if description has HTML formatting (paragraphs, lists, bold)."""
    return bool(re.search(r'<(p|ul|ol|li|strong|em|h[1-6])\b', text, re.IGNORECASE))


def score_description(text: str, keywords: list[str] | None = None) -> dict:
    """Score a product description on multiple dimensions.

    Returns dict with individual scores (0-1) and composite score (0-100).
    """
    if not text or not text.strip():
        return {
            "readability": 0, "length": 0, "keyword_density": 0,
            "structure": 0, "composite": 0, "word_count": 0,
        }

    kw = keywords or ["quality", "premium", "handcrafted", "unique", "perfect", "gift"]
    words = _word_count(text)

    # Readability (0-1): Flesch normalized
    flesch = _flesch_reading_ease(text)
    readability = flesch / 100.0

    # Length score (0-1): Sweet spot is 50-150 words
    if words < 20:
        length_score = words / 20.0
    elif words <= 150:
        length_score = 1.0
    elif words <= 300:
        length_score = 1.0 - (words - 150) / 300.0
    else:
        length_score = 0.3

    # Keyword density (0-1): Target 2-5%
    kd = _keyword_density(text, kw)
    if kd < 0.01:
        kd_score = kd / 0.01
    elif kd <= 0.05:
        kd_score = 1.0
    elif kd <= 0.10:
        kd_score = 1.0 - (kd - 0.05) / 0.10
    else:
        kd_score = 0.2  # Keyword stuffing

    # Structure (0-1): HTML formatting bonus
    structure_score = 0.6
    if _has_html_structure(text):
        structure_score = 1.0
    if _sentence_count(text) >= 3:
        structure_score = min(1.0, structure_score + 0.2)

    # Composite (0-100)
    composite = (readability * 30 + length_score * 30 + kd_score * 20 + structure_score * 20)

    return {
        "readability": round(readability, 3),
        "length": round(length_score, 3),
        "keyword_density": round(kd_score, 3),
        "structure": round(structure_score, 3),
        "composite": round(composite, 1),
        "word_count": words,
        "flesch": round(flesch, 1),
        "kd_pct": round(kd * 100, 2),
    }


# ── LangChain Tools ─────────────────────────────────────────────────────

class FetchProductsWithDescInput(BaseModel):
    limit: int = Field(default=10, description="Number of products to fetch")


@tool(args_schema=FetchProductsWithDescInput)
def fetch_products_with_descriptions(limit: int = 10) -> dict:
    """Fetch Shopify products with their full descriptions for content analysis."""
    from src.tools.shopify_tool import _graphql_request

    query = """
    query ($limit: Int!) {
      products(first: $limit) {
        edges {
          node {
            id
            title
            descriptionHtml
            status
            totalInventory
            onlineStoreUrl
            variants(first: 1) {
              edges {
                node {
                  price
                }
              }
            }
          }
        }
      }
    }
    """
    result = _graphql_request(query, {"limit": limit})
    products = result.get("data", {}).get("products", {}).get("edges", [])

    return {
        "count": len(products),
        "products": [
            {
                "id": p["node"]["id"],
                "title": p["node"]["title"],
                "description_html": p["node"].get("descriptionHtml", ""),
                "status": p["node"]["status"],
                "inventory": p["node"]["totalInventory"],
                "url": p["node"].get("onlineStoreUrl", ""),
                "price": (p["node"]["variants"]["edges"][0]["node"]["price"]
                          if p["node"]["variants"]["edges"] else "0.00"),
            }
            for p in products
        ],
    }


class ScoreDescriptionInput(BaseModel):
    description: str = Field(description="Product description to score")
    keywords: list[str] = Field(
        default=["quality", "premium", "handcrafted", "unique", "perfect", "gift"],
        description="Target keywords for density scoring",
    )


@tool(args_schema=ScoreDescriptionInput)
def score_product_description(
    description: str,
    keywords: list[str] | None = None,
) -> dict:
    """Score a product description on readability, length, keyword density, and structure."""
    return score_description(description, keywords)


class UpdateDescriptionInput(BaseModel):
    product_id: str = Field(description="Shopify product GID (gid://shopify/Product/...)")
    description_html: str = Field(description="New description HTML")


@tool(args_schema=UpdateDescriptionInput)
def update_product_description(product_id: str, description_html: str) -> dict:
    """Update a product's description in Shopify."""
    from src.tools.shopify_tool import _graphql_request

    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          title
          descriptionHtml
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "id": product_id,
            "descriptionHtml": description_html,
        }
    }
    result = _graphql_request(mutation, variables)
    data = result.get("data", {}).get("productUpdate", {})
    errors = data.get("userErrors", [])

    if errors:
        return {"error": errors[0]["message"], "field": errors[0]["field"]}

    product = data.get("product", {})
    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "description_updated": True,
    }


def get_shopify_content_tools() -> list:
    """Return all Shopify content tools."""
    return [fetch_products_with_descriptions, score_product_description, update_product_description]
