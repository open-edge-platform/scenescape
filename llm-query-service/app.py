# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
LLM Query Service - Uses Ollama to process natural language queries and generate InfluxDB Flux queries.
Supports scene analytics queries for person tracking, dwell time, tripwire crossings, and more.
"""

import os
import logging
import json
from flask import Flask, request, jsonify
import requests
from requests.exceptions import ReadTimeout, ConnectTimeout

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral:latest")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "SS-IGK6")
SERVICE_TIMEOUT = int(os.environ.get("SERVICE_TIMEOUT", "180"))

SYSTEM_PROMPT = """You are an expert at converting natural language queries into InfluxDB Flux queries for scene analytics data.

The InfluxDB bucket contains these measurements:

1. **tripwire_crossings**: Use for queries about people CROSSING lines, ENTERING/EXITING through doorways
   - Fields: count (integer - number of crossings in this specific event record)
   - Tags: location="IGK6", tripwire="entry", object="person", direction="forward" or "backward"
   - CRITICAL: To get TOTAL crossings, you MUST use: |> aggregateWindow() or |> sum()
   - Each record is an individual crossing event with its count
   - Direction "forward" = entering, "backward" = exiting
   - Example: "How many people entered?" → use tripwire_crossings with tripwire="entry", direction="forward" and sum aggregation

2. **region_obj_count_2**: Use for queries about HOW MANY objects are CURRENTLY IN a region
   - Fields: count (integer - snapshot count of objects in region at this time)
   - Tags: location="IGK6", region=<region_name>, object="person"
   - This shows occupancy over time, not total crossings
   - Use |> last() to get current count, or |> mean() for average occupancy

3. **region_obj_dwell_2**: Use for queries about TIME SPENT or DWELL TIME in regions
   - Fields: dwell_time (float - seconds spent in region)
   - Tags: location="IGK6", region=<region_name>, object="person"
   - IMPORTANT: Do NOT filter by _field for this measurement - dwell_time is accessed directly
   - Use |> mean() for average dwell time
   - Use |> max() for longest dwell time

4. **person_loc**: Use ONLY for queries about LOCATION COORDINATES or MOVEMENT tracking
   - Fields: obj_id, latitude, longitude, heading, velocity (float - m/s)
   - Tags: location="IGK6"
   - DO NOT use for counting people - use region_obj_count_2 or tripwire_crossings instead

CRITICAL KEYWORD MAPPINGS:
- "crossed", "entered", "exited", "went through", "came in", "left", "entrance", "exit" → tripwire_crossings
- "how many in", "count in region", "people in area", "occupancy", "currently in" → region_obj_count_2
- "time spent", "dwell time", "how long", "duration" → region_obj_dwell_2
- "where", "location", "coordinates", "moving", "velocity" → person_loc

AVAILABLE REGIONS AND TRIPWIRES:
- Region names: "demo_room", "tray_area"
  * "demo_room" = main demo room area
  * "tray_area" = tray/serving area
- Tripwire: "entry" (the single entry point tripwire)
- When user mentions "waiting area", "waiting room", or similar → use "demo_room"
- When user mentions "tray", "serving area", or similar → use "tray_area"
- When user mentions "entrance", "entry", "door" → use tripwire="entry"

IMPORTANT RULES:
- Always filter by location="IGK6" for all queries
- Always filter by object="person" for people queries
- For tripwire_crossings, ALWAYS use tripwire="entry" (this is the only tripwire)
- For tripwire_crossings, use aggregateWindow(every: v.windowPeriod, fn: sum) or |> sum() for totals
- ALWAYS use exact region names: "demo_room" or "tray_area" (with underscores, not spaces)
- If region not specified, query ALL regions (don't filter by region tag)
- Use appropriate time ranges: -5m, -30m, -1h, -24h, -7d
- Bucket name: {bucket}
- Field name in tripwire_crossings and region_obj_count_2 is "count" (use r["_field"] == "count")

Generate a valid InfluxDB Flux query based on the user's natural language request.
Respond ONLY with a JSON object in this exact format:
{{
  "flux_query": "from(bucket:\\"...\\")|>...",
  "summary": "Brief human-readable description of what the query does"
}}

Do not include any other text, explanations, or markdown formatting."""

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    try:
        # Check if Ollama is available
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        ollama_status = "healthy" if response.status_code == 200 else "unavailable"
    except Exception as e:
        ollama_status = f"error: {str(e)}"
    
    return jsonify({
        "status": "healthy",
        "ollama_status": ollama_status,
        "ollama_url": OLLAMA_URL,
        "model": OLLAMA_MODEL
    }), 200

def call_ollama(prompt: str, system_prompt: str) -> dict:
    """
    Call Ollama API to generate a response.
    
    Args:
        prompt: User's natural language query
        system_prompt: System prompt with context
        
    Returns:
        dict with 'flux_query' and 'summary' keys
    """
    try:
        # Add concrete examples to guide the model
        examples = f"""
EXAMPLES:

Query: "How many people entered in the last 24 hours?"
Response: {{"flux_query": "from(bucket:\\"{INFLUX_BUCKET}\\") |> range(start: -24h) |> filter(fn: (r) => r[\\"_measurement\\"] == \\"tripwire_crossings\\") |> filter(fn: (r) => r[\\"_field\\"] == \\"count\\") |> filter(fn: (r) => r[\\"location\\"] == \\"IGK6\\") |> filter(fn: (r) => r[\\"object\\"] == \\"person\\") |> filter(fn: (r) => r[\\"tripwire\\"] == \\"entry\\") |> filter(fn: (r) => r[\\"direction\\"] == \\"forward\\") |> sum()", "summary": "Total people who entered through the entry tripwire in the last 24 hours"}}

Query: "What is the average dwell time in the last hour?"
Response: {{"flux_query": "from(bucket:\\"{INFLUX_BUCKET}\\") |> range(start: -1h) |> filter(fn: (r) => r[\\"_measurement\\"] == \\"region_obj_dwell_2\\") |> filter(fn: (r) => r[\\"_field\\"] == \\"dwell_time\\") |> filter(fn: (r) => r[\\"location\\"] == \\"IGK6\\") |> filter(fn: (r) => r[\\"object\\"] == \\"person\\") |> mean()", "summary": "Average dwell time across all regions in the last hour"}}

Query: "How many people are in the demo room right now?"
Response: {{"flux_query": "from(bucket:\\"{INFLUX_BUCKET}\\") |> range(start: -5m) |> filter(fn: (r) => r[\\"_measurement\\"] == \\"region_obj_count_2\\") |> filter(fn: (r) => r[\\"_field\\"] == \\"count\\") |> filter(fn: (r) => r[\\"location\\"] == \\"IGK6\\") |> filter(fn: (r) => r[\\"object\\"] == \\"person\\") |> filter(fn: (r) => r[\\"region\\"] == \\"demo_room\\") |> last()", "summary": "Current occupancy count in the demo room"}}

Query: "Show me people count in the tray area over time"
Response: {{"flux_query": "from(bucket:\\"{INFLUX_BUCKET}\\") |> range(start: -1h) |> filter(fn: (r) => r[\\"_measurement\\"] == \\"region_obj_count_2\\") |> filter(fn: (r) => r[\\"_field\\"] == \\"count\\") |> filter(fn: (r) => r[\\"location\\"] == \\"IGK6\\") |> filter(fn: (r) => r[\\"object\\"] == \\"person\\") |> filter(fn: (r) => r[\\"region\\"] == \\"tray_area\\")", "summary": "Person count over time in the tray area for the last hour"}}
"""
        
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"{system_prompt}\n\n{examples}\n\nUser query: {prompt}\n\nRespond with JSON only:",
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        logger.info(f"Calling Ollama at {OLLAMA_URL}/api/generate with SERVICE_TIMEOUT={SERVICE_TIMEOUT}s")
        # Use an explicit (connect, read) timeout tuple so connect timeout and read timeout are controlled.
        # Keep a reasonable small connect timeout, and use SERVICE_TIMEOUT for the read timeout.
        connect_timeout = min(5, SERVICE_TIMEOUT)
        read_timeout = SERVICE_TIMEOUT
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
                timeout=(connect_timeout, read_timeout)
            )
        except requests.exceptions.ReadTimeout as e:
            logger.error(f"Ollama read timeout after {read_timeout}s: {e}")
            raise
        except requests.exceptions.ConnectTimeout as e:
            logger.error(f"Ollama connect timeout after {connect_timeout}s: {e}")
            raise
        response.raise_for_status()
        
        result = response.json()
        llm_response = result.get("response", "{}")
        
        logger.info(f"Ollama raw response: {llm_response}")
        
        # Parse the JSON response from LLM
        try:
            parsed = json.loads(llm_response)
            if "flux_query" in parsed and "summary" in parsed:
                return parsed
            else:
                logger.warning(f"LLM response missing required fields: {parsed}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return None
            
    except Exception as e:
        logger.exception(f"Error calling Ollama: {e}")
        raise

@app.route("/query", methods=["POST"])
def query():
    """
    Process NLQ query using Ollama LLM to generate Flux query.
    Returns error if LLM fails - caller should handle fallback.
    
    Expected input:
    {
        "query": "show recent scene events"
    }
    
    Expected output:
    {
        "success": true,
        "flux_query": "from(bucket:...) ...",
        "summary": "Human-readable summary",
        "method": "llm"
    }
    """
    try:
        data = request.get_json()
        if not data or "query" not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'query' field in request"
            }), 400
        
        query_text = data["query"]
        logger.info(f"Received NLQ query: {query_text}")
        
        # Call Ollama LLM
        system_prompt = SYSTEM_PROMPT.format(bucket=INFLUX_BUCKET)
        try:
            llm_result = call_ollama(query_text, system_prompt)
        except ReadTimeout as e:
            logger.warning(f"LLM service read timeout: {e}")
            return jsonify({
                "success": False,
                "error": f"LLM service error: read timeout after {SERVICE_TIMEOUT}s"
            }), 504
        except ConnectTimeout as e:
            logger.warning(f"LLM service connect timeout: {e}")
            return jsonify({
                "success": False,
                "error": "LLM service error: could not connect to Ollama (connect timeout)"
            }), 502
        
        if llm_result and "flux_query" in llm_result:
            logger.info(f"LLM generated query successfully")
            return jsonify({
                "success": True,
                "flux_query": llm_result["flux_query"],
                "summary": llm_result["summary"],
                "method": "llm",
                "original_query": query_text
            }), 200
        else:
            logger.error("LLM did not return valid query")
            return jsonify({
                "success": False,
                "error": "LLM returned invalid response"
            }), 500
        
    except Exception as e:
        logger.exception(f"Error processing query: {e}")
        return jsonify({
            "success": False,
            "error": f"LLM service error: {str(e)}"
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
