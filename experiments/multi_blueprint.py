"""RQ1 statistics: N varied blueprints (random Delta + random eligible-chapter subset 5-7),
B0 vs B1 paired. Paired Wilcoxon + effect size + bootstrap 95% CI on median diff."""
import random, numpy as np
from scipy.stats import wilcoxon
from baselines import (BANK, CHAP, BYID, SECTIONS, feasible_W, diff_target,
                       bloom_target, sec_dev, solve_b0, solve_b1, metrics)

np.random.seed(42)

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

rng=random.Random(42); N=80; chaps=list(CHAP)
d0L=[];d1L=[];b0L=[];b1L=[]; skip=0; tlist=[]
import time
for i in range(N):
    elig=set(rng.sample(chaps, rng.randint(5,7)))
    delta={nm:rand_delta(K,rng) for nm,K,M,tier in SECTIONS}
    bt={nm:bloom_target(K) for nm,K,M,tier in SECTIONS}
    t=time.time()
    g0=run('b0',elig,delta,bt,rng); g1=run('b1',elig,delta,bt,rng)
    tlist.append(time.time()-t)
    if g0 is None or g1 is None: skip+=1; continue
    _,d0=g0; _,d1=g1
    bm0,_,_,_=metrics(g0[0]); bm1,_,_,_=metrics(g1[0])
    d0L.append(d0);d1L.append(d1);b0L.append(bm0);b1L.append(bm1)

d0=np.array(d0L);d1=np.array(d1L);b0=np.array(b0L);b1=np.array(b1L); n=len(d0)
print(f"multi-blueprint: {n} feasible B0/B1 pairs ({skip} infeasible/skipped) of {N}; avg time/pair={np.mean(tlist):.2f}s")
def report(name,a,b):
    diff=a-b; med=np.median(diff); mn=diff.mean()
    try:
        w=wilcoxon(a,b,method='approx'); p=w.pvalue; z=getattr(w,'zstatistic',None); r=abs(z)/np.sqrt(n) if z is not None else float('nan')
    except Exception as e: p=float('nan'); r=float('nan')
    ci=np.percentile([np.median(diff[np.random.choice(n,n)]) for _ in range(3000)],[2.5,97.5])
    wins=int((diff>0).sum()); ties=int((diff==0).sum())
    print(f"{name}: B0 med={np.median(a):.0f} -> B1 med={np.median(b):.0f} | diff median={med:.1f} mean={mn:.1f} | B1 wins {wins}/{n} (ties {ties}) | Wilcoxon p={p:.2e} effect r={r:.2f} | 95% CI med-diff [{ci[0]:.1f},{ci[1]:.1f}]")
report("difficulty D",d0,d1)
report("bloom_dev  ",b0,b1)
