"""Fresh-issue radar: open issues from the last few days with no assignee, no linked PR and no claim anywhere."""
import json
import re
import sys
import time
from datetime import datetime, timezone

import pr_speed as ps

REPOS = {
    # repo: toolchain needed locally
    "Arize-ai/phoenix": "py/ts", "Arize-ai/openinference": "py/ts/java", "microsoft/agent-framework": "py/.net",
    "comet-ml/opik": "py/ts/java", "huggingface/huggingface_hub": "py", "huggingface/transformers": "py",
    "pydantic/pydantic": "py", "mlflow/mlflow": "py/ts", "open-telemetry/opentelemetry-python": "py",
    "open-telemetry/opentelemetry-python-contrib": "py", "langchain4j/langchain4j": "java",
    "goreleaser/goreleaser": "go", "mark3labs/mcp-go": "go", "modelcontextprotocol/go-sdk": "go",
    "open-telemetry/opentelemetry-collector-contrib": "go", "envoyproxy/gateway": "go", "prometheus/prometheus": "go",
    "grafana/alloy": "go", "argoproj/argo-cd": "go", "kgateway-dev/kgateway": "go",
    "astral-sh/ruff": "rust", "astral-sh/uv": "rust", "tokio-rs/tokio": "rust", "biomejs/biome": "rust",
    "zed-industries/zed": "rust", "oxc-project/oxc": "rust",
}
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
NOW = datetime.now(timezone.utc)
CLAIM = re.compile(
    r"(i('d| would) (like|love) to (work|investigate|take|fix|contribute|help|tackle|pick)|"
    r"(happy|glad) to (work|fix|submit|open|take|contribute|send)|i can (take|work|fix|submit|open|send)|"
    r"i('ll| will) (fix|take|work|submit|open|investigate|send|put up)|(working|work) on (this|it|a fix)|"
    r"have a (fix|branch|pr|patch)|pr (incoming|coming|soon)|opened #\d+|assign(ed)? (this|it )?(issue )?to me|"
    r"let me (take|work|fix)|can i (work|take|help|try|fix|pick)|may i|i('m| am) (working|interested|looking into))",
    re.I)
Q = """query($q:String!,$c:String){search(query:$q,type:ISSUE,first:50,after:$c){pageInfo{hasNextPage endCursor}
nodes{... on Issue{number title url createdAt authorAssociation author{login} bodyText
labels(first:12){nodes{name}} comments(first:40){totalCount nodes{author{login} authorAssociation bodyText}}
timelineItems(first:40,itemTypes:[CROSS_REFERENCED_EVENT,CONNECTED_EVENT]){nodes{
 ... on CrossReferencedEvent{source{... on PullRequest{number}}}
 ... on ConnectedEvent{subject{... on PullRequest{number}}}}}}}}}"""


def run(repo):
    q = f"repo:{repo} is:issue is:open no:assignee created:>={SINCE}"
    nodes, cursor = [], None
    while True:
        data = ps.http("https://api.github.com/graphql", json.dumps({"query": Q, "variables": {"q": q, "c": cursor}}).encode())
        s = data["data"]["search"]
        nodes += [n for n in s["nodes"] if n]
        if not s["pageInfo"]["hasNextPage"]:
            return nodes
        cursor = s["pageInfo"]["endCursor"]


out = []
for repo, tool in REPOS.items():
    try:
        issues = run(repo)
    except Exception as e:
        print(f"FAIL {repo}: {e}", file=sys.stderr)
        continue
    for it in issues:
        prs = [n.get("source") or n.get("subject") for n in it["timelineItems"]["nodes"]]
        if any(p and "number" in p for p in prs):
            continue
        texts = [it["bodyText"] or ""] + [c["bodyText"] or "" for c in it["comments"]["nodes"]]
        if any(CLAIM.search(t) for t in texts):
            continue
        labels = [l["name"] for l in it["labels"]["nodes"]]
        if {"good student issue", "agent-in-progress", "duplicate", "question", "wontfix", "invalid"} & set(labels):
            continue
        maint = it["authorAssociation"] in ps.MAINTAINER or any(
            c["authorAssociation"] in ps.MAINTAINER for c in it["comments"]["nodes"])
        hours = int((NOW - ps.ts(it["createdAt"])).total_seconds() // 3600)
        out.append((repo, tool, it["number"], hours, it["comments"]["totalCount"], maint, labels, it["title"]))
    time.sleep(1.5)

for repo, tool, n, h, c, maint, labels, title in sorted(out, key=lambda r: (r[0], r[3])):
    print(f"{repo}#{n} [{tool}] {h}h c={c} maint={'Y' if maint else '-'} [{','.join(labels)[:45]}] {title[:90]}")
print(f"total unclaimed fresh issues: {len(out)}", file=sys.stderr)
