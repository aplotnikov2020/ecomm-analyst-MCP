# WhatsApp Product Analysis Agent

An AI-powered e-commerce analyst available on WhatsApp. Send a product photo, voice note, or text message and receive demand forecasts, supply assessments, trend analysis, and market opportunities — all driven by Claude Opus 4.7 and a set of specialised MCP data servers.

## Architecture

```
WhatsApp User
     │  photo / audio / text
     ▼
WhatsApp Business Cloud API
     │  webhook POST /webhook
     ▼
FastAPI App  (GCP Cloud Run)
     │
     ├─► Google Cloud Speech-to-Text   (audio → transcript)
     ├─► Claude Vision                 (product photo → identification)
     │
     ▼
Claude Opus 4.7  (adaptive thinking + prompt caching)
     │  tool calls
     ├─► MCP: ecomm-server    — sales, inventory, demand forecast
     ├─► MCP: trends-server   — Google Trends, seasonality
     └─► MCP: market-server   — competitor pricing, market sizing
     │
     ▼
Firestore  (conversation history, 24 h TTL)
     │
     ▼
WhatsApp reply
```

## Features

| Capability | Detail |
|---|---|
| **Product photo** | Claude Vision identifies the product category and prompts for analysis type |
| **Audio message** | Google Cloud Speech-to-Text transcribes the voice note before analysis |
| **Text query** | Direct natural-language analysis requests |
| **Multi-turn** | Conversation context retained per user for 24 hours (Firestore) |
| **Demand analysis** | Historical sales trends, MoM momentum, 90-day forecast |
| **Supply analysis** | Inventory levels, days-of-stock, reorder alerts, supplier lead times |
| **Trend analysis** | Google Trends search interest, rising keywords, competitor keyword comparison |
| **Seasonality** | Monthly seasonality indices, peak/trough identification, planning calendar |
| **Market analysis** | Market size, growth rate, competitor pricing landscape, opportunity sizing |
| **Supply chain** | Sourcing country risk, lead times, tariff exposure |

## Project Structure

```
ecomm-analyst-MCP/
├── src/
│   ├── main.py              # FastAPI app & webhook endpoints
│   ├── config.py            # Pydantic settings (env vars)
│   ├── agent/
│   │   ├── core.py          # Claude agent loop + MCP connection manager
│   │   └── prompts.py       # System prompt
│   ├── whatsapp/
│   │   ├── client.py        # WhatsApp Business Cloud API client
│   │   └── webhook.py       # Webhook payload parser
│   └── media/
│       ├── audio.py         # Google Cloud Speech-to-Text
│       └── image.py         # Image encoding for Claude Vision
├── mcp_servers/
│   ├── ecomm_server.py      # Product catalog, sales, inventory, forecasting
│   ├── trends_server.py     # Google Trends, seasonality, rising trends
│   └── market_server.py     # Competitor pricing, market sizing, supply chain
├── deploy/
│   ├── Dockerfile
│   ├── cloudbuild.yaml      # Cloud Build CI/CD pipeline
│   └── service.yaml         # Cloud Run service manifest
└── tests/
    ├── test_webhook.py
    └── test_agent.py
```

## Prerequisites

- Python 3.11+
- GCP project with the following APIs enabled:
  - Cloud Run, Cloud Build, Cloud Speech-to-Text, Cloud Storage, Firestore
- [WhatsApp Business account](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started) with Cloud API access
- Anthropic API key

## Local Development

```bash
# 1. Clone and install dependencies
git clone https://github.com/aplotnikov2020/ecomm-analyst-MCP.git
cd ecomm-analyst-MCP
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Run the server
uvicorn src.main:app --reload --port 8080

# 4. Expose to WhatsApp via tunnel (e.g. ngrok)
ngrok http 8080
# Set the ngrok URL as your WhatsApp webhook: https://<id>.ngrok.io/webhook
```

### Test Without WhatsApp

```bash
curl -X POST http://localhost:8080/dev/chat \
  -H "Content-Type: application/json" \
  -d '{"from": "+15551234567", "text": "Analyse demand for wireless earbuds"}'
```

### Run Tests

```bash
pytest tests/ -v
```

## Deployment to GCP Cloud Run

### 1. Store secrets in Secret Manager

```bash
echo -n "$WHATSAPP_TOKEN"        | gcloud secrets create whatsapp-token --data-file=-
echo -n "$WHATSAPP_VERIFY_TOKEN" | gcloud secrets create whatsapp-verify-token --data-file=-
echo -n "$WHATSAPP_PHONE_ID"     | gcloud secrets create whatsapp-phone-number-id --data-file=-
echo -n "$ANTHROPIC_API_KEY"     | gcloud secrets create anthropic-key --data-file=-
```

### 2. Grant the service account access

```bash
PROJECT_ID=$(gcloud config get-value project)
SA="whatsapp-analyst-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create whatsapp-analyst-sa
for role in run.invoker secretmanager.secretAccessor datastore.user speech.client storage.objectAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA}" --role="roles/$role"
done
```

### 3. Deploy

```bash
# Update PROJECT_ID placeholders in deploy/service.yaml then:
gcloud run services replace deploy/service.yaml --region=us-central1

# Or use Cloud Build for CI/CD:
gcloud builds submit --config=deploy/cloudbuild.yaml \
  --substitutions=_PROJECT_ID=$PROJECT_ID,_PHONE_NUMBER_ID=$WHATSAPP_PHONE_NUMBER_ID
```

### 4. Register the webhook with Meta

In the Meta Developer console → WhatsApp → Configuration:
- **Callback URL**: `https://<your-cloud-run-url>/webhook`
- **Verify token**: value of `WHATSAPP_VERIFY_TOKEN`
- **Subscribed fields**: `messages`

## MCP Servers

Each server runs as a subprocess inside the Cloud Run container and communicates over stdio. The agent core connects to all three on startup and discovers their tools automatically.

| Server | Tools |
|---|---|
| `ecomm_server` | `search_products`, `get_sales_data`, `get_inventory_status`, `get_demand_forecast`, `get_top_products` |
| `trends_server` | `get_search_trends`, `analyze_seasonality`, `get_rising_trends`, `compare_keyword_trends` |
| `market_server` | `get_market_overview`, `analyze_competitor_pricing`, `get_market_sentiment`, `calculate_market_opportunity`, `get_supply_chain_risks` |

### Connecting Real Data Sources

The MCP servers ship with realistic mock data. Replace the data layer inside each server without changing the tool signatures:

```python
# mcp_servers/ecomm_server.py — swap mock for real DB
@mcp.tool()
async def get_sales_data(product_id: str, months: int = 12) -> str:
    # Replace with: BigQuery, Snowflake, Shopify API, etc.
    rows = await bigquery_client.query(
        "SELECT month, units FROM sales WHERE product_id = @id",
        params={"id": product_id}
    )
    ...
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `WHATSAPP_TOKEN` | ✅ | Meta WhatsApp Cloud API access token |
| `WHATSAPP_PHONE_NUMBER_ID` | ✅ | WhatsApp phone number ID |
| `WHATSAPP_VERIFY_TOKEN` | ✅ | Webhook verification token (any string you choose) |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `GCP_PROJECT_ID` | ✅ | GCP project ID |
| `GCS_BUCKET_NAME` | ✅ | Cloud Storage bucket for media |
| `FIRESTORE_COLLECTION` | | Firestore collection name (default: `conversations`) |
| `ANTHROPIC_MODEL` | | Claude model ID (default: `claude-opus-4-7`) |
| `CONVERSATION_TTL_HOURS` | | History retention (default: `24`) |
| `MAX_CONVERSATION_TURNS` | | Max turns in context (default: `20`) |
| `MAX_TOOL_ITERATIONS` | | Agent tool call limit per message (default: `10`) |

## Example Conversation

```
User:  [sends photo of running shoes]

Agent: 👟 I can see these are running shoes — looks like a performance road-running model.

       What analysis would you like?
       1️⃣ Demand & sales trends
       2️⃣ Inventory & supply health
       3️⃣ Competitor pricing
       4️⃣ Seasonality patterns
       5️⃣ Full market overview

User:  Full market overview please

Agent: 📊 Full Market Overview — Running Shoes
       ━━━━━━━━━━━━━━━━━━━━
       📦 Monthly units: ~340 | 📈 MoM trend: +4.2%
       💰 Avg price: $129.99 | 🏷️ Margin: 67.7%
       🗓️ Days of stock: 113 days ✅
       🔍 Search interest: rising (+18% last 3mo)

       💡 Key Insights:
       • Peak demand: Nov–Dec (holiday gifting +60%)
       • Market size: $95.4B globally, 5.8% CAGR
       • You're priced 3.8% below market avg — room to raise
       • Rising trend: "barefoot running shoes" +201% YoY

       ⚡ Recommendation:
       Stock up in Sep–Oct for holiday peak. Consider a
       $134.99 price test — still below Nike/Adidas while
       improving margin by ~4 pts.
```

## Extending the Agent

- **Add a new MCP server**: Create `mcp_servers/my_server.py` using `FastMCP`, add its command to `MCP_SERVERS` in `src/agent/core.py`.
- **Connect to remote MCP servers**: Replace `StdioServerParameters` with an SSE/HTTP transport for cloud-hosted MCP services.
- **Add languages**: Google Speech-to-Text auto-detects language; extend the system prompt for non-English markets.
- **Notifications**: Add a scheduled Cloud Scheduler job that calls `/dev/chat` to proactively alert users about inventory risks or trend spikes.

## License

MIT
