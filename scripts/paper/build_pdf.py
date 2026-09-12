"""Compile the paper and publish only its PDF.

There is one paper. Earlier versions live in git history, not in parallel
directories, so this script takes no version argument.
"""
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[2]
LATEX = ROOT / 'paper/latex'
PDF = ROOT / 'paper/pdf/C_microgrid.pdf'
BUILD = ROOT / 'tmp/paper_build'
BUILD.mkdir(parents=True, exist_ok=True)

subprocess.run(['/Library/TeX/texbin/latexmk', '-norc', '-xelatex', '-interaction=nonstopmode',
                '-halt-on-error', f'-outdir={BUILD}', 'main.tex'], cwd=LATEX, check=True)
log = (BUILD / 'main.log').read_text()
issues = [line for line in log.splitlines()
          if any(x in line for x in ['Overfull', 'Missing character', 'undefined references', 'undefined citations'])]
if issues:
    raise RuntimeError('Resolve TeX issues before publishing PDF: ' + str(issues))
PDF.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(BUILD / 'main.pdf', PDF)
print(f'PDF published to {PDF.relative_to(ROOT)}')
