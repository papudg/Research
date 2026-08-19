"""RQ3 (tightness sweep by eligible-chapter subset size) + RQ5 (CR_soft compliance, B0 vs B1)."""
import random, numpy as np
from scipy.stats import wilcoxon
from baselines import (BANK, CHAP, BYID, SECTIONS, feasible_W, diff_target,
                       bloom_target, sec_dev, solve_b0, solve_b1, metrics)

def rand_delta(K, rng):
    w=[4,5,4,3,2,1,0.3]; r=[rng.random()*x for x in w]; s=sum(r)
    raw=[int(K*x/s) for x in r]; i=0
    while sum(raw)<K: raw[i%7]+=1; i+=1
    while sum(raw)>K:
        j=rng.randint(0,6)
        if raw[j]>0: raw[j]-=1
    return {b+1:raw[b] for b in range(7)}

def run(method, elig, delta, bt, rng):
    used=set(); secs={}; D=0
    for name,K,M,tier in SECTIONS:
        W=feasible_W(tier,K)
        if method=='b0':
            sel,_=solve_b0(BANK,K,M,W,elig,CHAP,marks_tier=tier,exclude=used,seed=rng.randint(1,9999))
        else:
            rr,_=solve_b1(BANK,K,M,W,elig,CHAP,delta[name],list(elig),bt[name],marks_tier=tier,exclude=used)
            sel=rr['sel'] if rr else None
        if sel is None: return None
        secs[name]=sel; used|=set(sel); D+=sec_dev(sel,delta[name])
    return secs,D

KTOT=38
def cr_soft(D, bldev):
    return ((1-min(1,D/(2*KTOT))) + (1-min(1,bldev/(2*KTOT))))/2

rng=random.Random(99); chaps=list(CHAP)
print("=== RQ3: tightness tiers (eligible-chapter subset size; 20 blueprints/tier) ===")
print(f"{'size':>5} {'feas%':>6} {'med D_B0':>9} {'med D_B1':>9} {'med gap':>8}")
cr0L=[];cr1L=[]
for size in [7,6,5,4,3]:
    feas=0; d0s=[]; d1s=[]; gaps=[]
    for _ in range(20):
        elig=set(rng.sample(chaps,size))
        delta={nm:rand_delta(K,rng) for nm,K,M,tier in SECTIONS}
        bt={nm:bloom_target(K) for nm,K,M,tier in SECTIONS}
        g0=run('b0',elig,delta,bt,rng); g1=run('b1',elig,delta,bt,rng)
        if g0 is None or g1 is None: continue
        feas+=1; _,d0=g0; _,d1=g1; d0s.append(d0); d1s.append(d1); gaps.append(d0-d1)
        b0_,_,_,_=metrics(g0[0]); b1_,_,_,_=metrics(g1[0])
        cr0L.append(cr_soft(d0,b0_)); cr1L.append(cr_soft(d1,b1_))
    pct=100*feas/20
    if gaps: print(f"{size:5} {pct:6.0f} {np.median(d0s):9.0f} {np.median(d1s):9.0f} {np.median(gaps):8.0f}")
    else:    print(f"{size:5} {pct:6.0f}   (no feasible pairs)")

print("\n=== RQ5: CR_soft (mean of difficulty-fit and Bloom-fit satisfaction), B0 vs B1 ===")
cr0=np.array(cr0L); cr1=np.array(cr1L)
print(f"feasible pairs: {len(cr0)} | CR_soft median: B0={np.median(cr0):.3f}  B1={np.median(cr1):.3f}")
w=wilcoxon(cr0,cr1,method='approx'); r=abs(getattr(w,'zstatistic',0))/np.sqrt(len(cr0)) if getattr(w,'zstatistic',None) else float('nan')
print(f"paired Wilcoxon p={w.pvalue:.2e}  effect r={r:.2f}  B1 wins {int((cr1>cr0).sum())}/{len(cr0)}")
