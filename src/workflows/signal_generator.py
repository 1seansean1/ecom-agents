"""Signal Generator Workflow — cheap, high-volume signal for epsilon tuning.

Runs every 2 hours. For each Shopify product:
1. Fetch current description
2. Score it (readability, keywords, structure)
3. Generate 3 variant descriptions using GPT-4o-mini (cheap)
4. Score all variants
5. Pick the winner
6. If winner beats current by >10 points, update Shopify (Tier 1 auto)
7. Log all scores as APS eval results for epsilon monitoring

This produces dense, measurable signal that the morphogenetic system
can use for epsilon tuning practice.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def run_signal_generator() -> dict:
    """Execute the signal generator workflow.

    Returns summary dict with scores, updates applied, and eval results.
    """
    results = {
        "products_analyzed": 0,
        "variants_generated": 0,
        "descriptions_updated": 0,
        "eval_results": [],
        "errors": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Step 1: Fetch products
        products = _fetch_products()
        if not products:
            results["errors"].append("No products found in Shopify")
            return results
        results["products_analyzed"] = len(products)

        # Step 2: Process each product
        for product in products:
            try:
                product_result = _process_product(product)
                results["variants_generated"] += product_result.get("variants_generated", 0)
                if product_result.get("updated"):
                    results["descriptions_updated"] += 1
                results["eval_results"].append(product_result)
            except Exception as e:
                logger.error("Signal generator error for product %s: %s",
                             product.get("title", "?"), e)
                results["errors"].append(f"{product.get('title', '?')}: {e}")

        # Step 3: Store eval results in APS
        _store_eval_results(results)

    except Exception as e:
        logger.exception("Signal generator workflow failed")
        results["errors"].append(str(e))

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Signal generator complete: %d products, %d variants, %d updates",
                results["products_analyzed"], results["variants_generated"],
                results["descriptions_updated"])
    return results


def _fetch_products() -> list[dict]:
    """Fetch products from Shopify with descriptions."""
    try:
        from src.tools.shopify_content import fetch_products_with_descriptions
        result = fetch_products_with_descriptions.invoke({"limit": 10})
        return result.get("products", [])
    except Exception as e:
        logger.error("Failed to fetch products: %s", e)
        return []


def _process_product(product: dict) -> dict:
    """Analyze and optimize a single product's description."""
    from src.tools.shopify_content import score_description

    title = product.get("title", "Unknown")
    current_desc = product.get("description_html", "")
    product_id = product.get("id", "")
    price = product.get("price", "0.00")

    # Score current description
    current_score = score_description(current_desc)

    result = {
        "product_id": product_id,
        "title": title,
        "current_score": current_score["composite"],
        "variants_generated": 0,
        "best_variant_score": current_score["composite"],
        "updated": False,
        "improvement": 0,
    }

    # Generate variant descriptions via GPT-4o-mini
    variants = _generate_variants(title, current_desc, price)
    result["variants_generated"] = len(variants)

    # Score all variants
    best_variant = None
    best_score = current_score["composite"]

    for variant in variants:
        vscore = score_description(variant)
        if vscore["composite"] > best_score:
            best_score = vscore["composite"]
            best_variant = variant

    result["best_variant_score"] = best_score
    result["improvement"] = round(best_score - current_score["composite"], 1)

    # Update if improvement > 10 points
    if best_variant and result["improvement"] > 10:
        try:
            from src.tools.shopify_content import update_product_description
            update_result = update_product_description.invoke({
                "product_id": product_id,
                "description_html": best_variant,
            })
            if update_result.get("description_updated"):
                result["updated"] = True
                logger.info("Updated description for '%s': %.1f → %.1f (+%.1f)",
                            title, current_score["composite"], best_score,
                            result["improvement"])
        except Exception as e:
            logger.warning("Failed to update description for '%s': %s", title, e)

    return result


def _generate_variants(title: str, current_desc: str, price: str) -> list[str]:
    """Generate 3 variant descriptions using GPT-4o-mini."""
    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        prompt = (
            f"You are an e-commerce copywriter. Generate 3 different product descriptions "
            f"for this product:\n\n"
            f"Title: {title}\n"
            f"Price: ${price}\n"
            f"Current description: {current_desc[:500]}\n\n"
            f"Requirements for each variant:\n"
            f"- 50-150 words\n"
            f"- Include HTML formatting (<p>, <strong>, <ul>/<li>)\n"
            f"- Use keywords: quality, premium, handcrafted, unique, perfect, gift\n"
            f"- Different tone per variant: 1) Luxury/aspirational 2) Practical/benefit-focused 3) Story-driven/emotional\n\n"
            f"Return ONLY a JSON array of 3 strings (the HTML descriptions). No markdown fences."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()
        # Parse JSON array
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        variants = json.loads(content)
        if isinstance(variants, list):
            return [str(v) for v in variants[:3]]
        return []

    except Exception as e:
        logger.warning("Failed to generate variants: %s", e)
        return []


def _store_eval_results(results: dict) -> None:
    """Store signal generator results as APS eval entries."""
    try:
        from src.aps.store import store_eval_result

        suite_id = f"signal_gen_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"

        for i, product_result in enumerate(results.get("eval_results", [])):
            store_eval_result(
                suite_id=suite_id,
                task_id=f"product_{i}_{product_result.get('title', 'unknown')[:30]}",
                passed=product_result.get("improvement", 0) >= 0,
                score=product_result.get("best_variant_score", 0) / 100.0,
                latency_ms=0,
                cost_usd=0.002 * product_result.get("variants_generated", 0),  # ~$0.002 per GPT-4o-mini call
                output_preview=json.dumps({
                    "current": product_result.get("current_score", 0),
                    "best": product_result.get("best_variant_score", 0),
                    "updated": product_result.get("updated", False),
                })[:500],
            )

        logger.info("Stored %d eval results for suite %s",
                     len(results.get("eval_results", [])), suite_id)
    except Exception as e:
        logger.warning("Failed to store eval results: %s", e)
