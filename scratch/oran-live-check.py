"""Read-only live-bundle check untuk dashboard NodePort di node core testbed."""
import urllib.request, ssl, re, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HOST = "10.91.2.151"
PORT = 30090
out = {}
for scheme in ("https", "http"):
    url = "%s://%s:%s/" % (scheme, HOST, PORT)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dev-healthcheck"})
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            body = r.read().decode("utf-8", "replace")
            m = re.search(r'assets/index-[^"]+\.js', body)
            out[scheme] = {"status": r.status, "bundle": m.group(0) if m else None, "bytes": len(body)}
            break
    except Exception as e:
        out[scheme] = {"error": "%s: %s" % (type(e).__name__, e)}

print(json.dumps(out))
