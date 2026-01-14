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

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "SS-Anthem")
SERVICE_TIMEOUT = int(os.environ.get("SERVICE_TIMEOUT", "60"))


SYSTEM_PROMPT = """You are an expert at converting natural language queries into InfluxDB Flux queries for scene analytics data.

The InfluxDB bucket contains these measurements:

1. **tripwire_crossings**: Use for queries about people/objects CROSSING, ENTERING, or EXITING
   - Fields: count (integer - number of crossings in this event)
   - Tags: location="Anthem", tripwire="checkout", object="person", direction="forward" or "backward"
   - To get total crossings: use |> sum(column: "_value")
   - Example tripwires: "checkout", "entrance", "exit"

2. **region_obj_count_2**: Use for queries about HOW MANY objects are IN a region at a point in time
   - Fields: count (integer - current count in region)
   - Tags: location="Anthem", region="waiting_area", object="person"
   - Common regions: "waiting_area", "checkout_area", "entrance"

3. **region_obj_dwell_2**: Use for queries about TIME SPENT or DWELL TIME in regions
   - Fields: dwell_time (float - seconds spent in region)
   - Tags: location="Anthem", region="waiting_area", object="person"
   - Use |> mean() for average dwell time

4. **person_loc**: Use ONLY for queries about LOCATION COORDINATES or MOVEMENT tracking
   - Fields: obj_id, latitude, longitude, heading, velocity
   - Tags: location="Anthem"
   - DO NOT use for counting people - use region_obj_count_2 or tripwire_crossings instead

IMPORTANT RULES:
- For "crossed", "entered", "exited", "went through" → use tripwire_crossings with |> sum()
- For "how many in", "count in region" → use region_obj_count_2
- For "time spent", "dwell time", "how long" → use region_obj_dwell_2
- For "location", "coordinates", "velocity" → use person_loc
- Always filter by object="person" for people queries
- Use appropriate time ranges: -5m, -30m, -1h, -24h
- Bucket name: {bucket}

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
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"{system_prompt}\n\nUser query: {prompt}\n\nRespond with JSON only:",
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        logger.info(f"Calling Ollama at {OLLAMA_URL}/api/generate")
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=SERVICE_TIMEOUT
        )
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
        llm_result = call_ollama(query_text, system_prompt)
        
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
