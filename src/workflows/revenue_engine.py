"""Revenue Engine Workflow — SEO optimization + content marketing pipeline.

Runs daily at 8am. Strategy:
1. Analyze all Shopify products for SEO weaknesses
2. Generate SEO-optimized titles and meta descriptions
3. Create social media content to drive traffic
4. Track improvements via Stripe revenue data
5. Log metrics for morphogenetic evaluation

Revenue comes from: better product discovery (SEO) → more traffic →
more conversions → more Stripe charges. Measurable via financial_health.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def run_revenue_engine() -> dict:
    """Execute the revenue engine workflow.

    Returns summary of SEO improvements, content generated, and metrics.
    """
    results = {
        "products_analyzed": 0,
        "seo_improvements": 0,
        "social_posts_generated": 0,
        "email_campaigns_drafted": 0,
        "eval_results": [],
        "errors": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Phase 1: SEO Audit
        products = _fetch_products_for_seo()
        results["products_analyzed"] = len(products)

        seo_issues = []
        for product in products:
            issues = _audit_product_seo(product)
            if issues:
                seo_issues.append({"product": product, "issues": issues})

        # Phase 2: Fix SEO issues (auto-apply safe changes)
        for item in seo_issues:
            try:
                fixed = _fix_seo_issues(item["product"], item["issues"])
                if fixed:
                    results["seo_improvements"] += 1
                    results["eval_results"].append({
                        "title": item["product"].get("title", "?"),
                        "issues_found": len(item["issues"]),
                        "fixed": fixed,
                    })
            except Exception as e:
                results["errors"].append(f"SEO fix error: {e}")

        # Phase 3: Generate social media content
        try:
            posts = _generate_social_content(products[:3])  # Top 3 products
            results["social_posts_generated"] = len(posts)
        except Exception as e:
            results["errors"].append(f"Social content error: {e}")

        # Phase 4: Draft re-engagement email
        try:
            email_drafted = _draft_reengagement_email(products)
            if email_drafted:
                results["email_campaigns_drafted"] = 1
        except Exception as e:
            results["errors"].append(f"Email draft error: {e}")

        # Phase 5: Store eval results
        _store_revenue_evals(results)

    except Exception as e:
        logger.exception("Revenue engine workflow failed")
        results["errors"].append(str(e))

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Revenue engine complete: %d analyzed, %d SEO fixes, %d posts, %d emails",
                results["products_analyzed"], results["seo_improvements"],
                results["social_posts_generated"], results["email_campaigns_drafted"])
    return results


def _fetch_products_for_seo() -> list[dict]:
    """Fetch products with SEO-relevant data."""
    try:
        from src.tools.shopify_content import fetch_products_with_descriptions
        result = fetch_products_with_descriptions.invoke({"limit": 20})
        return result.get("products", [])
    except Exception as e:
        logger.error("Failed to fetch products for SEO: %s", e)
        return []


def _audit_product_seo(product: dict) -> list[str]:
    """Audit a product for SEO issues. Returns list of issue descriptions."""
    issues = []
    title = product.get("title", "")
    desc = product.get("description_html", "")

    # Title length (ideal: 50-60 chars for search results)
    if len(title) < 20:
        issues.append(f"Title too short ({len(title)} chars, target 50-60)")
    elif len(title) > 70:
        issues.append(f"Title too long ({len(title)} chars, target 50-60)")

    # Description length (ideal: 100-300 words)
    word_count = len(desc.split())
    if word_count < 30:
        issues.append(f"Description too thin ({word_count} words, need 100+)")
    elif word_count < 100:
        issues.append(f"Description could be richer ({word_count} words, target 100-300)")

    # Missing HTML structure
    import re
    if not re.search(r'<(p|ul|ol|strong|h[2-4])\b', desc, re.IGNORECASE):
        issues.append("No HTML structure (missing <p>, <ul>, <strong> tags)")

    # Missing key e-commerce terms
    desc_lower = desc.lower()
    missing_terms = []
    for term in ["free shipping", "satisfaction", "quality", "handcrafted"]:
        if term not in desc_lower:
            missing_terms.append(term)
    if missing_terms:
        issues.append(f"Missing conversion keywords: {', '.join(missing_terms[:3])}")

    # No call to action
    cta_patterns = ["buy now", "add to cart", "shop now", "order", "get yours"]
    if not any(cta in desc_lower for cta in cta_patterns):
        issues.append("No call-to-action in description")

    return issues


def _fix_seo_issues(product: dict, issues: list[str]) -> bool:
    """Fix SEO issues using GPT-4o-mini. Returns True if updated."""
    title = product.get("title", "")
    desc = product.get("description_html", "")
    product_id = product.get("id", "")
    price = product.get("price", "0.00")

    if not product_id or not issues:
        return False

    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        prompt = (
            f"You are an e-commerce SEO specialist. Fix these SEO issues for a product listing:\n\n"
            f"Product: {title}\n"
            f"Price: ${price}\n"
            f"Current Description:\n{desc[:1000]}\n\n"
            f"Issues to fix:\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
            f"Return ONLY the improved description HTML. Keep the same style but fix the issues. "
            f"Include <p>, <strong>, <ul>/<li> tags. Add missing keywords naturally. "
            f"100-200 words. Include a subtle call-to-action."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1000,
        )

        new_desc = response.choices[0].message.content.strip()
        # Remove markdown fences if present
        if new_desc.startswith("```"):
            lines = new_desc.split("\n")
            new_desc = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        # Apply the update
        from src.tools.shopify_content import update_product_description
        result = update_product_description.invoke({
            "product_id": product_id,
            "description_html": new_desc,
        })
        return result.get("description_updated", False)

    except Exception as e:
        logger.warning("Failed to fix SEO for '%s': %s", title, e)
        return False


def _generate_social_content(products: list[dict]) -> list[dict]:
    """Generate social media posts for products."""
    if not products:
        return []

    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        product_list = "\n".join(
            f"- {p.get('title', '?')} (${p.get('price', '0')}): {p.get('description_html', '')[:200]}"
            for p in products
        )

        prompt = (
            f"You are a social media manager for an e-commerce store. "
            f"Generate 1 Instagram caption for each product:\n\n{product_list}\n\n"
            f"Requirements:\n"
            f"- 2-3 sentences, engaging and on-brand\n"
            f"- Include relevant hashtags (5-8)\n"
            f"- Include a call-to-action (link in bio, shop now, etc.)\n\n"
            f"Return JSON array of objects: [{{\"product\": \"title\", \"caption\": \"text\"}}]"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        posts = json.loads(content)
        if isinstance(posts, list):
            logger.info("Generated %d social media posts", len(posts))
            return posts
        return []

    except Exception as e:
        logger.warning("Failed to generate social content: %s", e)
        return []


def _draft_reengagement_email(products: list[dict]) -> bool:
    """Draft a customer re-engagement email highlighting products."""
    if not products:
        return False

    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        top_products = products[:3]
        product_list = "\n".join(
            f"- {p.get('title', '?')} (${p.get('price', '0')})"
            for p in top_products
        )

        prompt = (
            f"Write a short re-engagement email for customers who haven't visited "
            f"our store recently. Feature these products:\n\n{product_list}\n\n"
            f"Requirements:\n"
            f"- Subject line + body\n"
            f"- Friendly, not pushy\n"
            f"- Mention free shipping if applicable\n"
            f"- Include a clear CTA\n"
            f"- Under 150 words for the body\n\n"
            f"Return JSON: {{\"subject\": \"...\", \"body\": \"...\"}}"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=800,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        email_data = json.loads(content)
        logger.info("Drafted re-engagement email: '%s'", email_data.get("subject", "?"))

        # Store as a Holly memory fact for later use
        try:
            from src.holly.memory import store_fact
            store_fact(
                category="email_drafts",
                content=json.dumps(email_data)[:500],
                source="revenue_engine",
            )
        except Exception:
            pass

        return True

    except Exception as e:
        logger.warning("Failed to draft re-engagement email: %s", e)
        return False


def _store_revenue_evals(results: dict) -> None:
    """Store revenue engine results as APS eval entries."""
    try:
        from src.aps.store import store_eval_result

        suite_id = f"revenue_eng_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"

        # Overall workflow result
        store_eval_result(
            suite_id=suite_id,
            task_id="overall",
            passed=results["seo_improvements"] > 0 or results["social_posts_generated"] > 0,
            score=min(1.0, (results["seo_improvements"] + results["social_posts_generated"]) / 10.0),
            latency_ms=0,
            cost_usd=0.003 * (results["seo_improvements"] + results["social_posts_generated"] + results["email_campaigns_drafted"]),
            output_preview=json.dumps({
                "seo_fixes": results["seo_improvements"],
                "posts": results["social_posts_generated"],
                "emails": results["email_campaigns_drafted"],
                "errors": len(results["errors"]),
            })[:500],
        )

        # Per-product results
        for i, er in enumerate(results.get("eval_results", [])):
            store_eval_result(
                suite_id=suite_id,
                task_id=f"seo_{i}_{er.get('title', '?')[:20]}",
                passed=er.get("fixed", False),
                score=1.0 if er.get("fixed") else 0.0,
                latency_ms=0,
                cost_usd=0.002,
                output_preview=json.dumps(er)[:500],
            )

        logger.info("Stored revenue engine eval results for suite %s", suite_id)
    except Exception as e:
        logger.warning("Failed to store revenue eval results: %s", e)
