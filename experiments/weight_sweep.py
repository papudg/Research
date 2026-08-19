"""B2 weight-sweep: show B2's quality is weight-dependent (B1 needs no tuning)."""
from baselines import (BANK, CHAP, BYID, SECTIONS, COVER, feasible_W, diff_target,
                       bloom_target, sec_dev, solve_b2, metrics)

def gen_b2(wd,wc,wb):
    used=set(); secs={}; D=0
    for name,K,M,tier in SECTIONS:
        W=feasible_W(tier,K); delta=diff_target(K); bt=bloom_target(K)
        sel=solve_b2(BANK,K,M,W,set(CHAP),CHAP,delta,COVER,bt,tier=tier,exclude=used,wd=wd,wc=wc,wb=wb)
        if sel is None: return None
        secs[name]=sel; used|=set(sel); D+=sec_dev(sel,delta)
    return secs,D

print("B2 weight sweep (wc=1 fixed).  B1 (no tuning): D=22, bloom_dev=16")
print(f"{'wd':>5} {'wb':>5} | {'D':>3} {'bloom_dev':>9} {'bloom(RU/APP/AEC)':>22}")
Ds=[]; Bs=[]
for wd in [1,3,10]:
    for wb in [1,3,10]:
        out=gen_b2(wd,1,wb)
        if out is None: print(f"{wd:5} {wb:5} | INFEASIBLE"); continue
        secs,D=out; bldev,cov,groups,bt=metrics(secs)
        Ds.append(D); Bs.append(bldev)
        print(f"{wd:5} {wb:5} | {D:3} {bldev:9} {str(groups):>22}")
print(f"\nB2 across weights: D in [{min(Ds)},{max(Ds)}], bloom_dev in [{min(Bs)},{max(Bs)}]  (9 weight settings)")
print("B1 fixed:          D=22, bloom_dev=16  (single run, no weight selection)")
