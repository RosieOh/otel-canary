"""Cohort view: what happened to outsider PRs opened 30-90 days ago (fork PRs, non-maintainer, non-bot)."""
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pr_speed as ps

EXTRA = [
    # TypeScript
    "vercel/ai", "google-gemini/gemini-cli", "modelcontextprotocol/typescript-sdk", "langfuse/langfuse",
    "cline/cline", "continuedev/continue",
    # Rust
    "astral-sh/uv", "astral-sh/ruff", "tauri-apps/tauri", "zed-industries/zed", "biomejs/biome",
    "oxc-project/oxc", "qdrant/qdrant", "pola-rs/polars", "tokio-rs/tokio",
    # Python / Java extras
    "pydantic/pydantic", "fastapi/fastapi", "langchain4j/langchain4j", "spring-projects/spring-ai",
]
REPOS = ps.REPOS + EXTRA
C_START, C_END = date(2026, 6, 30), date(2026, 8, 28)  # every PR in the cohort is >= 30 days old

ps.SEARCH = """query($q:String!,$n:Int!,$c:String){search(query:$q,type:ISSUE,first:$n,after:$c){
issueCount pageInfo{hasNextPage endCursor}
nodes{... on PullRequest{number createdAt mergedAt closedAt state isCrossRepository authorAssociation author{login __typename}}}}}"""


def analyze(repo):
    meta = ps.http(f"https://api.github.com/repos/{repo}")
    name = meta["full_name"]
    prs = ps.fetch(f"repo:{name} is:pr", "created", C_START, C_END)
    humans = [p for p in prs if not ps.is_bot(p)]
    outsiders = [p for p in humans if p["authorAssociation"] not in ps.MAINTAINER and p["isCrossRepository"]]
    per_author = {}
    for p in outsiders:
        per_author[p["author"]["login"]] = per_author.get(p["author"]["login"], 0) + 1
    # newcomer proxy: outsiders who opened <= 3 PRs in the cohort window (drops prolific regulars and PR spammers)
    occ = [p for p in outsiders if per_author[p["author"]["login"]] <= 3]
    n = len(occ)
    days = lambda p: (ps.ts(p["mergedAt"]) - ps.ts(p["createdAt"])).total_seconds() / 86400
    merged = [p for p in occ if p["mergedAt"]]
    frac = lambda k: round(k / n, 2) if n else None
    gfi = f'repo:{name} is:issue is:open label:"good first issue","good-first-issue","help wanted"'
    return {
        "repo": name, "lang": meta.get("language"), "stars": meta["stargazers_count"],
        "prs_all": len(prs), "prs_human": len(humans), "n_occ": n, "occ_authors": sum(v <= 3 for v in per_author.values()),
        "merged": frac(len(merged)),
        "m7": frac(sum(days(p) <= 7 for p in merged)),
        "m14": frac(sum(days(p) <= 14 for p in merged)),
        "closed": frac(sum(1 for p in occ if p["state"] == "CLOSED")),
        "open": frac(sum(1 for p in occ if p["state"] == "OPEN")),
        "ttm_med": round(statistics.median(map(days, merged)), 1) if merged else None,
        "gfi_unassigned": ps.count(f"{gfi} no:assignee"),
    }


def main(out_path):
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for repo, fut in [(r, ex.submit(analyze, r)) for r in REPOS]:
            try:
                results.append(fut.result())
                print(f"done {repo}", file=sys.stderr, flush=True)
            except Exception as e:
                results.append({"repo": repo, "error": str(e)[:300]})
                print(f"FAIL {repo}: {e}", file=sys.stderr, flush=True)
    json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
