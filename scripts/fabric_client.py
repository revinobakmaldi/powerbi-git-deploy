"""Small client for the Fabric and Power BI REST APIs, with retries and long-running operations.

Two ways to sign in:
- "azcli": a token from `az account get-access-token`. In GitHub Actions, `azure/login` signs in the
  service principal first (federated credential, no secret), so the token is the service principal's.
- "fab": every call goes through the Fabric CLI (`fab api`), signed in as you (`fab auth login`).
  Use this on your own machine.

Retries: only timeouts, 408, 429 and 5xx, with backoff (Retry-After when the service sends it).
A 4xx is never retried: it means the request is wrong, and retrying would hide that.
"""
import json
import subprocess
import time
import urllib.error
import urllib.request

FABRIC = "https://api.fabric.microsoft.com/v1/"
POWERBI = "https://api.powerbi.com/v1.0/myorg/"
RESOURCE = {"fabric": "https://api.fabric.microsoft.com", "powerbi": "https://analysis.windows.net/powerbi/api"}
TRANSIENT = {408, 429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    def __init__(self, status, method, path, body):
        self.status, self.body = status, body
        super().__init__(f"{method.upper()} {path} -> {status}: {json.dumps(body)[:600]}")


class AzCliTransport:
    """Plain HTTPS with a bearer token from the Azure CLI."""

    def __init__(self):
        self._tokens = {}

    def _token(self, audience):
        tok, exp = self._tokens.get(audience, (None, 0))
        if tok and exp - time.time() > 300:
            return tok
        out = subprocess.run(["az", "account", "get-access-token", "--resource", RESOURCE[audience],
                              "--query", "{t:accessToken,e:expires_on}", "-o", "json"],
                             capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        d = json.loads(out.stdout)
        self._tokens[audience] = (d["t"], float(d.get("e") or time.time() + 1800))
        return d["t"]

    def call(self, method, url, body, audience):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method.upper())
        req.add_header("Authorization", "Bearer " + self._token(audience))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, _parse(r.read())
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, _parse(e.read())


class FabTransport:
    """Every call through `fab api`, signed in as the user. Run with stdin closed: fab can hang otherwise."""

    def call(self, method, url, body, audience):
        base = FABRIC if audience == "fabric" else POWERBI
        path = url[len(base):] if url.startswith(base) else url
        cmd = ["fab", "api", path, "-X", method.lower(), "-A", audience, "--show_headers"]
        if body is not None:
            cmd += ["-i", json.dumps(body)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return 408, {}, {"error": "fab api timed out"}
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            return 599, {}, {"error": (r.stdout + r.stderr)[-500:]}
        headers = {k.lower(): v for k, v in (d.get("headers") or {}).items()}
        return int(d.get("status_code", 599)), headers, d.get("text")


def _parse(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")


class Client:
    def __init__(self, auth="azcli", retries=5, log=print):
        self.t = AzCliTransport() if auth == "azcli" else FabTransport()
        self.retries, self.log = retries, log

    def request(self, method, path, body=None, audience="fabric", ok=(200, 201, 202, 204)):
        base = FABRIC if audience == "fabric" else POWERBI
        url = path if path.startswith("https://") else base + path
        for attempt in range(self.retries + 1):
            try:
                status, headers, data = self.t.call(method, url, body, audience)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                status, headers, data = 408, {}, {"error": str(e)}
            if status in ok:
                return status, headers, data
            if status in TRANSIENT and attempt < self.retries:
                wait = float(headers.get("retry-after") or min(60, 2 ** (attempt + 1)))
                self.log(f"  {method.upper()} {path}: {status}, retry {attempt + 1}/{self.retries} in {wait:.0f}s")
                time.sleep(wait)
                continue
            raise ApiError(status, method, path, data)

    def get(self, path, audience="fabric"):
        return self.request("get", path, audience=audience)[2]

    def wait_operation(self, headers, timeout=900):
        """Poll a Fabric long-running operation until it succeeds or fails."""
        op = headers.get("x-ms-operation-id")
        url = headers.get("location") or (FABRIC + f"operations/{op}")
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(float(headers.get("retry-after") or 5))
            _, headers2, d = self.request("get", url)
            state = (d or {}).get("status")
            if state == "Succeeded":
                return d
            if state in ("Failed", "Cancelled"):
                raise RuntimeError(f"operation {op} {state}: {json.dumps(d)[:800]}")
            headers = {**headers, **{k: v for k, v in headers2.items() if k == "retry-after"}}
        raise RuntimeError(f"operation {op} did not finish in {timeout}s")

    def workspace_id(self, name):
        for w in self.get("workspaces").get("value", []):
            if w["displayName"] == name:
                return w["id"]
        raise RuntimeError(f"workspace '{name}' not found, or this identity has no access to it")
