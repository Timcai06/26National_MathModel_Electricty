"""Compile the portable LaTeX draft and copy only its PDF into the handoff."""
from pathlib import Path
import subprocess,shutil,argparse
parser=argparse.ArgumentParser();parser.add_argument("--version",choices=["v1","v2","v3","v4","v5"],default="v1");version=parser.parse_args().version
R=Path(__file__).resolve().parents[2]
build=R/f'tmp/paper_{version}_build'; build.mkdir(parents=True,exist_ok=True)
cmd=['rtk','proxy','/Library/TeX/texbin/latexmk','-norc','-xelatex','-interaction=nonstopmode','-halt-on-error',f'-outdir={build}','main.tex']
subprocess.run(cmd,cwd=R/f'deliverables/draft_{version}/latex',check=True)
log=(build/'main.log').read_text()
issues=[line for line in log.splitlines() if any(x in line for x in ['Overfull','Missing character','undefined references','undefined citations'])]
if issues: raise RuntimeError('Resolve TeX issues before publishing PDF: '+str(issues))
shutil.copy2(build/'main.pdf',R/f'deliverables/draft_{version}/pdf/C_microgrid_draft_{version}.pdf')
print(f'PDF published to deliverables/draft_{version}/pdf/C_microgrid_draft_{version}.pdf')
