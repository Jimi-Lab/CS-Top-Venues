#!/usr/bin/env python3
"""Calibrated full-corpus recommendations from Output/候选池.json.

Uses the 120-paper semantic audit to produce title-and-abstract-level reading
recommendations.  It never changes source records or the input candidate pool.
"""
from __future__ import annotations
import json, re
from collections import Counter
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent; OUT=ROOT/'Output'
INPUT=OUT/'候选池.json'
KNOWN_CONFLICT={('DB/ICDE/ICDE-2026.json',172),('Security/NDSS/NDSS-2026.json',257),('Sys/ASPLOS/ASPLOS-2026.json',129)}

AI=["large language model","language model","llm","generative ai","ai agent","llm agent","agentic","autonomous agent","coding agent","machine learning","deep learning","neural network","reinforcement learning"]
SAFETY=["prompt injection","indirect prompt injection","environmental injection","gui injection","adversarial ui","spoofed notification","jailbreak","tool poisoning","tool hijacking","tool calling attack","memory poisoning","context poisoning","retrieval poisoning","rag poisoning","knowledge base poisoning","model backdoor","backdoor attack","model supply chain","agent supply chain","model extraction","model stealing","membership inference","training data extraction","data exfiltration","mcp security","model context protocol","agent security","agent authorization","agent authentication","agent identity","ai red teaming","llm red teaming","agent red teaming","unsafe code generation","insecure code"]
SEC_TASK=["cve","cwe","vulnerability detection","vulnerability discovery","code audit","taint analysis","symbolic execution","fuzzing","fuzzer","program repair","security patch","patch validation","affected version","fixing commit","vulnerability-introducing","backport","supply chain","dependency confusion","malicious package","sbom","malware detection","malware analysis","penetration testing","intrusion detection","incident response","binary analysis","binary lifting","decompilation","firmware","formal verification","model checking","security regression","misconfiguration","web security","api security","cloud security","smart contract"]
SE=["repository-level","software repository","git history","git commit","issue-to-code","report-to-code","commit-to-cve","code review","devsecops","continuous integration","ci/cd","compiler optimization","debug information","code migration","patch propagation"]
FOUND=["static analysis","dynamic analysis","program slicing","call graph","data flow","control flow","reverse engineering","formal verification","symbolic execution","binary analysis","fuzzing","program repair","git history","backport","firmware"]
BOUND=["adversarial attack","adversarial examples","robustness","hallucination","vision-language model","multimodal","world model","coding agent","code generation","privacy"]
EVIDENCE=["cve","zero-day","zero day","confirmed by","responsibly disclosed","real-world","github repositories","benchmark","dataset","open-source"]

def n(x): return ' '+re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',str(x or '').lower()))+' '
def hits(t,ps): return sorted({p for p in ps if f' {n(p).strip()} ' in t})
def classify(row):
 p=row['paper']; title=n(p.get('title')); text=title+n(p.get('abstract')); k=(row['source_file'],row['source_index'])
 if k in KNOWN_CONFLICT: return 'metadata_repair',[],['known_title_abstract_conflict'],None
 if not str(p.get('abstract') or '').strip(): return 'metadata_repair',[],['abstract_missing'],None
 a,s,q,se,f,b,e=map(lambda x:hits(text,x),(AI,SAFETY,SEC_TASK,SE,FOUND,BOUND,EVIDENCE))
 # Direct means a primary security threat/task plus AI/Agent method, or a
 # direct AI-system security threat.  Generic vision/model robustness is not enough.
 if s: label='directly_related'; why=['ai_safety_threat']+s
 elif a and q: label='directly_related'; why=['ai_for_security_intersection']+a+q
 elif a and se and (q or 'security' in text): label='directly_related'; why=['security_oriented_ai_for_se']+a+se
 elif q: label='foundation_related'; why=['security_or_program_analysis_foundation']+q
 elif f and ('security' in text or 'vulnerability' in text or 'malware' in text): label='foundation_related'; why=['contextual_security_foundation']+f
 elif b: label='boundary_related'; why=['adjacent_ai_security_or_se_topic']+b
 else: label='unrelated'; why=['no_primary_taxonomy_signal']
 score=(8 if label=='directly_related' else 4 if label=='foundation_related' else 1 if label=='boundary_related' else 0)+min(3,len(e))+(2 if any(x in title for x in q+s) else 0)
 priority='P0' if label=='directly_related' and score>=10 else ('P1' if label=='directly_related' else ('P2' if label=='foundation_related' else None))
 return label,why,e,priority
def doc(name,rows):
 return {'name':name,'schema_version':'2026-full-recommendations-v1','generated_on':date.today().isoformat(),'scope':'Calibrated title-and-abstract recommendations; PDF reading remains required for final inclusion.','summary':{'papers':len(rows),'labels':dict(Counter(r['full_recommendation']['label'] for r in rows))},'papers':rows}
def main():
 rows=json.loads(INPUT.read_text(encoding='utf8'))['papers']; buckets={x:[] for x in ['directly_related','foundation_related','boundary_related','unrelated','metadata_repair']}
 for r in rows:
  label,why,e,priority=classify(r); x=dict(r); x['full_recommendation']={'label':label,'priority':priority,'reasons':why,'impact_evidence':e,'basis':'calibrated title-and-abstract rule set'}; buckets[label].append(x)
 for rs in buckets.values(): rs.sort(key=lambda r:({'P0':0,'P1':1,'P2':2,None:3}[r['full_recommendation']['priority']],r['paper'].get('venue',''),r['paper'].get('title','').lower()))
 names={'directly_related':'直接相关推荐','foundation_related':'基础相关推荐','boundary_related':'边界相关推荐','unrelated':'暂不相关审计','metadata_repair':'元数据待修复'}
 for k,name in names.items(): (OUT/f'{name}.json').write_text(json.dumps(doc(name,buckets[k]),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:len(v) for k,v in buckets.items()},ensure_ascii=False))
if __name__=='__main__': main()
