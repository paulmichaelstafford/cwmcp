"""Query Grafana Loki for cwbe log lines — primarily for debugging
`/chapters/from-marks` failures (scraping `sourceAudioBlobName` and
`translationsBlobName` from a failed job's log window)."""
from __future__ import annotations

import time

import httpx


def query_logs(
    grafana_url: str,
    grafana_user: str,
    grafana_password: str,
    *,
    job_id: str | None = None,
    filter_text: str | None = None,
    logql: str | None = None,
    minutes_back: int = 30,
    limit: int = 500,
    container: str = "cwbe",
) -> list[dict]:
    """
    Returns a newest-first list of `{"timestamp": "<ns>", "line": "<log>"}`.

    Query modes (mutually exclusive):
      - `job_id`      → `{container="cwbe"} |= "<job_id>"` — all lines for one job.
      - `filter_text` → `{container="cwbe"} |= "<text>"`  — recent lines containing `<text>`.
      - `logql`       → raw LogQL, used verbatim (caller responsible for escaping).
      - none of the above → `{container="cwbe"}` — all recent lines (noisy).
    """
    if not grafana_user or not grafana_password:
        raise ValueError(
            "grafana_user and grafana_password must be set in ~/.cwmcp/config.properties "
            "(see config.example.properties)"
        )

    if logql is None:
        base = f'{{container="{container}"}}'
        if job_id:
            logql = f'{base} |= "{job_id}"'
        elif filter_text:
            # Escape embedded quotes in the user-supplied text.
            safe = filter_text.replace("\\", "\\\\").replace('"', '\\"')
            logql = f'{base} |= "{safe}"'
        else:
            logql = base

    now_ns = int(time.time() * 1_000_000_000)
    start_ns = now_ns - minutes_back * 60 * 1_000_000_000
    url = (
        f"{grafana_url.rstrip('/')}"
        "/api/datasources/proxy/uid/loki/loki/api/v1/query_range"
    )
    params = {
        "query": logql,
        "start": str(start_ns),
        "end": str(now_ns),
        "limit": str(limit),
        "direction": "backward",
    }

    resp = httpx.get(
        url,
        params=params,
        auth=(grafana_user, grafana_password),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    entries: list[dict] = []
    for stream in payload.get("data", {}).get("result", []):
        for ts, line in stream.get("values", []):
            entries.append({"timestamp": ts, "line": line})

    # Loki returns entries grouped by stream; merge + sort newest-first.
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries
