#!/usr/bin/env python3
"""Build the SCRAPER_PROXY URL from USER_PROXY / PASSWORD_PROXY in .env.

Reads .env WITHOUT shell `source` (the password can contain characters that
break sourcing) and URL-encodes the credentials so special chars are safe in
the proxy URL's userinfo.

    export SCRAPER_PROXY="$(uv run python3 scripts/mkproxy.py)"
    uv run tiki-scraper --concurrency 5 --batch-size 200

Optional arg overrides host:port (default Decodo rotating gateway):
    uv run python3 scripts/mkproxy.py gate.decodo.com:10001
"""
import sys
import urllib.parse

env = {}
for line in open(".env"):
    line = line.rstrip("\n")
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v

host = sys.argv[1] if len(sys.argv) > 1 else "gate.decodo.com:7000"
u = urllib.parse.quote(env["USER_PROXY"], safe="")
p = urllib.parse.quote(env["PASSWORD_PROXY"], safe="")
print(f"http://{u}:{p}@{host}")
