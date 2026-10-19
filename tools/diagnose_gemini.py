"""Check Gemini endpoint connectivity without using/sending an API key.

Uses the current environment's network settings unchanged. Prints proxy presence
and hostname only, never credentials or full URLs from proxy environment values.
"""
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import getproxies, urlopen


def main():
    result = {"target": "generativelanguage.googleapis.com", "credentials_sent": False,
              "network_settings_modified": False, "proxies": {}}
    for kind, value in getproxies().items():
        if kind in ("http", "https", "all"):
            parsed = urlparse(value)
            result["proxies"][kind] = {"configured": True, "host": parsed.hostname}
    try:
        addresses = socket.getaddrinfo(result["target"], 443, type=socket.SOCK_STREAM)
        result["dns"] = {"status": "ok", "address_count": len(addresses)}
    except OSError as exc:
        result["dns"] = {"status": "error", "errno": exc.errno, "winerror": getattr(exc, "winerror", None)}
    start = time.perf_counter()
    try:
        with urlopen("https://generativelanguage.googleapis.com/", timeout=15) as response:
            result["https"] = {"reachable": True, "http_status": response.status}
    except HTTPError as exc:
        result["https"] = {"reachable": True, "http_status": exc.code,
                           "note": "Any HTTP status proves endpoint response, not model/key access"}
    except (URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        result["https"] = {"reachable": False, "error_type": type(reason).__name__,
                           "errno": getattr(reason, "errno", None), "winerror": getattr(reason, "winerror", None)}
    result["latency_seconds"] = time.perf_counter() - start
    print(json.dumps(result, indent=2))
    return 0 if result["https"]["reachable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
