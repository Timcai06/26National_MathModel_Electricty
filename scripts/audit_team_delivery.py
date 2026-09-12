"""Read-only intake audit. Never cleans or rewrites teammate data."""
import csv, hashlib, json, math
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np
import openpyxl
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/processed/team_delivery'
ANALYSIS=ROOT/'analysis/team_delivery'
SOURCE=ROOT/'CUMCM2026Problems/C题/附件'

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def workbook(n):
    w=openpyxl.load_workbook(SOURCE/f'附件{n}.xlsx',read_only=True,data_only=True)
    values={s.title:list(s.values) for s in w};w.close();return values

def main():
    paths=list(DATA.glob('*.csv'))+list(ANALYSIS.glob('*.csv'))+list(SOURCE.glob('*.xlsx'))
    before={str(p.relative_to(ROOT)):digest(p) for p in paths}
    data={p.stem:read(p) for p in paths if p.suffix=='.csv'}
    report={'files':{},'source_comparisons':{},'derived':{}}
    for name,rows in data.items():
        keys=['slot'] if name=='day_base' else ['date','slot'] if name in ['annual_actual','dynamic_price'] else ['date','issue_time','forecast_horizon'] if name in ['pv_forecast','pv_forecast_error'] else ['date']
        counts=Counter(tuple(r[k] for k in keys) for r in rows)
        numeric=[k for k in rows[0] if k not in ['date','time','time_str','issue_time','target_date','target_time']]
        report['files'][name]={'rows':len(rows),'duplicate_keys':sum(v-1 for v in counts.values()),'blank_cells':sum(v=='' for r in rows for v in r.values()),
          'nonfinite':sum(not math.isfinite(float(r[k])) for r in rows for k in numeric if r[k]!='')}
    annual=data['annual_actual'];dynamic=data['dynamic_price'];base=data['day_base'];forecast=data['pv_forecast']
    expected=[(str(date(2025,1,1)+timedelta(days=i)),j) for i in range(365) for j in range(144)]
    for name in ['annual_actual','dynamic_price']:
        report['files'][name]['exact_date_slot_order']= [(r['date'],int(r['slot'])) for r in data[name]]==expected
    report['files']['day_base']['exact_slots']= [int(r['slot']) for r in base]==list(range(144))
    for name,pairs in [('day_base',[('load_kw','load_kwh'),('pv_forecast_kw','pv_forecast_kwh')]),('annual_actual',[('load_kw','load_kwh'),('pv_actual_kw','pv_actual_kwh')])]:
        report['files'][name]['unit_max_residual']=max(abs(float(r[a])/6-float(r[b])) for r in data[name] for a,b in pairs)
    for name,cols in [('annual_actual',['load_kw','pv_actual_kw']),('dynamic_price',['price']),('day_base',['load_kw','pv_forecast_kw','price']),('pv_forecast',['pv_forecast_kw'])]:
        report['files'][name]['ranges']={c:[min(float(r[c]) for r in data[name]),max(float(r[c]) for r in data[name])] for c in cols}
    wb1=workbook(1)['Sheet1'];wb2=workbook(2);wb3=workbook(3)['Sheet1'];wb4=workbook(4)['Sheet1']
    def compare(name,values):
        errors=[abs(a-b) for a,b in values];report['source_comparisons'][name]={'values_checked':len(errors),'mismatches_above_1e-8':sum(v>1e-8 for v in errors),'max_residual':max(errors)}
    compare('day_base',[(float(r[k]),float(wb1[i+1][col])) for i,r in enumerate(base) for k,col in [('price',1),('load_kw',2),('pv_forecast_kw',3)]])
    compare('annual_actual',[(float(r[k]),float(wb2[sheet][i//144+1][i%144+1])) for i,r in enumerate(annual) for k,sheet in [('load_kw','小区负载'),('pv_actual_kw','光伏发电实际功率')]])
    compare('dynamic_price',[(float(r['price']),float(wb4[i//144+1][i%144+1])) for i,r in enumerate(dynamic)])
    compare('pv_forecast',[(float(r['pv_forecast_kw']),float(wb3[i//24+1][i%24+2])) for i,r in enumerate(forecast)])
    expected_f=[(str(date(2025,1,1)+timedelta(days=i)),f'{h}:00',n) for i in range(365) for h in [0,6,12,18] for n in range(1,25)]
    report['files']['pv_forecast']['exact_issue_horizon_order']=[(r['date'],r['issue_time'],int(r['forecast_horizon'])) for r in forecast]==expected_f
    target_errors=0
    for r in forecast:
        target=datetime.fromisoformat(r['date'])+timedelta(hours=int(r['issue_time'].split(':')[0])+int(r['forecast_horizon']))
        target_errors+=target!=datetime.fromisoformat(r['target_date']+'T'+r['target_time'])
    report['files']['pv_forecast']['target_timestamp_errors']=target_errors
    dates=[str(date(2025,1,1)+timedelta(days=i)) for i in range(365)]
    report['source_comparisons']['source_date_axes_match']=all([r[0].date().isoformat() for r in values[1:]]==dates for values in [*wb2.values(),wb4])
    issues_ok=True
    for i,row in enumerate(wb3[1:]):
        if i%4==0:
            parts=str(row[0]).split('-');source_day=date(*map(int,parts)).isoformat()
        else:
            if row[0] not in [None,'']:issues_ok=False
        issues_ok=issues_ok and source_day==dates[i//4] and row[1]==f'{[0,6,12,18][i%4]}:00'
    report['source_comparisons']['source_issue_axis_match']=issues_ok
    def label(v):return str(v)
    report['source_comparisons']['source_time_labels_match']=all(r['time']==label(wb1[i+1][0]) for i,r in enumerate(base)) and all(r['time_str']==label(wb2['小区负载'][0][i%144+1])==label(wb2['光伏发电实际功率'][0][i%144+1]) for i,r in enumerate(annual)) and all(r['time_str']==label(wb4[0][i%144+1]) for i,r in enumerate(dynamic))
    loads=np.array([float(r['load_kw']) for r in annual]).reshape(365,144)
    pv=np.array([float(r['pv_actual_kw']) for r in annual]).reshape(365,144)
    prices=np.array([float(r['price']) for r in dynamic]).reshape(365,144)
    derived={'load_mean':loads.mean(1),'load_max':loads.max(1),'load_min':loads.min(1),'pv_daily_kwh':pv.sum(1)/6,'pv_max_kw':pv.max(1),'price_mean':prices.mean(1),'price_max':prices.max(1),'price_min':prices.min(1),'price_spread':prices.max(1)-prices.min(1)}
    report['derived']['basic_statistics_max_errors']={k:max(abs(float(r[k])-v[i]) for i,r in enumerate(data['basic_statistics'])) for k,v in derived.items()}
    for lag in [1,7]:
        k=f'load_diff_lag{lag}_mean';rows=data['load_lag_comparison']
        report['derived'][k]={'expected_warmup_blanks':sum(r[k]=='' for r in rows[:lag]),'mae_max_error':max(abs(float(rows[i][k])-np.abs(loads[i]-loads[i-lag]).mean()) for i in range(lag,365))}
    # Exact physical END timestamp join; audits only, does not produce repaired CSV.
    actual_by_end={datetime.fromisoformat(r['date'])+timedelta(minutes=10*(int(r['slot'])+1)):float(r['pv_actual_kw']) for r in annual}
    fkey=lambda r:(r['date'],r['issue_time'],r['forecast_horizon'])
    observed={fkey(r):r for r in data['pv_forecast_error']}
    omitted_in_range=[];out_of_range=0;wrong_actual=0;arithmetic=0
    for r in forecast:
        target=datetime.fromisoformat(r['target_date']+'T'+r['target_time']);key=fkey(r)
        if key not in observed:
            if target in actual_by_end:omitted_in_range.append(r)
            else:out_of_range+=1
        else:
            e=observed[key];truth=actual_by_end.get(target)
            if truth is None or abs(float(e['pv_actual_kw'])-truth)>1e-8:wrong_actual+=1
            err=float(e['pv_forecast_kw'])-float(e['pv_actual_kw'])
            if max(abs(float(e['error'])-err),abs(float(e['abs_error'])-abs(err)),abs(float(e['squared_error'])-err*err))>1e-6:arithmetic+=1
    report['derived']['pv_forecast_error']={'missing_in_range':len(omitted_in_range),'missing_out_of_range':out_of_range,'missing_by_target_time':dict(Counter(r['target_time'] for r in omitted_in_range)),'first_missing':omitted_in_range[:2],'actual_join_mismatches':wrong_actual,'arithmetic_mismatches':arithmetic}
    night=[r for r in annual if float(r['pv_actual_kw'])!=0 and ((int(r['slot'])+1)*10<=300 or (int(r['slot'])+1)*10>=1260)]
    report['derived']['night_zero_claim']={'nonzero_count':len(night),'maximum_kw':max(float(r['pv_actual_kw']) for r in night),'examples':night[:2]}
    report['unchanged']=all(digest(ROOT/p)==h for p,h in before.items());report['input_sha256']=before
    (ANALYSIS/'intake_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
