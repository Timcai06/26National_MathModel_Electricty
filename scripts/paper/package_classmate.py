"""Package the referenced paper assets and runnable modeling source for review."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'deliverables/review'

README = '''# 微网储能与购电调控：论文及建模源码

## 环境与代表日复现

使用 Python 3.12.13 验证通过，建议使用 Python 3.12，安装项目锁定的依赖版本：

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-excel.txt
python scripts/reproduce_paper_q1.py
```

最后一步直接调用论文使用的约束与求解器，读取随附的标准化附件1数据，
输出购电费用 35126.948589 元、购电量约 59482.699 kWh，并复算物理约束。

## 核心程序与公式

| 程序 | 数学内容 |
| --- | --- |
| src/core/model.py、solver.py | 能量平衡、储电量递推、LP与MILP互斥求解 |
| src/q2/residual_margin.py | 历史净负荷残差、四小时桶分位数安全裕量 |
| src/q2/strict_execution.py | 槽首动作、槽末结算和日终可达性 |
| src/q3/pv.py | 按预报发布时间对齐的光伏插值积分 |
| src/q3/planning.py | 合同增减量费用与余日重规划 |
| src/q3/voi.py | 联合历史残差场景及预期净收益门控 |
| scripts/run_strict_q4.py | 动态电价下的同口径回放 |

附录中的代码通过 lstinputlisting 从这些文件直接读取。
所有电量为kWh，价格为元/kWh；90%为各方向效率，日初日末均为6000kWh。
采用减购退款后加收50%违约费的解释；动态电价假定目标日整条曲线零点可知。

## 年度结果从头复现

在独立解压目录按顺序执行。中间结果写入 analysis/；全年回放和独立校验耗时
显著长于代表日求解。已完成的结果目录会受到脚本保护；重新运行请重新解压。
包内只提供输入数据及接收校验，不预放年度结果，以便从头计算。

```sh
python scripts/run_strict_q2.py
python scripts/verify_strict_q2.py
python scripts/run_q2_margin_oracle.py
python scripts/verify_q2_margin_oracle.py
python scripts/run_strict_q3.py
python scripts/verify_strict_q3.py
python scripts/run_q3_voi.py
python scripts/verify_q3_voi.py
python scripts/run_strict_q4.py
python scripts/verify_strict_q4.py
```

对照论文：第二问B2为15137987.06元；第三问裕量固定为15129676.16元，
收益门控为15122320.83元；第四问对应第二、三问的裕量固定方案分别为
15829022.52元和15822900.47元。评价范围均为二月至十二月334天。

## 核心逻辑回归与论文编译

```sh
python -m unittest discover -s tests
cd paper/latex
latexmk -norc -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

tests/保留储能求解、安全裕量、严格时序、合同调整及门控的核心测试。
论文编译需要含中文字体Fandol的TeX Live。图件均已附入，无需先运行年度回放。
源数据为四份标准化附件CSV，其哈希与接收校验一起提供。
源码中保留其他开发入口以满足模块依赖；复现正文按以上入口运行。
'''


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    pdf = ROOT / 'paper/pdf/C_microgrid.pdf'
    files = {p.relative_to(ROOT).as_posix(): p for p in (ROOT / 'src').rglob('*.py')}
    files.update({p.relative_to(ROOT).as_posix(): p for p in (ROOT / 'scripts').glob('*.py')})
    for p in (ROOT / 'data/processed/team_delivery').glob('*.csv'):
        files[p.relative_to(ROOT).as_posix()] = p
    for name in ('requirements-core.txt', 'requirements-figures.txt', 'requirements-excel.txt',
                 'analysis/team_delivery/intake_audit.json'):
        files[name] = ROOT / name
    for name in ('test_microgrid.py', 'test_strict_execution.py', 'test_strict_q3.py',
                 'test_q3_voi.py', 'test_q2_margin_oracle.py'):
        files['tests/' + name] = ROOT / 'tests' / name
    main_tex = (ROOT / 'paper/latex/main.tex').read_text()
    texts = {'paper/latex/main.tex': main_tex}

    def collect(text):
        for name in re.findall(r'\\input\{([^}]+)\}', text):
            key = 'paper/latex/' + name
            if key not in texts:
                texts[key] = (ROOT / key).read_text()
                collect(texts[key])

    collect(main_tex)
    figures = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', main_tex)
    figures = [f for f in figures if '#' not in f]
    figures += [f + '.pdf' for f in re.findall(r'\\fig\{([^}]+)\}', main_tex)]
    lookup = [ROOT / 'paper/figures'] + [ROOT / 'deliverables/candidate_figures' / v
                                       for v in ('v3_3d', 'v2', 'v1')]
    for name in figures:
        files['paper/figures/' + name] = next(p / name for p in lookup if (p / name).is_file())
    texts['paper/latex/main.tex'] = re.sub(r'\\graphicspath\{[^\n]+',
                                         lambda _: r'\graphicspath{{../figures/}}', main_tex)
    texts['README.md'] = README
    contents = {name: path.read_bytes() for name, path in files.items()}
    contents.update({name: text.encode() for name, text in texts.items()})
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())}
    contents['SHA256.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    archive = ROOT / 'tmp/export/C_microgrid_source_code.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(contents.items()):
            z.writestr(name, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    print(json.dumps({'pdf': str(pdf.relative_to(ROOT)), 'source_code': str(archive.relative_to(ROOT)),
                      'files': len(contents), 'bytes': archive.stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    main()
