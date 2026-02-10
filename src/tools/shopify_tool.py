"""Shopify GraphQL Admin API tool.

Wraps the Shopify GraphQL Admin API for product and order management.
REST API is deprecated — using GraphQL exclusively.
Check-before-create idempotency on product creation prevents duplicates.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.tools.idempotency import get_idempotency_store
from src.tools.retry import retry_with_backoff

logger = logging.getLogger(__name__)


@retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
def _graphql_request(query: str, variables: dict | None = None) -> dict:
    """Execute a Shopify GraphQL Admin API request."""
    shop_url = os.environ.get("SHOPIFY_SHOP_URL", "")
    access_token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    api_version = os.environ.get("SHOPIFY_API_VERSION", "2025-01")

    endpoint = f"https://{shop_url}/admin/api/{api_version}/graphql.json"

    response = httpx.post(
        endpoint,
        json={"query": query, "variables": variables or {}},
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


class QueryProductsInput(BaseModel):
    limit: int = Field(default=10, description="Number of products to return")


@tool(args_schema=QueryProductsInput)
def shopify_query_products(limit: int = 10) -> dict:
    """Query products from Shopify store."""
    query = """
    query ($limit: Int!) {
      products(first: $limit) {
        edges {
          node {
            id
            title
            status
            totalInventory
            variants(first: 5) {
              edges {
                node {
                  id
                  title
                  price
                  inventoryQuantity
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
                "status": p["node"]["status"],
                "total_inventory": p["node"]["totalInventory"],
                "variants": [
                    {
                        "id": v["node"]["id"],
                        "title": v["node"]["title"],
                        "price": v["node"]["price"],
                        "inventory": v["node"]["inventoryQuantity"],
                    }
                    for v in p["node"]["variants"]["edges"]
                ],
            }
            for p in products
        ],
    }


class CreateProductInput(BaseModel):
    title: str = Field(description="Product title")
    description: str = Field(default="", description="Product description (HTML)")
    price: str = Field(default="0.00", description="Price as string e.g. '29.99'")


@tool(args_schema=CreateProductInput)
def shopify_create_product(title: str, description: str = "", price: str = "0.00") -> dict:
    """Create a new product in Shopify (with duplicate detection)."""
    store = get_idempotency_store()
    params = {"title": title, "description": description, "price": price}
    idem_key = store.generate_key("shopify_create_product", params)

    cached = store.check_and_set(idem_key)
    if cached:
        logger.info("Returning cached Shopify product for key=%s", idem_key)
        return {**cached.result, "_idempotent": True}

    # Check-before-create: query existing products by title
    check_query = """
    query ($query: String!) {
      products(first: 1, query: $query) {
        edges { node { id title status } }
      }
    }
    """
    existing = _graphql_request(check_query, {"query": f"title:'{title}'"})
    existing_products = existing.get("data", {}).get("products", {}).get("edges", [])
    if existing_products:
        result = {
            "id": existing_products[0]["node"]["id"],
            "title": existing_products[0]["node"]["title"],
            "status": existing_products[0]["node"]["status"],
            "_duplicate_prevented": True,
        }
        store.store(idem_key, result, ttl=3600)
        logger.info("Duplicate Shopify product prevented: %s", title)
        return result

    # Create the product
    mutation = """
    mutation productCreate($input: ProductInput!) {
      productCreate(input: $input) {
        product {
          id
          title
          status
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
            "title": title,
            "descriptionHtml": description,
            "variants": [{"price": price}],
        }
    }
    result = _graphql_request(mutation, variables)
    product_data = result.get("data", {}).get("productCreate", {})
    errors = product_data.get("userErrors", [])

    if errors:
        return {"error": errors[0]["message"], "field": errors[0]["field"]}

    product = product_data.get("product", {})
    product_result = {
        "id": product.get("id"),
        "title": product.get("title"),
        "status": product.get("status"),
    }
    store.store(idem_key, product_result, ttl=3600)
    return product_result


class QueryOrdersInput(BaseModel):
    limit: int = Field(default=10, description="Number of orders to return")


@tool(args_schema=QueryOrdersInput)
def shopify_query_orders(limit: int = 10) -> dict:
    """Query recent orders from Shopify."""
    query = """
    query ($limit: Int!) {
      orders(first: $limit, sortKey: CREATED_AT, reverse: true) {
        edges {
          node {
            id
            name
            createdAt
            displayFinancialStatus
            displayFulfillmentStatus
            totalPriceSet {
              shopMoney {
                amount
                currencyCode
              }
            }
          }
        }
      }
    }
    """
    result = _graphql_request(query, {"limit": limit})
    orders = result.get("data", {}).get("orders", {}).get("edges", [])

    return {
        "count": len(orders),
        "orders": [
            {
                "id": o["node"]["id"],
                "name": o["node"]["name"],
                "created_at": o["node"]["createdAt"],
                "financial_status": o["node"]["displayFinancialStatus"],
                "fulfillment_status": o["node"]["displayFulfillmentStatus"],
                "total": o["node"]["totalPriceSet"]["shopMoney"]["amount"],
                "currency": o["node"]["totalPriceSet"]["shopMoney"]["currencyCode"],
            }
            for o in orders
        ],
    }


def get_shopify_tools() -> list:
    """Return all Shopify tools for agent use."""
    return [shopify_query_products, shopify_create_product, shopify_query_orders]
