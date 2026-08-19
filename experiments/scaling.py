"""RQ2 (Cost/Scaling): synthetic pools (bootstrap from the 475-bank) at N=100..10000.
Time B0 vs B1 on a fixed Section-A blueprint (K=20, M=20, 1-mark). Median of 3 seeds."""
import random, time
from generate import load_bank, chapters_of, solve_b0, solve_b1

BANK=load_bank(); CHAP=chapters_of(BANK)
DELTA={1:3,2:6,3:5,4:3,5:2,6:1,7:0}; BT={'RU':11,'APP':5,'AEC':4}
K,M,W=20,20,40

def gen_pool(N, rng):
    return [{'id':f's{i}','marks':q['marks'],'time':q['time'],'difficulty':q['difficulty'],'tags':q['tags']}
            for i,q in enumerate(rng.choices(BANK,k=N))]

def med(fn, reps=3):
    ts=[]
    for _ in range(reps):
        t=time.time();
        try: fn()
        except Exception: pass
        ts.append(time.time()-t)
    return sorted(ts)[len(ts)//2]

print("RQ2 scaling: Section A (K=20, M=20, 1-mark) on synthetic pools")
print(f"{'N':>7} {'1-mark pool':>11} {'B0 med(s)':>10} {'B1 med(s)':>10} {'B1/B0':>7} {'B0 status':>10}")
res=[]
for N in [100,500,1000,5000,10000]:
    rng=random.Random(7); pool=gen_pool(N,rng)
    n1=sum(1 for q in pool if int(q['marks'])==1)
    def b0():
        for sd in (1,2,3):
            sel,st=solve_b0(pool,K,M,W,set(CHAP),CHAP,marks_tier=1,seed=sd)
            if sel is not None: return st
        return 'INFEASIBLE'
    def b1():
        r,st=solve_b1(pool,K,M,W,set(CHAP),CHAP,DELTA,sorted(CHAP),BT,marks_tier=1)
        return st
    stb=b0(); t0=med(b0); t1=med(b1)
    ratio=t1/t0 if t0>0 else 0
    res.append((N,n1,t0,t1,ratio))
    print(f"{N:7} {n1:11} {t0:10.3f} {t1:10.3f} {ratio:7.2f} {str(stb):>10}")
import json

from icaa.paths import results_path
json.dump([{'N':r[0],'pool_1mark':r[1],'b0_s':r[2],'b1_s':r[3],'ratio':r[4]} for r in res],
          open(results_path('results_scaling.json'), 'w'), indent=1)
print("\nsaved results_scaling.json")
