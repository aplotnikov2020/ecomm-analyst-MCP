"""Market MCP Server — competitor pricing, market sizing, opportunity analysis."""

import json
import random
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("market-analyst")

# ---------------------------------------------------------------------------
# Mock market data
# ---------------------------------------------------------------------------

MARKET_DATA = {
    "footwear": {
        "market_size_usd_bn": 95.4,
        "growth_rate_pct": 5.8,
        "top_players": ["Nike", "Adidas", "New Balance", "ASICS", "Brooks"],
        "avg_price_usd": 89.50,
        "online_share_pct": 38.2,
        "key_trends": ["sustainable materials", "direct-to-consumer", "performance tech"],
    },
    "electronics": {
        "market_size_usd_bn": 1180.0,
        "growth_rate_pct": 8.2,
        "top_players": ["Apple", "Samsung", "Sony", "Bose", "Jabra"],
        "avg_price_usd": 145.00,
        "online_share_pct": 52.7,
        "key_trends": ["AI integration", "true wireless", "noise cancellation"],
    },
    "sports & fitness": {
        "market_size_usd_bn": 178.3,
        "growth_rate_pct": 9.4,
        "top_players": ["Nike", "Lululemon", "Under Armour", "Peloton", "Gaiam"],
        "avg_price_usd": 52.30,
        "online_share_pct": 41.5,
        "key_trends": ["home fitness", "recovery products", "sustainable activewear"],
    },
    "kitchen appliances": {
        "market_size_usd_bn": 245.8,
        "growth_rate_pct": 6.1,
        "top_players": ["Cuisinart", "KitchenAid", "Ninja", "Instant Pot", "Breville"],
        "avg_price_usd": 115.00,
        "online_share_pct": 33.8,
        "key_trends": ["smart connectivity", "multi-function", "energy efficiency"],
    },
    "wearables": {
        "market_size_usd_bn": 95.2,
        "growth_rate_pct": 14.7,
        "top_players": ["Apple", "Samsung", "Fitbit", "Garmin", "Xiaomi"],
        "avg_price_usd": 198.00,
        "online_share_pct": 55.3,
        "key_trends": ["health monitoring", "GPS accuracy", "battery life", "fashion"],
    },
}

COMPETITOR_PRICING = {
    "running-shoes-pro": [
        {"brand": "Nike Air Zoom", "price": 139.99, "rating": 4.7, "review_count": 12450},
        {"brand": "Adidas Ultraboost", "price": 149.99, "rating": 4.8, "review_count": 9870},
        {"brand": "New Balance Fresh Foam", "price": 119.99, "rating": 4.5, "review_count": 6320},
        {"brand": "ASICS Gel-Nimbus", "price": 134.99, "rating": 4.6, "review_count": 5180},
    ],
    "wireless-earbuds": [
        {"brand": "AirPods Pro", "price": 249.00, "rating": 4.9, "review_count": 89200},
        {"brand": "Sony WF-1000XM5", "price": 279.99, "rating": 4.8, "review_count": 21400},
        {"brand": "Jabra Elite 8", "price": 199.99, "rating": 4.6, "review_count": 8760},
        {"brand": "Samsung Galaxy Buds2", "price": 149.99, "rating": 4.4, "review_count": 15300},
    ],
    "yoga-mat": [
        {"brand": "Lululemon The Mat", "price": 98.00, "rating": 4.8, "review_count": 7840},
        {"brand": "Manduka PRO", "price": 120.00, "rating": 4.9, "review_count": 12600},
        {"brand": "Gaiam Premium", "price": 35.99, "rating": 4.4, "review_count": 25800},
        {"brand": "Liforme Original", "price": 140.00, "rating": 4.7, "review_count": 4200},
    ],
    "coffee-maker": [
        {"brand": "Breville Barista Express", "price": 699.99, "rating": 4.8, "review_count": 14500},
        {"brand": "Keurig K-Elite", "price": 189.99, "rating": 4.5, "review_count": 32100},
        {"brand": "Cuisinart DCC-3200", "price": 79.99, "rating": 4.4, "review_count": 28700},
        {"brand": "Ninja CE251", "price": 99.99, "rating": 4.6, "review_count": 19800},
    ],
    "smartwatch": [
        {"brand": "Apple Watch Series 9", "price": 399.00, "rating": 4.9, "review_count": 45600},
        {"brand": "Samsung Galaxy Watch 6", "price": 299.99, "rating": 4.6, "review_count": 18200},
        {"brand": "Garmin Forerunner 265", "price": 449.99, "rating": 4.7, "review_count": 7800},
        {"brand": "Fitbit Sense 2", "price": 249.95, "rating": 4.3, "review_count": 9400},
    ],
}


def _category_for_product(product_id: str) -> str:
    mapping = {
        "running-shoes-pro": "footwear",
        "wireless-earbuds": "electronics",
        "yoga-mat": "sports & fitness",
        "coffee-maker": "kitchen appliances",
        "smartwatch": "wearables",
    }
    return mapping.get(product_id, "electronics")


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_market_overview(category: str) -> str:
    """Get a comprehensive market overview for a product category.

    Args:
        category: Product category (e.g. 'footwear', 'electronics', 'wearables')
    """
    cat_lower = category.lower()
    market = MARKET_DATA.get(cat_lower) or next(
        (v for k, v in MARKET_DATA.items() if k in cat_lower or cat_lower in k),
        None,
    )

    if not market:
        return json.dumps({"error": f"No market data available for category '{category}'"})

    addressable_market = market["market_size_usd_bn"] * (market["online_share_pct"] / 100)
    fragmentation = "fragmented" if len(market["top_players"]) >= 5 else "consolidated"

    return json.dumps({
        "category": category,
        "total_market_size_usd_bn": market["market_size_usd_bn"],
        "annual_growth_rate_pct": market["growth_rate_pct"],
        "cagr_5yr_projection_usd_bn": round(
            market["market_size_usd_bn"] * (1 + market["growth_rate_pct"] / 100) ** 5, 1
        ),
        "online_share_pct": market["online_share_pct"],
        "online_addressable_market_usd_bn": round(addressable_market, 1),
        "market_structure": fragmentation,
        "top_competitors": market["top_players"],
        "avg_selling_price_usd": market["avg_price_usd"],
        "key_growth_drivers": market["key_trends"],
        "market_maturity": (
            "emerging" if market["growth_rate_pct"] > 12
            else "growth" if market["growth_rate_pct"] > 6
            else "mature"
        ),
    })


@mcp.tool()
async def analyze_competitor_pricing(product_id: str, our_price: float = 0.0) -> str:
    """Analyze competitor pricing landscape and positioning for a product.

    Args:
        product_id: Product identifier to analyze
        our_price: Our current selling price (0 to use product's default)
    """
    competitors = COMPETITOR_PRICING.get(product_id, [])
    if not competitors:
        return json.dumps({"error": f"No competitor pricing data for product '{product_id}'"})

    prices = [c["price"] for c in competitors]
    avg_comp_price = sum(prices) / len(prices)
    min_price = min(prices)
    max_price = max(prices)

    # Default to mid-market if our_price not supplied
    if our_price <= 0:
        our_price = avg_comp_price * random.uniform(0.88, 1.05)

    our_percentile = sum(1 for p in prices if p > our_price) / len(prices) * 100

    positioning = "budget" if our_price < avg_comp_price * 0.85 else (
        "premium" if our_price > avg_comp_price * 1.15 else "mid-market"
    )

    avg_comp_rating = sum(c["rating"] for c in competitors) / len(competitors)
    avg_comp_reviews = sum(c["review_count"] for c in competitors) / len(competitors)

    return json.dumps({
        "product_id": product_id,
        "our_price_usd": round(our_price, 2),
        "positioning": positioning,
        "percentile_vs_competition": round(our_percentile, 1),
        "price_analysis": {
            "market_average_usd": round(avg_comp_price, 2),
            "market_low_usd": round(min_price, 2),
            "market_high_usd": round(max_price, 2),
            "price_gap_vs_avg_pct": round((our_price - avg_comp_price) / avg_comp_price * 100, 1),
        },
        "competitors": sorted(competitors, key=lambda x: x["price"]),
        "social_proof_benchmark": {
            "avg_competitor_rating": round(avg_comp_rating, 2),
            "avg_competitor_reviews": round(avg_comp_reviews),
        },
        "pricing_recommendation": (
            f"Consider {'lowering' if our_price > avg_comp_price * 1.20 else 'maintaining'} "
            f"price; market avg is ${avg_comp_price:.2f}"
        ),
    })


@mcp.tool()
async def get_market_sentiment(product_category: str, keywords: str = "") -> str:
    """Analyze consumer sentiment and review trends for a product category.

    Args:
        product_category: Category to analyze
        keywords: Optional specific keywords to focus on
    """
    sentiment_data = {
        "footwear": {"overall": 78, "quality": 82, "value": 71, "comfort": 85, "durability": 74},
        "electronics": {"overall": 81, "quality": 79, "value": 68, "performance": 84, "reliability": 77},
        "sports & fitness": {"overall": 83, "quality": 80, "value": 75, "effectiveness": 86, "durability": 79},
        "kitchen appliances": {"overall": 76, "quality": 78, "value": 72, "ease_of_use": 82, "reliability": 74},
        "wearables": {"overall": 80, "quality": 77, "value": 65, "accuracy": 79, "battery_life": 71},
    }

    cat_lower = product_category.lower()
    sentiment = sentiment_data.get(cat_lower) or next(
        (v for k, v in sentiment_data.items() if k in cat_lower), sentiment_data["electronics"]
    )

    # Simulate top complaints and praises
    top_praises = {
        "footwear": ["great cushioning", "true to size", "durable sole"],
        "electronics": ["clear audio", "long battery", "easy setup"],
        "sports & fitness": ["non-slip surface", "lightweight", "easy to clean"],
        "kitchen appliances": ["fast brewing", "easy cleanup", "consistent results"],
        "wearables": ["accurate tracking", "comfortable", "great app"],
    }
    top_complaints = {
        "footwear": ["runs narrow", "limited color options", "price"],
        "electronics": ["connection drops", "ear tip fit", "charging case"],
        "sports & fitness": ["rolled edges", "thin for hard floors", "smell"],
        "kitchen appliances": ["loud", "drips on counter", "lid issues"],
        "wearables": ["battery life", "screen brightness", "app sync"],
    }

    praises = top_praises.get(cat_lower, ["quality", "value", "design"])
    complaints = top_complaints.get(cat_lower, ["price", "durability", "setup"])

    return json.dumps({
        "product_category": product_category,
        "keywords_focus": keywords or "general",
        "sentiment_scores": {k: v for k, v in sentiment.items()},
        "overall_sentiment": "positive" if sentiment["overall"] >= 75 else "mixed",
        "nps_estimate": round((sentiment["overall"] - 50) * 2.5),
        "top_praised_attributes": praises,
        "top_complained_attributes": complaints,
        "review_volume_trend": random.choice(["growing", "stable", "growing"]),
        "sentiment_vs_3mo_ago": round(random.uniform(-3.5, 8.2), 1),
    })


@mcp.tool()
async def calculate_market_opportunity(
    product_id: str,
    target_market_share_pct: float = 1.0,
    price_point: float = 0.0,
) -> str:
    """Calculate addressable market opportunity and revenue potential for a product.

    Args:
        product_id: Product identifier
        target_market_share_pct: Target market share percentage to capture
        price_point: Target selling price (0 to use market average)
    """
    category = _category_for_product(product_id)
    market = MARKET_DATA.get(category)
    if not market:
        return json.dumps({"error": f"No market data for category '{category}'"})

    price = price_point if price_point > 0 else market["avg_price_usd"]
    online_market_usd_bn = market["market_size_usd_bn"] * (market["online_share_pct"] / 100)

    # Revenue opportunity at target market share
    opportunity_usd_m = online_market_usd_bn * (target_market_share_pct / 100) * 1000

    # Unit opportunity
    avg_order_value = price * 1.15  # account for bundles/accessories
    unit_opportunity = round(opportunity_usd_m * 1_000_000 / avg_order_value)

    # Competitive difficulty score (0-100, higher = more competitive)
    competitor_count = len(market["top_players"])
    competition_score = min(100, 45 + competitor_count * 8 + random.randint(-5, 10))

    # Growth-adjusted 3yr opportunity
    three_yr_opportunity = opportunity_usd_m * (1 + market["growth_rate_pct"] / 100) ** 3

    return json.dumps({
        "product_id": product_id,
        "category": category,
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "market_inputs": {
            "total_market_usd_bn": market["market_size_usd_bn"],
            "online_market_usd_bn": round(online_market_usd_bn, 1),
            "market_growth_rate_pct": market["growth_rate_pct"],
        },
        "opportunity_at_target_share": {
            "target_share_pct": target_market_share_pct,
            "annual_revenue_opportunity_usd_m": round(opportunity_usd_m, 2),
            "unit_volume_opportunity": unit_opportunity,
            "3yr_projected_revenue_usd_m": round(three_yr_opportunity, 2),
        },
        "competitive_difficulty_score": competition_score,
        "entry_barrier": (
            "high" if competition_score > 75 else "medium" if competition_score > 50 else "low"
        ),
        "roi_potential": (
            "excellent" if market["growth_rate_pct"] > 10 and competition_score < 60
            else "good" if market["growth_rate_pct"] > 6
            else "moderate"
        ),
        "key_success_factors": [
            "Differentiated product positioning",
            f"Competitive pricing around ${price:.0f}",
            "Strong review generation strategy",
            "SEO-optimized listings",
        ],
    })


@mcp.tool()
async def get_supply_chain_risks(product_category: str) -> str:
    """Assess supply chain risks and sourcing considerations for a category.

    Args:
        product_category: Product category to assess
    """
    risk_profiles = {
        "footwear": {
            "primary_sources": ["China (52%)", "Vietnam (28%)", "Indonesia (12%)"],
            "lead_time_days": {"standard": 45, "express": 20, "sea_freight": 60},
            "risk_level": "medium",
            "top_risks": ["port congestion", "raw material costs", "labor regulations"],
            "diversification_recommendation": "Increase Vietnam/Indonesia sourcing to reduce China dependency",
        },
        "electronics": {
            "primary_sources": ["China (78%)", "Taiwan (12%)", "South Korea (7%)"],
            "lead_time_days": {"standard": 30, "express": 12, "sea_freight": 45},
            "risk_level": "high",
            "top_risks": ["semiconductor shortages", "geopolitical tensions", "IP protection"],
            "diversification_recommendation": "Qualify Mexico and India as alternative assembly locations",
        },
        "sports & fitness": {
            "primary_sources": ["China (61%)", "India (18%)", "Bangladesh (12%)"],
            "lead_time_days": {"standard": 40, "express": 18, "sea_freight": 55},
            "risk_level": "low",
            "top_risks": ["material quality variance", "minimum order quantities", "ESG compliance"],
            "diversification_recommendation": "Strong supplier base — focus on sustainability certifications",
        },
    }

    cat_lower = product_category.lower()
    profile = risk_profiles.get(cat_lower) or next(
        (v for k, v in risk_profiles.items() if k in cat_lower),
        risk_profiles["electronics"],
    )

    return json.dumps({
        "product_category": product_category,
        "supply_chain_risk_level": profile["risk_level"],
        "primary_sourcing_countries": profile["primary_sources"],
        "average_lead_times": profile["lead_time_days"],
        "key_risks": profile["top_risks"],
        "diversification_recommendation": profile["diversification_recommendation"],
        "recommended_safety_stock_weeks": 8 if profile["risk_level"] == "high" else (6 if profile["risk_level"] == "medium" else 4),
        "tariff_exposure": {
            "us_import_duty_pct": round(random.uniform(5.0, 25.0), 1),
            "section_301_tariff_applicable": random.choice([True, False]),
        },
    })


if __name__ == "__main__":
    mcp.run()
