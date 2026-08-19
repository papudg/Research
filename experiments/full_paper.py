"""
Full 80-mark CBSE Class X paper: B0 vs B1, per-section with cross-section uniqueness.
Section E = proper 3x4 case-study (bank now has 4 four-mark case-study items).
Difficulty metric = SUM of per-section deviations (each vs its own Delta) -- the quantity B1
actually optimizes -- so the comparison is fair.
"""
from generate import load_bank, chapters_of, chapter, bloom, diff, solve_b0, solve_b1
from collections import Counter
import time

BANK=load_bank(); CHAP=chapters_of(BANK); BYID={q['id']:q for q in BANK}
RU={'Remembering','Understanding'}; APP={'Applying'}; AEC={'Analysing','Evaluating','Creating'}
print("bank:",len(BANK),"| chapters:",sorted(CHAP))
print("4-mark questions:",[q['id'] for q in BANK if int(q['marks'])==4])

from itertools import combinations as _comb
def feasible_W(tier, K):
    pool=[int(q['time']) for q in BANK if int(q['marks'])==tier and chapter(q,CHAP) is not None]
    if len(pool) <= 12:   # small tier: pick a time-sum actually achievable by some K-subset
        sums=Counter(sum(c) for c in _comb(pool,K))
        return sums.most_common(1)[0][0]
    return K*Counter(pool).most_common(1)[0][0]   # large tier: mode*K

# name, K, M, marks_tier  (M & K force the tier)
SECTIONS=[('A',20,20,1),('B',5,10,2),('C',6,18,3),('D',4,20,5),('E',3,12,4)]
COVER=sorted(CHAP)

def diff_target(K):
    prof=[3,6,5,3,2,1,0]; s=sum(prof)
    raw=[max(0,round(p*K/s)) for p in prof]
    while sum(raw)<K: raw[1]+=1
    while sum(raw)>K:
        for i in range(6,0,-1):
            if raw[i]>0: raw[i]-=1; break
    return {b+1:raw[b] for b in range(7)}
def bloom_target(K):
    ru=round(0.54*K); app=round(0.24*K); return {'RU':ru,'APP':app,'AEC':K-ru-app}
def sec_deviation(sel, delta):
    bc=Counter(diff(BYID[i]) for i in sel)
    return sum(abs(bc.get(b,0)-delta[b]) for b in delta)

def generate_paper(solver):
    used=set(); secs={}; total_t=0.0; secD={}
    for name,K,M,tier in SECTIONS:
        W=feasible_W(tier,K); delta=diff_target(K); bt=bloom_target(K)
        t=time.time()
        if solver=='B0':
            sel,st=solve_b0(BANK,K,M,W,set(CHAP),CHAP,marks_tier=tier,exclude=used)
            if sel: secD[name]=sec_deviation(sel,delta)
        else:
            r,st=solve_b1(BANK,K,M,W,set(CHAP),CHAP,delta,COVER,bt,marks_tier=tier,exclude=used)
            sel=r['sel'] if r else None
            if r: secD[name]=r['Dstar']
        total_t+=time.time()-t
        if sel is None:
            print(f"  {solver} section {name}: INFEASIBLE ({st})"); return None
        secs[name]=sel; used|=set(sel)
    return secs,total_t,secD

def paper_metrics(sections, secD):
    ids=[i for s in sections.values() for i in s]
    dh=Counter(diff(BYID[i]) for i in ids)
    bl=Counter(bloom(BYID[i]) for i in ids)
    groups={'RU':sum(bl.get(b,0) for b in RU),'APP':sum(bl.get(b,0) for b in APP),'AEC':sum(bl.get(b,0) for b in AEC)}
    cov=set(chapter(BYID[i],CHAP) for i in ids)
    K=len(ids); bt=bloom_target(K)
    bldev=sum(abs(groups[g]-bt[g]) for g in bt)
    return {'K':K,'marks':sum(int(BYID[i]['marks']) for i in ids),
            'D_persec':sum(secD.values()),'secD':secD,
            'diff_hist':{b:dh.get(b,0) for b in range(1,8)},
            'bloom':groups,'bloom_target':bt,'bloom_dev':bldev,
            'coverage':f"{len(cov)}/{len(CHAP)}"}

print("\n=== Full 80-mark paper: B0 vs B1 ===")
for solver in ('B0','B1'):
    out=generate_paper(solver)
    if out is None: print(f"\n{solver}: failed"); continue
    secs,t,secD=out; m=paper_metrics(secs,secD)
    print(f"\n{solver}: K={m['K']} marks={m['marks']} time={t:.2f}s | "
          f"D(per-section sum)={m['D_persec']}  bloom_dev={m['bloom_dev']}  coverage={m['coverage']}")
    print("   per-section D:",m['secD'])
    print("   bloom groups:",m['bloom']," target(54/24/22):",m['bloom_target'])
    print("   difficulty hist:",m['diff_hist'])
