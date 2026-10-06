#!/usr/bin/env python3
"""Probe local UI without displaying HTML or injected session credentials."""
import time
import urllib.request
import urllib.error
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(90):
    try:
        with opener.open("http://127.0.0.1:8000/canvas", timeout=3) as response:
            assert response.status == 200
            body = response.read(200000)
            if b"<html" not in body.lower():
                raise ValueError("Expected UI HTML")
        print("Local OpenHands UI reachable (HTTP 200).")
        break
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        if attempt == 89:
            raise SystemExit("UI not ready: inspect task openhands:logs.")
        time.sleep(2)
