"""Measure how fast sizable OSS repos merge PRs from outside contributors (last 60 days)."""
import json
import ssl
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

REPOS = [
    # Python / AI
    "BerriAI/litellm", "langchain-ai/langchain", "langchain-ai/langgraph", "run-llama/llama_index",
    "vllm-project/vllm", "sgl-project/sglang", "huggingface/transformers", "huggingface/huggingface_hub",
    "pydantic/pydantic-ai", "openai/openai-agents-python", "modelcontextprotocol/python-sdk",
    "mlflow/mlflow", "Arize-ai/phoenix", "traceloop/openllmetry", "open-telemetry/opentelemetry-python-contrib",
    "crewAIInc/crewAI", "google/adk-python", "stanfordnlp/dspy", "microsoft/agent-framework",
    "comet-ml/opik", "567-labs/instructor",
    # Go
    "open-telemetry/opentelemetry-go", "open-telemetry/opentelemetry-collector-contrib", "envoyproxy/gateway",
    "theagentrouter/agent-router", "kgateway-dev/kgateway", "kubernetes-sigs/gateway-api-inference-extension",
    "prometheus/prometheus", "grafana/alloy", "goreleaser/goreleaser", "cli/cli", "argoproj/argo-cd",
    "jaegertracing/jaeger", "temporalio/temporal", "milvus-io/milvus", "ollama/ollama",
    "modelcontextprotocol/go-sdk", "mark3labs/mcp-go", "dagger/dagger", "helm/helm", "traefik/traefik",
    "kubernetes/kubernetes",
]

SSL_CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
TOKEN = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
END = date(2026, 9, 27)
START = END - timedelta(days=59)
STALE_CUTOFF = END - timedelta(days=30)
MAINTAINER = {"MEMBER", "OWNER", "COLLABORATOR"}
BOT_LOGINS = {"copilot", "dependabot", "renovate", "github-actions", "mergify", "pre-commit-ci"}

SEARCH = """query($q:String!,$n:Int!,$c:String){search(query:$q,type:ISSUE,first:$n,after:$c){
issueCount pageInfo{hasNextPage endCursor}
nodes{... on PullRequest{number createdAt mergedAt closedAt authorAssociation author{login __typename}}}}}"""


def http(url, body=None, tries=8):
    for i in range(tries):
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90, context=SSL_CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After")
                time.sleep(int(ra) if ra else 8 * (i + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"request failed: {url}")


def gql(query, variables):
    for i in range(6):
        data = http("https://api.github.com/graphql", json.dumps({"query": query, "variables": variables}).encode())
        if data.get("data") and data["data"].get("search") is not None:
            return data["data"]
        time.sleep(8 * (i + 1))
    raise RuntimeError(f"graphql failed: {str(data.get('errors'))[:300]}")


def count(q):
    return gql(SEARCH, {"q": q, "n": 1, "c": None})["search"]["issueCount"]


def fetch(base, field, d1, d2):
    q = f"{base} {field}:{d1.isoformat()}..{d2.isoformat()}"
    if count(q) > 1000 and d1 < d2:
        mid = d1 + (d2 - d1) // 2
        return fetch(base, field, d1, mid) + fetch(base, field, mid + timedelta(days=1), d2)
    out, cursor = [], None
    while True:
        s = gql(SEARCH, {"q": q, "n": 100, "c": cursor})["search"]
        out += [n for n in s["nodes"] if n]
        if not s["pageInfo"]["hasNextPage"]:
            return out
        cursor = s["pageInfo"]["endCursor"]


def is_bot(pr):
    a = pr.get("author")
    if not a:
        return True
    login = a["login"].lower()
    return a["__typename"] == "Bot" or login.endswith("[bot]") or login in BOT_LOGINS or login.endswith("-bot")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def analyze(repo):
    meta = http(f"https://api.github.com/repos/{repo}")
    name = meta["full_name"]
    base = f"repo:{name} is:pr"
    merged = fetch(f"{base} is:merged", "merged", START, END)
    unmerged = fetch(f"{base} is:closed is:unmerged", "closed", START, END)

    ext = lambda p: not is_bot(p) and p["authorAssociation"] not in MAINTAINER
    merged_h = [p for p in merged if not is_bot(p)]
    merged_ext = [p for p in merged_h if ext(p)]
    per_author = {}
    for p in merged_ext:
        per_author[p["author"]["login"]] = per_author.get(p["author"]["login"], 0) + 1
    # "occasional" outsiders: <=3 merged PRs in the window — the closest proxy for a newcomer's experience
    occ = lambda p: ext(p) and per_author.get(p["author"]["login"], 0) <= 3
    occ_merged = [p for p in merged_ext if occ(p)]
    occ_unmerged = [p for p in unmerged if occ(p)]
    ttm = [(ts(p["mergedAt"]) - ts(p["createdAt"])).total_seconds() / 86400 for p in occ_merged]

    gfi = f'repo:{name} is:issue is:open label:"good first issue","good-first-issue","help wanted"'
    return {
        "repo": name, "lang": meta.get("language"), "stars": meta["stargazers_count"], "archived": meta["archived"],
        "merged_human": len(merged_h), "merged_ext": len(merged_ext), "ext_authors": len(per_author),
        "occ_merged": len(occ_merged), "occ_unmerged": len(occ_unmerged),
        "occ_merge_rate": round(len(occ_merged) / max(1, len(occ_merged) + len(occ_unmerged)), 2),
        "ttm_med_days": round(statistics.median(ttm), 1) if ttm else None,
        "ttm_p75_days": round(pct(ttm, 0.75), 1) if ttm else None,
        "within_7d": round(sum(t <= 7 for t in ttm) / len(ttm), 2) if ttm else None,
        "open_prs": count(f"{base} is:open"),
        "open_prs_30d_old": count(f"{base} is:open created:<{STALE_CUTOFF.isoformat()}"),
        "gfi_open": count(gfi),
        "gfi_unassigned": count(f"{gfi} no:assignee"),
    }


def main(out_path):
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for repo, fut in [(r, ex.submit(analyze, r)) for r in REPOS]:
            try:
                results.append(fut.result())
                print(f"done {repo}", file=sys.stderr, flush=True)
            except Exception as e:  # keep going; report the failure
                results.append({"repo": repo, "error": str(e)[:300]})
                print(f"FAIL {repo}: {e}", file=sys.stderr, flush=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
