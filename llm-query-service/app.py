# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
LLM Query Service - Forwards NLQ requests to Node-RED for processing.
This service acts as a thin proxy between Django and Node-RED.
"""

import os
import logging
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
NODE_RED_URL = os.environ.get("NODE_RED_URL", "http://node-red:1880")
NODE_RED_NLQ_ENDPOINT = os.environ.get("NODE_RED_NLQ_ENDPOINT", "/nlq")
SERVICE_TIMEOUT = int(os.environ.get("SERVICE_TIMEOUT", "30"))

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200

@app.route("/query", methods=["POST"])
def query():
    """
    Process NLQ query by forwarding to Node-RED.
    
    Expected input:
    {
        "query": "show recent scene events"
    }
    
    Expected output:
    {
        "success": true,
        "flux_query": "from(bucket:...) ...",
        "summary": "Human-readable summary"
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
        
        # Forward to Node-RED
        node_red_url = f"{NODE_RED_URL}{NODE_RED_NLQ_ENDPOINT}"
        logger.info(f"Forwarding to Node-RED at {node_red_url}")
        
        response = requests.post(
            node_red_url,
            json={"query": query_text},
            timeout=SERVICE_TIMEOUT
        )
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Node-RED response: {result}")
        
        return jsonify(result), 200
        
    except requests.exceptions.Timeout:
        logger.error(f"Node-RED timeout after {SERVICE_TIMEOUT}s")
        return jsonify({
            "success": False,
            "error": f"Node-RED service timeout after {SERVICE_TIMEOUT}s"
        }), 504
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to Node-RED at {NODE_RED_URL}")
        return jsonify({
            "success": False,
            "error": "Node-RED service unavailable"
        }), 503
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"Node-RED HTTP error: {e}")
        return jsonify({
            "success": False,
            "error": f"Node-RED error: {str(e)}"
        }), 502
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
