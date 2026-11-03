"""_fal.py: shared helper so the skill scripts can call fal.ai through the `fal` tool's own code.

Not run on its own. Scripts import it:
    from _fal import call, upload

It loads tools/fal.py (the same code behind the `fal` command), so uploads, the queue API,
the FAL_KEY check and the cost log in Logs/fal.csv all behave exactly like `fal run`.
Lookup order: $MA_FAL_TOOL, the `fal` wrapper on PATH, then <repo>/tools/fal.py.
"""
import importlib.util, os, re, shutil, sys, time

_mod = None


def tool():
    global _mod
    if _mod is not None:
        return _mod
    cands = [os.environ.get("MA_FAL_TOOL")]
    w = shutil.which("fal")
    if w:
        try:
            m = re.search(r'"([^"]+fal\.py)"', open(w).read())
            cands.append(m.group(1) if m else None)
        except (OSError, UnicodeDecodeError):
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.normpath(os.path.join(here, "..", "..", "..", "..", "tools", "fal.py")))
    for c in cands:
        if c and os.path.isfile(c):
            spec = importlib.util.spec_from_file_location("fal_tool", c)
            _mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_mod)
            return _mod
    sys.exit("Could not find the fal tool (tools/fal.py). Run this inside the motion agent, or set MA_FAL_TOOL.")


def upload(path):
    """Local file -> public fal CDN URL (reuses the URL if fal already made or uploaded this file)."""
    return tool().to_url("@" + path)


def call(endpoint, inp, timeout=900):
    """Submit to the fal queue, wait, return the result JSON. Logs the cost like `fal run`."""
    fal = tool()
    rid, info = fal.submit(endpoint, inp)
    print(f"  {endpoint}: request {rid}", file=sys.stderr, flush=True)
    t0, last = time.time(), ""
    while True:
        s, r = fal.http("GET", info["status_url"], timeout=60)
        st = r.get("status", "") if isinstance(r, dict) else ""
        if st != last:
            print(f"  status: {st} ({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
            last = st
        if s in (200, 202) and st == "COMPLETED":
            if r.get("error"):
                sys.exit(f"{endpoint} failed: {r.get('error_type', '')} {r.get('error')}")
            break
        if s not in (200, 202, 429) and s < 500:
            sys.exit(f"{endpoint} status check failed ({s}): {str(r)[:400]}")
        if time.time() - t0 > timeout:
            sys.exit(f"{endpoint} is still running after {timeout}s. Request id: {rid} (continue with: fal wait {rid})")
        time.sleep(3)
    s, result = fal.http("GET", info["response_url"], timeout=120)
    if s != 200:
        sys.exit(f"{endpoint}: could not fetch the result ({s}): {str(result)[:400]}")
    cost, how = fal.estimate_cost(info.get("price"), inp, [], result)
    fal.log_cost(endpoint, rid, cost, [], how)
    return result


def fetch(url, out):
    """Download a result URL to a local path."""
    import urllib.request
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "claude-motion-agent/1.0"}), timeout=300) as r, \
            open(out, "wb") as f:
        shutil.copyfileobj(r, f)
    tool().remember_urls([(out, url)])
    return out
