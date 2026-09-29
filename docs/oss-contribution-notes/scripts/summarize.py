import json
import sys

rows = json.load(open(sys.argv[1]))
ok = [r for r in rows if "error" not in r]
for r in rows:
    if "error" in r:
        print("ERROR", r["repo"], r["error"])

# newcomer-relevant view: only repos where outsiders actually get merged (>=10 occasional merges in 60d)
ok.sort(key=lambda r: (r["ttm_med_days"] is None, r["ttm_med_days"] or 0))
hdr = f'{"repo":48} {"lang":10} {"stars":>6} {"occM":>5} {"rate":>5} {"med_d":>6} {"p75_d":>6} {"<=7d":>5} {"open":>5} {"old30":>5} {"gfi":>4} {"gfiU":>4}'
print(hdr)
print("-" * len(hdr))
for r in ok:
    print(f'{r["repo"]:48} {str(r["lang"])[:10]:10} {r["stars"]//1000:>5}k {r["occ_merged"]:>5} {r["occ_merge_rate"]:>5} '
          f'{str(r["ttm_med_days"]):>6} {str(r["ttm_p75_days"]):>6} {str(r["within_7d"]):>5} {r["open_prs"]:>5} '
          f'{r["open_prs_30d_old"]:>5} {r["gfi_open"]:>4} {r["gfi_unassigned"]:>4}')
