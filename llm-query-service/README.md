# LLM Query Service

A lightweight Flask service that forwards Natural Language Query (NLQ) requests to Node-RED for processing.

## Architecture

This service acts as a proxy between the Django backend and Node-RED:
1. Django sends NLQ requests to this service
2. Service forwards requests to Node-RED's `/nlq` endpoint
3. Node-RED processes simple NLQ cases and returns Flux queries
4. Service returns the response to Django

## Environment Variables

- `NODE_RED_URL`: Node-RED base URL (default: `http://node-red:1880`)
- `NODE_RED_NLQ_ENDPOINT`: Node-RED NLQ endpoint path (default: `/nlq`)
- `SERVICE_TIMEOUT`: Request timeout in seconds (default: `30`)
- `PORT`: Service port (default: `5000`)

## Endpoints

### GET /health
Health check endpoint.

### POST /query
Process NLQ query.

**Request:**
```json
{
  "query": "show recent scene events"
}
```

**Response:**
```json
{
  "success": true,
  "flux_query": "from(bucket:\"scenescape\") |> range(start:-1h) ...",
  "summary": "Human-readable summary of the query results"
}
```

## Building

```bash
docker build -t llm-query-service:latest .
```

## Running

```bash
docker run -p 5000:5000 \
  -e NODE_RED_URL=http://node-red:1880 \
  llm-query-service:latest
```
