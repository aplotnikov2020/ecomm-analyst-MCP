"""Tests for agent utilities and MCP server tool schemas."""

import json
import pytest
from src.media.image import encode_image_for_openai, detect_mime_from_bytes


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def test_encode_image_valid_jpeg():
    # Minimal valid JPEG magic bytes padded to >0 bytes
    fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 100
    block = encode_image_for_openai(fake_jpeg, "image/jpeg")
    assert block is not None
    assert block["type"] == "image_url"
    assert block["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_encode_image_empty_returns_none():
    block = encode_image_for_openai(b"", "image/jpeg")
    assert block is None


def test_detect_mime_jpeg():
    assert detect_mime_from_bytes(b"\xff\xd8\xff\xe0") == "image/jpeg"


def test_detect_mime_png():
    assert detect_mime_from_bytes(b"\x89PNG\r\n\x1a\n") == "image/png"


def test_detect_mime_webp():
    assert detect_mime_from_bytes(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"


def test_detect_mime_unknown_defaults_to_jpeg():
    assert detect_mime_from_bytes(b"\x00\x00\x00\x00") == "image/jpeg"


# ---------------------------------------------------------------------------
# MCP server tool schemas (import the servers and verify tool registration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ecomm_server_search_products():
    from mcp_servers.ecomm_server import search_products
    result = await search_products("yoga")
    data = json.loads(result)
    assert "found" in data
    assert data["found"] >= 1


@pytest.mark.asyncio
async def test_ecomm_server_get_sales_data():
    from mcp_servers.ecomm_server import get_sales_data
    result = await get_sales_data("yoga-mat", months=6)
    data = json.loads(result)
    assert "total_units_sold" in data
    assert data["period_months"] == 6


@pytest.mark.asyncio
async def test_trends_server_seasonality():
    from mcp_servers.trends_server import analyze_seasonality
    result = await analyze_seasonality("footwear")
    data = json.loads(result)
    assert "seasonality_strength" in data
    assert "monthly_indices" in data
    assert len(data["monthly_indices"]) == 12


@pytest.mark.asyncio
async def test_market_server_overview():
    from mcp_servers.market_server import get_market_overview
    result = await get_market_overview("electronics")
    data = json.loads(result)
    assert "total_market_size_usd_bn" in data
    assert data["market_structure"] in ("fragmented", "consolidated")


@pytest.mark.asyncio
async def test_market_server_opportunity():
    from mcp_servers.market_server import calculate_market_opportunity
    result = await calculate_market_opportunity("yoga-mat", target_market_share_pct=0.5)
    data = json.loads(result)
    assert "opportunity_at_target_share" in data
    assert data["opportunity_at_target_share"]["target_share_pct"] == 0.5
