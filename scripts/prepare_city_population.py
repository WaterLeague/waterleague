"""공개 자치구 시간대 생활인구의 사건·참고 프로필 추출."""
import csv
import io
import json
import math
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from fetch_seoul_observations import SOURCES, fetch
from prepare_seoul_city import ROOT, digest, write


def main():
    SOURCES.update({
        'people2022':('OA-15439','6','3','seoul-people-2022.zip',45_000_000),
        'people2025':('OA-15439','9','3','seoul-people-2025.zip',45_000_000),
    })
    city=json.loads((ROOT/'frontend/public/data/seoul-v1/city.json').read_text())
    codes={'종로구':'11110','중구':'11140','용산구':'11170','성동구':'11200','광진구':'11215','동대문구':'11230','중랑구':'11260','성북구':'11290','강북구':'11305','도봉구':'11320','노원구':'11350','은평구':'11380','서대문구':'11410','마포구':'11440','양천구':'11470','강서구':'11500','구로구':'11530','금천구':'11545','영등포구':'11560','동작구':'11590','관악구':'11620','서초구':'11650','강남구':'11680','송파구':'11710','강동구':'11740'}
    ids={codes[d['name']]:d['id'] for d in city['districts']}
    sources=[]; event={}; profile={}
    for year in (2022,2025):
        fetch(f'people{year}')
        path=ROOT/f'data/raw/seoul-people-{year}.zip'
        sources.append({'year':year,'sourcePage':'https://data.seoul.go.kr/dataList/OA-15439/A/1/datasetView.do','sha256':digest(path)})
        seen = set()
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.filename.lower().endswith('.csv'):
                    continue
                with archive.open(info) as raw:
                    rows=csv.reader(io.TextIOWrapper(raw,encoding='cp949'))
                    header=next(rows)
                    expected = ['기준일ID','시간대구분','자치구코드','총생활인구수'] if year == 2022 else ['stdr_de_id','tmzon_pd_se','adstrd_code_se','tot_lvpop_co']
                    if header[:4] != expected: raise ValueError('생활인구 열 정의 불일치')
                    print(year,info.filename,header[:5],flush=True)
                    for row in rows:
                        if not row: continue
                        if len(row)<4: raise ValueError('생활인구 행 누락')
                        day,hour,code,total=row[:4]
                        if code not in ids: continue
                        value=float(total)
                        if not math.isfinite(value) or value<0: raise ValueError('인구 범위 오류')
                        district=ids[code]; h=int(hour)
                        date = datetime.strptime(day,'%Y%m%d')
                        if date.year != year or not 0 <= h < 24: raise ValueError('생활인구 시각 오류')
                        record = (day,h,code)
                        if record in seen: raise ValueError('중복 인구 행')
                        seen.add(record)
                        if year==2022 and day in ('20220808','20220809'):
                            key=f'{day}:{district}'
                            values=event.setdefault(key,[None]*24)
                            if values[h] is not None: raise ValueError('중복 시간')
                            values[h]=value
                        if year==2025:
                            weekday=date.weekday()
                            key=f'{weekday}:{district}'
                            values=profile.setdefault(key,[[0,0] for _ in range(24)])
                            values[h][0]+=value;values[h][1]+=1
        dates = {day for day,_,_ in seen}
        if len(seen) != len(dates) * 24 * 25: raise ValueError('자치구 시간대 부분 누락')
        start = datetime(year,1,1)
        missing = [(start+timedelta(days=i)).strftime('%Y%m%d') for i in range(365)
                   if (start+timedelta(days=i)).strftime('%Y%m%d') not in dates]
        sources[-1]['coverage'] = {'days':len(dates),'rows':len(seen),'missingDates':missing,'missingPolicy':'EXCLUDE_FROM_REFERENCE_MEAN_NO_IMPUTATION'}
    if len(event)!=50 or any(None in v for v in event.values()):raise ValueError('사건 시간 누락')
    if len(profile)!=175 or any(not x[1] for v in profile.values() for x in v):raise ValueError('프로필 시간 누락')
    data={'schemaVersion':1,'sources':sources,'event2022':event,
          'reference2025':{k:[round(s/n,5) for s,n in v] for k,v in profile.items()},
          'classification':'DOMESTIC_LIVING_POPULATION_ESTIMATE','referencePolicy':'2025_WEEKDAY_HOUR_PROFILE_NOT_REALTIME',
          'unavailableHistoricalYears':[2010,2011]}
    ref=write(ROOT/'frontend/public/data/city-population-v1.json',data)
    write(ROOT/'data/manifests/city-population-v1.json',{'sources':sources,'output':ref,'generatorSha256':digest(Path(__file__))})
    print(ref)


if __name__=='__main__': main()
