"""Ablations (A1 difficulty-only, A2 difficulty+coverage, A3 full B1, A4 coverage+bloom w/o difficulty)
and greedy baseline B_G (feasibility solve + greedy difficulty-fit solution hint), on the
representative 80-mark blueprint. """
import time
from generate import cp_model, chapter, diff, bloom, solve_b1
from baselines import (BANK, CHAP, BYID, SECTIONS, COVER, feasible_W, diff_target,
                       bloom_target, sec_dev, metrics, gin)

def build(pool,K,M,W,delta,cover,bt):
    m=cp_model.CpModel()
    x={q['id']:m.NewBoolVar(q['id']) for q in pool}
    m.Add(sum(int(q['marks'])*x[q['id']] for q in pool)==M)
    m.Add(sum(int(q['time'])*x[q['id']] for q in pool)==W)
    m.Add(sum(x[q['id']] for q in pool)==K)
    bands=sorted(delta)
    u={b:m.NewIntVar(0,K,f'u{b}') for b in bands}
    for b in bands:
        bc=sum(x[q['id']] for q in pool if diff(q)==b)
        m.Add(u[b]>=bc-delta[b]); m.Add(u[b]>=delta[b]-bc)
    y={t:m.NewBoolVar(f'y{t}') for t in cover}
    for t in cover: m.Add(y[t]<=sum(x[q['id']] for q in pool if chapter(q,CHAP)==t))
    gnames=sorted(bt); bg={g:m.NewIntVar(0,K,f'bg{g}') for g in gnames}
    for g in gnames:
        gc=sum(x[q['id']] for q in pool if gin(q,g))
        m.Add(bg[g]>=gc-bt[g]); m.Add(bg[g]>=bt[g]-gc)
    return m,x,u,y,bg,bands,gnames

def solve_variant(kind,K,M,W,delta,cover,bt,tier=None,exclude=None):
    excl=set(exclude or [])
    pool=[q for q in BANK if q['id'] not in excl and chapter(q,CHAP) in set(CHAP) and (tier is None or int(q['marks'])==tier)]
    m,x,u,y,bg,bands,gnames=build(pool,K,M,W,delta,cover,bt)
    s=cp_model.CpSolver(); s.parameters.max_time_in_seconds=30; s.parameters.random_seed=1; s.parameters.num_search_workers=1
    if kind=='BG':  # greedy-guided feasibility: hint = top-K items by difficulty-band deficit
        deficit={b:delta.get(b,0) for b in range(1,8)}
        scored=sorted(pool,key=lambda q:-deficit.get(diff(q),0))
        for q in scored[:K]: m.AddHint(x[q['id']],1)
        st=s.Solve(m)
        if st not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None
        return [q['id'] for q in pool if s.Value(x[q['id']])]
    # A1: difficulty only
    m.Minimize(sum(u[b] for b in bands))
    if s.Solve(m) not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None
    if kind=='A1': return [q['id'] for q in pool if s.Value(x[q['id']])]
    Dstar=round(s.ObjectiveValue()); m.Add(sum(u[b] for b in bands)<=Dstar)
    # A2: + coverage
    m.Maximize(sum(y[t] for t in cover)); s2=cp_model.CpSolver(); s2.parameters.max_time_in_seconds=30; s2.parameters.random_seed=1; s2.parameters.num_search_workers=1
    if s2.Solve(m) not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None
    if kind=='A2': return [q['id'] for q in pool if s2.Value(x[q['id']])]
    return None

def solve_a4(K,M,W,delta,cover,bt,tier=None,exclude=None):
    excl=set(exclude or [])
    pool=[q for q in BANK if q['id'] not in excl and chapter(q,CHAP) in set(CHAP) and (tier is None or int(q['marks'])==tier)]
    m,x,u,y,bg,bands,gnames=build(pool,K,M,W,delta,cover,bt)
    m.Maximize(sum(y[t] for t in cover))
    s=cp_model.CpSolver(); s.parameters.max_time_in_seconds=30; s.parameters.random_seed=1; s.parameters.num_search_workers=1
    if s.Solve(m) not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None
    Cstar=round(s.ObjectiveValue()); m.Add(sum(y[t] for t in cover)>=Cstar)
    m.Maximize(-sum(bg[g] for g in gnames))
    s2=cp_model.CpSolver(); s2.parameters.max_time_in_seconds=30; s2.parameters.random_seed=1; s2.parameters.num_search_workers=1
    if s2.Solve(m) not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None
    return [q['id'] for q in pool if s2.Value(x[q['id']])]

def gen(kind):
    used=set(); secs={}; t=0; D=0
    for name,K,M,tier in SECTIONS:
        W=feasible_W(tier,K); delta=diff_target(K); bt=bloom_target(K)
        st=time.time()
        if kind in ('A1','A2','BG'): sel=solve_variant(kind,K,M,W,delta,COVER,bt,tier=tier,exclude=used)
        elif kind=='A4': sel=solve_a4(K,M,W,delta,COVER,bt,tier=tier,exclude=used)
        else:
            r,_=solve_b1(BANK,K,M,W,set(CHAP),CHAP,delta,COVER,bt,marks_tier=tier,exclude=used); sel=r['sel'] if r else None
        t+=time.time()-st
        if sel is None: print(f"  {kind} section {name} INFEASIBLE"); return None
        secs[name]=sel; used|=set(sel); D+=sec_dev(sel,delta)
    return secs,t,D

print(f"{'variant':4s} {'D':>4} {'bloom_dev':>9} {'cov':>5} {'time':>6}")
for kind,label in [('A1','A1 diff-only'),('A2','A2 diff+cov'),('A3','A3 full B1'),('A4','A4 cov+bloom, no diff'),('BG','B_G greedy-hint')]:
    out=gen(kind)
    if out is None: print(f"{label:24s} FAILED"); continue
    secs,t,D=out; bl,cov,_,_=metrics(secs)
    print(f"{label:24s} {D:4} {bl:9} {cov}/7 {t:6.2f}")
