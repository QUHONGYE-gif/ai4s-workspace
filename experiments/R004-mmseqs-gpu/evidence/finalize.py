from pathlib import Path
import json,hashlib,os,subprocess,math,zipfile,tarfile,shutil,datetime
R=Path('/root/ai4s-trial/runs/R004-mmseqs-gpu'); O=R/'audited-b'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def write(p,v): p.write_text(json.dumps(v,indent=2)+'\n')
M=json.loads((O/'manifest.json').read_text()); assert M['status']=='completed'
validation={}
for label in ['design','positive']:
 b=O/label; summary=json.loads((b/'msa-summary.json').read_text()); checks=json.loads((b/'checks.json').read_text())
 for key in ['confidence_score','ptm','complex_plddt']: assert math.isfinite(checks['confidence'][key])
 npzs=list((b/'boltz').rglob('*.npz'))
 for p in npzs:
  with zipfile.ZipFile(p) as z: assert z.namelist() and z.testzip() is None,str(p)
 validation[label]={'npz_files_integrity_passed':len(npzs),'prediction_checks':checks,'msa_summary':summary}
cpu=Path('/root/ai4s-trial/runs/R003-positive-msa-b')
def targets(p): return set(x.split('	')[1] for x in p.read_text().splitlines() if x.strip())
g=targets(O/'positive/hits.tsv'); c=targets(cpu/'hits.tsv')
comparison={'cpu_positive_hits':len(c),'gpu_positive_hits':len(g),'shared_target_ids':len(c&g),'only_cpu':sorted(c-g),'only_gpu':sorted(g-c),'same_target_set':g==c,'cpu_filtered_sha256':sha(cpu/'filtered.a3m'),'gpu_filtered_sha256':sha(O/'positive/filtered.a3m'),'note':'CPU -s 7 and GPU maximum sensitivity; one query each, not a speed benchmark.'}
write(R/'validation.json',validation); write(R/'cpu-gpu-comparison.json',comparison)
proc=subprocess.run(['/root/miniconda3/envs/myconda/bin/python','-c','import sys,torch,importlib.metadata as m; print(sys.version); print("torch",torch.__version__,"CUDA",torch.version.cuda); print({x:m.version(x) for x in ["boltz","numpy","pytorch-lightning"]})'],capture_output=True,text=True)
(R/'runtime-versions.txt').write_text(proc.stdout+proc.stderr)
shutil.copy2(Path('/root/ai4s-trial/protein_design.matpool.json'),R/'cpu-source-config.json')
inv=[]
for p in sorted(R.rglob('*')):
 if p==R/'inventory-final.json': continue
 if p.is_symlink(): inv.append({'path':str(p.relative_to(R)),'symlink':os.readlink(p)})
 elif p.is_file(): inv.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)})
write(R/'inventory-final.json',inv)
full=Path('/root/ai4s-R004-gpu-full-20261021.tar.gz'); evidence=Path('/root/ai4s-R004-gpu-evidence-20261021.tar.gz')
with tarfile.open(full,'x:gz') as z: z.add(R,arcname='R004-mmseqs-gpu')
with tarfile.open(evidence,'x:gz') as z:
 for p in sorted(R.rglob('*')):
  if not p.is_file() or p.is_symlink(): continue
  rel=p.relative_to(R)
  if rel.parts[0] in ('db','tmp') or 'tmp' in rel.parts or '__pycache__' in rel.parts: continue
  z.add(p,arcname='R004-mmseqs-gpu/'+str(rel),recursive=False)
backup=Path('/mnt/ai4s-trial-20261021'); backup.mkdir(exist_ok=True)
info={}
for p in [full,evidence]:
 shutil.copy2(p,backup/p.name); assert sha(p)==sha(backup/p.name)
 info[p.name]={'bytes':p.stat().st_size,'sha256':sha(p),'persistent_backup':str(backup/p.name)}
write(Path('/root/ai4s-R004-archives.json'),info); shutil.copy2('/root/ai4s-R004-archives.json',backup/'R004-archives.json')
print('VALIDATION',json.dumps(validation)); print('COMPARISON',json.dumps(comparison)); print('ARCHIVES',json.dumps(info)); print('INVENTORY',len(inv),'entries'); print('DONE',datetime.datetime.now(datetime.timezone.utc).isoformat())
