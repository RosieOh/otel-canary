"""Find open, unclaimed starter issues: no assignee, no open linked PR, no recent 'I'll take this' comment."""
import json
import re
import sys
import time
from datetime import datetime, timezone

import pr_speed as ps

TARGETS = {
    "goreleaser/goreleaser": ["good-first-issue", "help wanted", "bug"],
    "open-telemetry/opentelemetry-collector-contrib": ["good first issue", "help wanted"],
    "astral-sh/ruff": ["help wanted"],
    "tokio-rs/tokio": ["E-help-wanted"],
    "Arize-ai/phoenix": ["good student issue", "help wanted", "good first issue"],
    "langchain4j/langchain4j": ["good first issue"],
    "prometheus/prometheus": ["good first issue", "help wanted"],
    "mark3labs/mcp-go": None,  # no starter labels in use: scan recent issues instead
}
NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
CLAIM = re.compile(r"(work(ing)? on (this|it)|take (this|it)|pick (this|it) up|assign (this|it)? ?(to )?me|"
                   r"i('d| would) like to (work|contribute|help|fix|take)|can i (work|take|help|try|fix)|"
                   r"may i|i('ll| will) (fix|take|work|submit|open)|i('m| am) (working|interested|looking))", re.I)
MAINTAINER = {"MEMBER", "OWNER", "COLLABORATOR"}

Q = """query($owner:String!,$name:String!,$labels:[String!],$c:String){repository(owner:$owner,name:$name){
issues(first:50,after:$c,states:OPEN,labels:$labels,orderBy:{field:UPDATED_AT,direction:DESC}){
pageInfo{hasNextPage endCursor}
nodes{number title url createdAt updatedAt authorAssociation author{login} bodyText
assignees(first:3){totalCount}
labels(first:12){nodes{name}}
comments(last:30){totalCount nodes{author{login} authorAssociation createdAt bodyText}}
closedByPullRequestsReferences(first:5,includeClosedPrs:true){nodes{number state}}
timelineItems(last:30,itemTypes:[CROSS_REFERENCED_EVENT,CONNECTED_EVENT]){nodes{
 ... on CrossReferencedEvent{source{... on PullRequest{number state createdAt}}}
 ... on ConnectedEvent{subject{... on PullRequest{number state createdAt}}}}}}}}}"""


def gql(variables):
    for i in range(6):
        data = ps.http("https://api.github.com/graphql", json.dumps({"query": Q, "variables": variables}).encode())
        if data.get("data") and data["data"].get("repository"):
            return data["data"]["repository"]
        time.sleep(10 * (i + 1))
    raise RuntimeError(str(data.get("errors"))[:300])


def days(ts):
    return (NOW - ps.ts(ts)).days


def scan(repo, labels):
    owner, name = repo.split("/")
    out, cursor = [], None
    for _ in range(3):  # up to 150 most recently updated issues per repo
        r = gql({"owner": owner, "name": name, "labels": labels, "c": cursor})["issues"]
        out += r["nodes"]
        if not r["pageInfo"]["hasNextPage"]:
            break
        cursor = r["pageInfo"]["endCursor"]
        time.sleep(1)
    rows = []
    for it in out:
        prs = [n.get("source") or n.get("subject") for n in it["timelineItems"]["nodes"]]
        prs = [p for p in prs if p and "state" in p] + it["closedByPullRequestsReferences"]["nodes"]
        open_prs = sorted({p["number"] for p in prs if p["state"] == "OPEN"})
        claims = [c for c in it["comments"]["nodes"] if c["authorAssociation"] not in MAINTAINER
                  and CLAIM.search(c["bodyText"] or "") and days(c["createdAt"]) <= 60]
        maint = [c for c in it["comments"]["nodes"] if c["authorAssociation"] in MAINTAINER]
        rows.append({
            "repo": repo, "n": it["number"], "title": it["title"][:95], "url": it["url"],
            "age": days(it["createdAt"]), "upd": days(it["updatedAt"]),
            "assigned": it["assignees"]["totalCount"], "open_prs": open_prs,
            "all_prs": sorted({p["number"] for p in prs}), "claims": len(claims),
            "comments": it["comments"]["totalCount"],
            "maint_touch": it["authorAssociation"] in MAINTAINER or bool(maint),
            "labels": [l["name"] for l in it["labels"]["nodes"]], "body_len": len(it["bodyText"] or ""),
        })
    return rows


if __name__ == "__main__":
    allrows = []
    for repo, labels in TARGETS.items():
        rows = scan(repo, labels)
        free = [r for r in rows if not r["assigned"] and not r["open_prs"] and not r["claims"] and r["upd"] <= 240
                and (labels is not None or r["age"] <= 90)]
        print(f"=== {repo}: scanned {len(rows)}, unclaimed {len(free)}", flush=True)
        for r in sorted(free, key=lambda r: (not r["maint_touch"], r["upd"]))[:14]:
            print(f"  #{r['n']} age={r['age']}d upd={r['upd']}d c={r['comments']} maint={'Y' if r['maint_touch'] else '-'} "
                  f"prs={r['all_prs'] or '-'} | {r['title']}", flush=True)
        allrows += rows
        time.sleep(2)
    json.dump(allrows, open(sys.argv[1], "w"), indent=1)
