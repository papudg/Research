"""RQ4 (Duplicate detection) v2: split numeric variants into SHORT (entity-dominated, gate should help)
vs LONG (multi-entity, gate weak), sweep gate threshold, report FP-rates + paraphrase recall.
Entity rule: lemmatized NOUN/PROPN + numeric tokens (tok.like_num)."""
import re, random, json
import numpy as np, spacy
from generate import load_bank
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from icaa.paths import results_path

nlp=spacy.load('en_core_web_sm'); BANK=load_bank()
def clean(t):
    t=re.sub(r'<[^>]+>',' ',t or ''); t=re.sub(r'\{\{[^}]*\}\}',' ',t)
    t=re.sub(r'\\[a-zA-Z]+',' ',t); t=re.sub(r'[^A-Za-z0-9 .]',' ',t)
    return re.sub(r'\s+',' ',t).lower().strip()
texts={q['id']:clean(q['text']) for q in BANK}; ids=list(texts); corpus=[texts[i] for i in ids]
def entities(t):
    e=set()
    for tok in nlp(t):
        if tok.pos_ in ('NOUN','PROPN'): e.add(tok.lemma_.lower())
        if tok.like_num: e.add(tok.text.lower())
    return e
def jacc(a,b): return len(a&b)/max(1,len(a|b))
sbert=SentenceTransformer('all-MiniLM-L6-v2')
emb=sbert.encode(corpus,normalize_embeddings=True); embmap={ids[k]:emb[k] for k in range(len(ids))}
entmap={i:entities(texts[i]) for i in ids}
print("encoded:",len(ids),"| entity-count dist buckets:",{b:sum(1 for i in ids if b[0]<=len(entmap[i])<b[1]) for b in [(0,3),(3,6),(6,100)]})

SYN=[('find','determine'),('calculate','compute'),('solve','find'),('evaluate','determine'),('number','value'),('sum','total'),('product','multiplication'),('equals','is'),('determine','find')]
def paraphrase(t,rng):
    s=t
    for _ in range(rng.randint(2,4)):
        a,b=rng.choice(SYN); s=re.sub(r'\b'+a+r'\b',b,s,count=1)
    return s
def numvar(t,rng):
    nums=re.findall(r'\d+',t)
    if not nums: return None
    n=rng.choice(nums); new=str(int(n)+rng.choice([1,2,3,5,7,11]))
    return re.sub(r'\b'+n+r'\b',new,t,count=1)

rng=random.Random(123); pairs=[]  # (idA, textB, label, type)
for i in rng.sample(ids,80): pairs.append((i,paraphrase(texts[i],rng),1,'pos'))
short=[i for i in ids if len(entmap[i])<=3 and re.search(r'\d',texts[i])]
longq=[i for i in ids if len(entmap[i])>=6 and re.search(r'\d',texts[i])]
def fill(src, n, tag):
    m=0
    for i in rng.sample(src,len(src)):
        if m>=n: break
        v=numvar(texts[i],rng)
        if v and v!=texts[i]: pairs.append((i,v,0,tag)); m+=1
    return m
ns=fill(short,80,'hard-short'); nl=fill(longq,80,'hard-long')
for _ in range(80):
    a,b=rng.sample(ids,2); pairs.append((a,texts[b],0,'easy'))
print(f"pairs: 80 pos, {ns} hard-short, {nl} hard-long, 80 easy")

bemb=sbert.encode([p[1] for p in pairs],normalize_embeddings=True)
bent=[entities(p[1]) for p in pairs]
def sbert_cos(k,i): return float(np.dot(embmap[i],bemb[k]))
def jac(k,i): return jacc(entmap[i],bent[k])

# score distributions by type
from collections import defaultdict
dist=defaultdict(lambda: {'sb':[],'ja':[]})
for k,(i,bt,lab,typ) in enumerate(pairs):
    dist[typ]['sb'].append(sbert_cos(k,i)); dist[typ]['ja'].append(jac(k,i))
print("\nmedian SBERT-cos / entity-Jaccard by pair type:")
for t in ['pos','hard-short','hard-long','easy']:
    print(f"  {t:11s}: SBERT={np.median(dist[t]['sb']):.2f}  Jaccard={np.median(dist[t]['ja']):.2f}")

def metrics(pred):
    tp=sum(1 for p,(i,bt,lab,typ) in zip(pred,pairs) if p==1 and lab==1)
    fp=sum(1 for p,(i,bt,lab,typ) in zip(pred,pairs) if p==1 and lab==0)
    fn=sum(1 for p,(i,bt,lab,typ) in zip(pred,pairs) if p==0 and lab==1)
    P=tp/(tp+fp) if tp+fp else 0; R=tp/(tp+fn) if tp+fn else 0; F=2*P*R/(P+R) if P+R else 0
    def fpr(tag):
        n=sum(1 for x in pairs if x[3]==tag); fp_=sum(1 for p,(i,bt,lab,typ) in zip(pred,pairs) if p==1 and typ==tag); return fp_/max(1,n)
    return P,R,F,fpr('hard-short'),fpr('hard-long')

print(f"\n{'detector':16s} {'P':>5} {'R':>5} {'F1':>5} {'FP-short':>9} {'FP-long':>8}")
# pure SBERT @0.75
for th in [0.75,0.85,0.9]:
    pred=[1 if sbert_cos(k,i)>=th else 0 for k,(i,bt,lab,typ) in enumerate(pairs)]
    P,R,F,fs,fl=metrics(pred); print(f"{'SBERT@'+str(th):16s} {P:5.2f} {R:5.2f} {F:5.2f} {fs:9.2f} {fl:8.2f}")
# gate: SBERT>=0.75 AND Jaccard>=J, sweep J
for J in [0.5,0.6,0.7,0.8]:
    pred=[1 if (sbert_cos(k,i)>=0.75 and jac(k,i)>=J) else 0 for k,(i,bt,lab,typ) in enumerate(pairs)]
    P,R,F,fs,fl=metrics(pred); print(f"{'gate SB.75^J'+str(J):16s} {P:5.2f} {R:5.2f} {F:5.2f} {fs:9.2f} {fl:8.2f}")
json.dump({t:{'sbert':round(float(np.median(dist[t]['sb'])),2),'jaccard':round(float(np.median(dist[t]['ja'])),2)} for t in dist},
          open(results_path('results_detector.json'), 'w'), indent=1)
