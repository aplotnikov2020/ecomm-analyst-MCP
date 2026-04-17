"""E-Commerce MCP Server — product catalog, sales, inventory, demand."""

import json
import random
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ecomm-analyst")

# ---------------------------------------------------------------------------
# Mock data layer — replace with real DB / API calls in production
# ---------------------------------------------------------------------------

PRODUCT_DB = {
    "running-shoes-pro": {
        "id": "running-shoes-pro",
        "name": "ProRun Elite Running Shoes",
        "category": "Footwear",
        "subcategory": "Running",
        "brand": "ProRun",
        "avg_price": 129.99,
        "cost": 42.00,
        "weight_kg": 0.32,
        "tags": ["running", "athletic", "shoes", "sport"],
    },
    "wireless-earbuds": {
        "id": "wireless-earbuds",
        "name": "SoundPro X5 Wireless Earbuds",
        "category": "Electronics",
        "subcategory": "Audio",
        "brand": "SoundPro",
        "avg_price": 79.99,
        "cost": 18.50,
        "weight_kg": 0.05,
        "tags": ["earbuds", "wireless", "bluetooth", "audio"],
    },
    "yoga-mat": {
        "id": "yoga-mat",
        "name": "ZenFlow Premium Yoga Mat",
        "category": "Sports & Fitness",
        "subcategory": "Yoga",
        "brand": "ZenFlow",
        "avg_price": 45.99,
        "cost": 9.80,
        "weight_kg": 1.2,
        "tags": ["yoga", "fitness", "mat", "exercise"],
    },
    "coffee-maker": {
        "id": "coffee-maker",
        "name": "BrewMaster Pro Coffee Maker",
        "category": "Kitchen Appliances",
        "subcategory": "Coffee",
        "brand": "BrewMaster",
        "avg_price": 189.99,
        "cost": 58.00,
        "weight_kg": 2.8,
        "tags": ["coffee", "kitchen", "appliance", "brewing"],
    },
    "smartwatch": {
        "id": "smartwatch",
        "name": "FitTrack Pro Smartwatch",
        "category": "Electronics",
        "subcategory": "Wearables",
        "brand": "FitTrack",
        "avg_price": 249.99,
        "cost": 72.00,
        "weight_kg": 0.08,
        "tags": ["smartwatch", "fitness", "wearable", "health"],
    },
}


def _generate_monthly_sales(base: int, months: int = 24, seasonal: bool = True) -> list[dict]:
    """Generate realistic monthly sales data with optional seasonality."""
    now = datetime.now()
    data = []
    for i in range(months, 0, -1):
        date = now - timedelta(days=30 * i)
        month = date.month
        # Apply seasonal multiplier
        seasonal_mult = 1.0
        if seasonal:
            # Q4 holiday boost
            if month in (11, 12):
                seasonal_mult = 1.6
            elif month == 1:
                seasonal_mult = 0.75  # post-holiday dip
            elif month in (6, 7, 8):
                seasonal_mult = 1.2  # summer boost
        units = int(base * seasonal_mult * random.uniform(0.85, 1.15))
        data.append({"month": date.strftime("%Y-%m"), "units": units})
    return data


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_products(query: str, category: str = "", limit: int = 5) -> str:
    """Search the product catalog by name, category, or keyword.

    Args:
        query: Search query (product name, keyword, or description)
        category: Optional category filter (e.g. 'Electronics', 'Footwear')
        limit: Maximum number of results to return
    """
    query_lower = query.lower()
    results = []

    for product in PRODUCT_DB.values():
        if category and product["category"].lower() != category.lower():
            continue
        score = 0
        if query_lower in product["name"].lower():
            score += 3
        if query_lower in product["category"].lower():
            score += 2
        if any(query_lower in tag for tag in product["tags"]):
            score += 1
        if score > 0:
            results.append((score, product))

    results.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in results[:limit]]

    if not top:
        return json.dumps({"found": 0, "message": f"No products found matching '{query}'"})

    return json.dumps(
        {
            "found": len(top),
            "products": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "category": p["category"],
                    "price": p["avg_price"],
                    "margin_pct": round((p["avg_price"] - p["cost"]) / p["avg_price"] * 100, 1),
                }
                for p in top
            ],
        }
    )


@mcp.tool()
async def get_sales_data(product_id: str, months: int = 12) -> str:
    """Retrieve historical monthly sales data for a product.

    Args:
        product_id: Product identifier
        months: Number of historical months to retrieve (max 24)
    """
    months = min(months, 24)
    product = PRODUCT_DB.get(product_id)
    if not product:
        return json.dumps({"error": f"Product '{product_id}' not found"})

    # Base units vary by product
    base_units = {"running-shoes-pro": 340, "wireless-earbuds": 820, "yoga-mat": 290,
                  "coffee-maker": 175, "smartwatch": 210}.get(product_id, 200)

    sales = _generate_monthly_sales(base_units, months)
    total_units = sum(s["units"] for s in sales)
    total_revenue = total_units * product["avg_price"]
    avg_monthly = total_units / months

    # Simple MoM trend
    if len(sales) >= 3:
        recent_avg = sum(s["units"] for s in sales[-3:]) / 3
        older_avg = sum(s["units"] for s in sales[-6:-3]) / 3
        trend_pct = round((recent_avg - older_avg) / older_avg * 100, 1) if older_avg else 0
    else:
        trend_pct = 0

    return json.dumps({
        "product_id": product_id,
        "product_name": product["name"],
        "period_months": months,
        "total_units_sold": total_units,
        "total_revenue_usd": round(total_revenue, 2),
        "avg_monthly_units": round(avg_monthly, 1),
        "mom_trend_pct": trend_pct,
        "monthly_breakdown": sales,
    })


@mcp.tool()
async def get_inventory_status(product_id: str) -> str:
    """Get current inventory levels, reorder points, and supply health.

    Args:
        product_id: Product identifier
    """
    product = PRODUCT_DB.get(product_id)
    if not product:
        return json.dumps({"error": f"Product '{product_id}' not found"})

    # Simulate inventory data
    stock_map = {
        "running-shoes-pro": 1240,
        "wireless-earbuds": 3800,
        "yoga-mat": 650,
        "coffee-maker": 320,
        "smartwatch": 890,
    }
    current_stock = stock_map.get(product_id, 500)
    daily_velocity = random.randint(8, 25)
    days_of_stock = round(current_stock / daily_velocity, 1)
    reorder_point = daily_velocity * 14  # 2-week buffer
    lead_time_days = random.randint(14, 45)

    status = "healthy"
    if days_of_stock < 14:
        status = "critical"
    elif days_of_stock < 30:
        status = "low"
    elif days_of_stock > 180:
        status = "overstocked"

    return json.dumps({
        "product_id": product_id,
        "product_name": product["name"],
        "current_stock_units": current_stock,
        "daily_sales_velocity": daily_velocity,
        "days_of_stock_remaining": days_of_stock,
        "reorder_point_units": reorder_point,
        "needs_reorder": current_stock <= reorder_point,
        "supplier_lead_time_days": lead_time_days,
        "inventory_status": status,
        "warehouses": [
            {"location": "US-East", "units": int(current_stock * 0.45)},
            {"location": "US-West", "units": int(current_stock * 0.35)},
            {"location": "EU-Central", "units": int(current_stock * 0.20)},
        ],
    })


@mcp.tool()
async def get_demand_forecast(product_id: str, forecast_days: int = 90) -> str:
    """Get demand forecast using historical sales patterns.

    Args:
        product_id: Product identifier
        forecast_days: Number of days to forecast (30, 60, or 90)
    """
    product = PRODUCT_DB.get(product_id)
    if not product:
        return json.dumps({"error": f"Product '{product_id}' not found"})

    forecast_days = min(forecast_days, 90)
    base_daily = {"running-shoes-pro": 11, "wireless-earbuds": 27, "yoga-mat": 9,
                  "coffee-maker": 6, "smartwatch": 7}.get(product_id, 8)

    # Project with growth factor and seasonality
    now = datetime.now()
    monthly_forecast = []
    for week in range(0, forecast_days, 30):
        month = (now + timedelta(days=week)).month
        seasonal = 1.5 if month in (11, 12) else (0.8 if month == 1 else 1.0)
        growth = 1.02 ** (week / 30)  # 2% monthly growth
        projected_daily = base_daily * seasonal * growth
        monthly_forecast.append({
            "period_start": (now + timedelta(days=week)).strftime("%Y-%m-%d"),
            "projected_daily_units": round(projected_daily, 1),
            "projected_monthly_units": round(projected_daily * 30),
            "confidence_interval": [
                round(projected_daily * 0.85 * 30),
                round(projected_daily * 1.15 * 30),
            ],
        })

    total_projected = sum(m["projected_monthly_units"] for m in monthly_forecast)

    return json.dumps({
        "product_id": product_id,
        "product_name": product["name"],
        "forecast_horizon_days": forecast_days,
        "total_projected_units": total_projected,
        "total_projected_revenue_usd": round(total_projected * product["avg_price"], 2),
        "methodology": "time-series decomposition with seasonal adjustment",
        "forecast_accuracy_mape": round(random.uniform(8.5, 14.2), 1),
        "monthly_forecast": monthly_forecast,
    })


@mcp.tool()
async def get_top_products(category: str = "", metric: str = "revenue", limit: int = 10) -> str:
    """Get top-performing products by revenue, units, or margin.

    Args:
        category: Filter by category (leave empty for all categories)
        metric: Ranking metric — 'revenue', 'units', or 'margin'
        limit: Number of top products to return
    """
    products = list(PRODUCT_DB.values())
    if category:
        products = [p for p in products if p["category"].lower() == category.lower()]

    ranked = []
    for p in products:
        base = {"running-shoes-pro": 340, "wireless-earbuds": 820, "yoga-mat": 290,
                "coffee-maker": 175, "smartwatch": 210}.get(p["id"], 200)
        monthly_units = base
        monthly_revenue = monthly_units * p["avg_price"]
        margin = (p["avg_price"] - p["cost"]) / p["avg_price"] * 100
        score = monthly_revenue if metric == "revenue" else (monthly_units if metric == "units" else margin)
        ranked.append({
            "id": p["id"],
            "name": p["name"],
            "category": p["category"],
            "monthly_units": monthly_units,
            "monthly_revenue_usd": round(monthly_revenue, 2),
            "margin_pct": round(margin, 1),
            "score": score,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return json.dumps({
        "metric": metric,
        "category_filter": category or "all",
        "top_products": [{k: v for k, v in p.items() if k != "score"} for p in ranked[:limit]],
    })


if __name__ == "__main__":
    mcp.run()
