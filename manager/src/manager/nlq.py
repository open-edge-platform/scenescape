# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Natural Language Query (NLQ) API for Intel SceneScape.
Translates natural language prompts into InfluxDB Flux queries using LLM Query Service.
"""

import os
import json
import logging
from statistics import mean

import requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# Configuration
INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb2:8086")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "ITM")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "SS-Anthem")

# Read InfluxDB token from file path (if INFLUXDB_INIT_ADMIN_TOKEN_FILE is set) or env variables
token_file = os.environ.get("INFLUXDB_INIT_ADMIN_TOKEN_FILE")
if token_file and os.path.exists(token_file):
    try:
        with open(token_file, 'r') as f:
            INFLUX_TOKEN = f.read().strip()
    except Exception as e:
        logger.warning(f"Could not read token from file {token_file}: {e}")
        INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", os.environ.get("INFLUXDB_INIT_ADMIN_TOKEN", "scenescape-token"))
else:
    INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", os.environ.get("INFLUXDB_INIT_ADMIN_TOKEN", "scenescape-token"))

LLM_SERVICE_URL = os.environ.get("LLM_SERVICE_URL", "http://llm-query-service:5000")
LLM_SERVICE_TIMEOUT = int(os.environ.get("LLM_SERVICE_TIMEOUT", "30"))


def translate_with_llm_service(prompt: str) -> tuple:
    """
    Translate prompt using LLM Query Service (which delegates to Node-RED).
    
    Returns tuple (flux_query, summary) or (None, None) on failure.
    """
    try:
        url = f"{LLM_SERVICE_URL}/query"
        logger.info(f"Calling LLM service at {url} with prompt: {prompt}")
        
        response = requests.post(
            url,
            json={"query": prompt},
            timeout=LLM_SERVICE_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            flux = data.get("flux_query", "")
            summary = data.get("summary", "")
            logger.info(f"LLM service returned Flux query: {flux}")
            return flux, summary
        else:
            logger.warning(f"LLM service returned error: {data.get('error')}")
            return None, None
            
    except requests.exceptions.Timeout:
        logger.warning(f"LLM service timeout after {LLM_SERVICE_TIMEOUT}s")
        return None, None
    except requests.exceptions.ConnectionError:
        logger.warning(f"LLM service unavailable at {LLM_SERVICE_URL}")
        return None, None
    except Exception as e:
        logger.warning(f"Error calling LLM service: {e}")
        return None, None


def rule_based_translate(prompt: str) -> str:
    """
    Fallback rule-based translation when LLM service is unavailable.
    """
    p = prompt.lower()
    if "scene event" in p or "scene_event" in p or "scene events" in p:
        if "last" in p and "hour" in p:
            return f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-1h) |> filter(fn:(r)=> r._measurement == "scene_event")'
        return f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-24h) |> filter(fn:(r)=> r._measurement == "scene_event")'
    if "object" in p and "detect" in p:
        if "count" in p:
            return f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-24h) |> filter(fn:(r)=> r._measurement == "object_detection") |> count()'
        return f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-24h) |> filter(fn:(r)=> r._measurement == "object_detection")'
    return f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-1h) |> limit(n:100)'


def run_flux(flux: str):
    """Execute Flux query against InfluxDB."""
    url = f"{INFLUX_URL}/api/v2/query?org={INFLUX_ORG}"
    headers = {
        "Authorization": f"Token {INFLUX_TOKEN}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    r = requests.post(url, headers=headers, data=flux, timeout=20)
    r.raise_for_status()
    return r.text


def parse_flux_csv(csv_text: str):
    """
    Parse Flux CSV output into a list of records (dicts).
    
    Handles repeated header blocks by detecting header lines that contain
    the Flux `_time` or `_value` columns and mapping subsequent data rows.
    """
    rows = []
    if not csv_text:
        return rows
    lines = [l for l in csv_text.splitlines()]
    header = None
    for line in lines:
        if not line.strip():
            # blank separator between tables
            header = None
            continue
        if line.startswith('#'):
            continue
        # detect header line
        if ('_time' in line and '_value' in line) or line.startswith(',result'):
            parts = [p.strip() for p in line.split(',')]
            header = parts
            continue
        if header is None:
            # skip until we find a header
            continue
        parts = [p for p in line.split(',')]
        if len(parts) < len(header):
            parts += [''] * (len(header) - len(parts))
        elif len(parts) > len(header):
            parts = parts[:len(header)]
        record = {h: v for h, v in zip(header, parts)}
        rows.append(record)
    return rows


def summarize_records(rows):
    """Produce a structured summary and a short human text from parsed rows."""
    summary = {}
    if not rows:
        return summary, "No results for your query."
    
    measurements = {}
    for r in rows:
        m = r.get('_measurement') or ''
        measurements.setdefault(m, []).append(r)

    texts = []
    for m, recs in measurements.items():
        numeric_vals = []
        for r in recs:
            v = r.get('_value')
            try:
                if v is not None and v != '':
                    nv = float(v)
                    numeric_vals.append(nv)
            except Exception:
                continue
        entry = {"count_rows": len(recs)}
        if numeric_vals:
            entry.update({
                "sum": sum(numeric_vals),
                "min": min(numeric_vals),
                "max": max(numeric_vals),
                "mean": mean(numeric_vals),
            })
        summary[m] = entry
        
        if m == 'object_detection':
            det_count = entry.get('count_rows', 0)
            texts.append(f"There were {det_count} object detections in the queried time range.")
        elif m == 'scene_event':
            person_vals = []
            for r in recs:
                if r.get('_field') == 'person_count':
                    try:
                        person_vals.append(int(float(r.get('_value') or 0)))
                    except Exception:
                        pass
            if person_vals:
                total = sum(person_vals)
                texts.append(f"Total person_count across events: {total}.")
            else:
                texts.append(f"There were {len(recs)} scene_event rows returned.")
        else:
            texts.append(f"Query returned {len(recs)} rows for measurement '{m}'.")

    human = ' '.join(texts[:3]) if texts else f"Query returned {len(rows)} rows across {len(measurements)} measurements."
    return summary, human


@csrf_exempt
def nlq_view(request):
    """
    NLQ API endpoint.
    
    POST /api/v1/nlq/
    {
        "prompt": "show recent scene events"
    }
    
    Returns:
    {
        "prompt": "...",
        "flux": "...",
        "csv": "...",
        "summary": {...},
        "text": "..."
    }
    """
    if request.method != "POST":
        return HttpResponseBadRequest(
            json.dumps({"error": "POST required"}),
            content_type="application/json"
        )
    
    try:
        data = json.loads(request.body.decode() or "{}")
        prompt = data.get("prompt") or data.get("q") or data.get("query")
        
        if not prompt:
            return HttpResponseBadRequest(
                json.dumps({"error": "missing 'prompt' field"}),
                content_type="application/json"
            )
        
        logger.info(f"Received NLQ request: {prompt}")
        
        # Try LLM service first
        flux = None
        llm_summary = None
        
        flux, llm_summary = translate_with_llm_service(prompt)
        
        # Fallback to rule-based if LLM service fails
        if not flux:
            logger.info("LLM service unavailable, using rule-based translation")
            flux = rule_based_translate(prompt)
        
        # Execute query
        csv = run_flux(flux)
        
        # Log raw CSV for debugging
        logger.info(f"NLQ CSV result length: {len(csv)} bytes")
        
        # Parse and summarize
        text = llm_summary  # Use LLM service summary if available
        if not text:
            try:
                rows = parse_flux_csv(csv)
                summary, text = summarize_records(rows)
            except Exception as e:
                summary, text = {}, "Could not summarize results; returning raw CSV."
                logger.exception(f"Error summarizing NLQ csv: {e}")
        else:
            # Parse for summary dict
            try:
                rows = parse_flux_csv(csv)
                summary, _ = summarize_records(rows)
            except Exception:
                summary = {}

        return JsonResponse({
            "prompt": prompt,
            "flux": flux,
            "csv": csv,
            "summary": summary,
            "text": text
        })
        
    except requests.HTTPError as e:
        logger.exception(f"InfluxDB error: {e}")
        return JsonResponse({
            "error": "influx-error",
            "detail": str(e),
            "status_code": getattr(e.response, 'status_code', 500)
        }, status=502)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return JsonResponse({
            "error": "server-error",
            "detail": str(e)
        }, status=500)
