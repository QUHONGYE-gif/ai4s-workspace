import sys,os,json,time,subprocess,hashlib,shutil,datetime
from pathlib import Path
ROOT=Path('/root/ai4s-trial'); sys.path.insert(0,str(ROOT))
from protein_design_pipeline import read_fasta,filter_a3m,check_a3m,pdb_sequence
R=ROOT/'runs/R004-mmseqs-gpu'; O=R/'audited-b'; O.mkdir(exist_ok=False)
MM=ROOT/'tools/mmseqs-gpu/bin/mmseqs'; DB=R/'db/swissprot_gpu'; ENV={**os.environ,'CUDA_VISIBLE_DEVICES':'0'}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def write(p,x): p.write_text(json.dumps(x,indent=2)+'\n')
def snap(p): return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
M={'status':'running','started_utc':now(),'stages':[],'branches':{},'runner':snap(Path(__file__)),'helper':snap(ROOT/'protein_design_pipeline.py'),'notes':['Initial successful interactive search log overwritten by accidental duplicate attempt; initial result and tmp retained. Audited run uses exclusive logs and new prefixes.','CPU sensitivity 7 versus GPU maximum; no speedup claim.']}
def save(): write(O/'manifest.json',M)
def cmd(n,args):
 args=list(map(str,args)); log=O/(n+'.log'); z={'name':n,'argv':args,'cwd':str(ROOT),'start_utc':now()}; M['stages'].append(z); save(); t=time.monotonic()
 with log.open('x') as f: p=subprocess.run(args,cwd=ROOT,env=ENV,stdout=f,stderr=subprocess.STDOUT)
 z.update(end_utc=now(),wall_seconds=time.monotonic()-t,exit_code=p.returncode,log=snap(log)); save(); print(n,p.returncode,z['wall_seconds'],flush=True)
 if p.returncode: raise RuntimeError(n)
try:
 cmd('environment',['bash','-c','date -Is; hostname; uname -a; ldd --version; nvidia-smi; df -h / /mnt; free -h; lscpu'])
 M['inputs']=[snap(p) for p in [ROOT/'db/uniprot_sprot.fasta.gz',ROOT/'db/uniprot_sprot.fasta',ROOT/'runs/R003b-pipeline/inputs/design.fasta',ROOT/'inputs/positive_control.fasta',MM]]
 M['databases']=[snap(p) for p in sorted((R/'db').glob('swissprot*')) if p.is_file()]
 shutil.copy2(ROOT/'protein_design_pipeline.py',O/'helper_snapshot.py')
 for label,src in [('design',ROOT/'runs/R003b-pipeline/inputs/design.fasta'),('positive',ROOT/'inputs/positive_control.fasta')]:
  b=O/label; b.mkdir(); q=b/'query.fasta'; shutil.copy2(src,q); s=read_fasta(q)[0][1]; qdb=b/'query'; h=b/'hits'; tsv=b/'hits.tsv'; a=b/'alignment'; f=b/'filtered.a3m'
  cmd(label+'-createdb',[MM,'createdb',q,qdb])
  cmd(label+'-search',[MM,'search',qdb,DB,h,b/'tmp','--gpu',1,'-e','0.001','--max-seqs',500,'--threads',10,'-a',1,'--alignment-mode',3,'--min-seq-id','0.3','-c','0.8','--cov-mode',2])
  cmd(label+'-tsv',[MM,'convertalis',qdb,DB,h,tsv,'--format-output','query,target,fident,alnlen,qcov,tcov,evalue,bits'])
  cmd(label+'-msa',[MM,'result2msa',qdb,DB,h,a,'--msa-format-mode',5])
  cmd(label+'-unpack',[MM,'unpackdb',a,b/'a3m','--unpack-name-mode',1,'--unpack-suffix','.a3m'])
  st=filter_a3m(b/'a3m/0.a3m',tsv,f,s,0.3,0.8,0.001); n=check_a3m(f,s); st.update(records=n,query_length=len(s),hits=len(tsv.read_text().splitlines()),used_by_boltz=n>1,filtered_sha256=sha(f),query=s)
  write(b/'msa-summary.json',st); M['branches'][label]=st; save(); write(b/'input.yaml',{'version':1,'sequences':[{'protein':{'id':'A','sequence':s,'msa':str(f) if n>1 else 'empty'}}]})
  cmd(label+'-boltz',[Path('/root/miniconda3/envs/myconda/bin/boltz'),'predict',b/'input.yaml','--out_dir',b/'boltz','--cache',ROOT/'cache/boltz','--model','boltz2','--accelerator','gpu','--devices',1,'--output_format','pdb','--no_kernels','--num_workers',0,'--seed',42,'--recycling_steps',3,'--sampling_steps',200,'--diffusion_samples',1])
  pdbs=list((b/'boltz/boltz_results_input/predictions/input').rglob('*.pdb')); assert len(pdbs)==1; assert pdb_sequence(pdbs[0])==s
  cf=list((b/'boltz/boltz_results_input/predictions/input').rglob('confidence*.json')); assert len(cf)==1
  checks={'prediction_count':1,'sequence_matches_query':True,'length':len(s),'confidence':json.loads(cf[0].read_text())}; write(b/'checks.json',checks); st['checks']=checks; save(); print(label,json.dumps(st),flush=True)
 M.update(status='completed',ended_utc=now())
except BaseException as e:
 M.update(status='failed',ended_utc=now(),error=repr(e)); raise
finally:
 save(); inv=[]
 for p in sorted(R.rglob('*')):
  if p==O/'inventory.json': continue
  if p.is_symlink(): inv.append({'path':str(p.relative_to(R)),'symlink':os.readlink(p)})
  elif p.is_file(): inv.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)})
 write(O/'inventory.json',inv); print('FINAL',M['status'],'files',len(inv),flush=True)
