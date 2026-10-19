"""과거 재해 전용 FAO-56 일 기준 증발산. 일중 변화 복원에는 사용하지 않는다."""
import hashlib
import math
from datetime import timedelta
from pathlib import Path

from .evaporation import KST, STATION_URL, station, LiveSourceError

METHOD = 'FAO56_DAILY_ASOS_V1'
URL = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php'


def daily(day, latitude, elevation, minimum, maximum, vapor, wind, pressure, height, radiation):
    values = (latitude, elevation, minimum, maximum, vapor, wind, pressure, height, radiation)
    if (not all(math.isfinite(v) for v in values) or not -90 <= minimum <= maximum <= 60
            or not 0 <= vapor <= 15 or not 0 <= wind <= 150 or not 300 <= pressure <= 1100
            or not .1 <= height <= 100 or not 0 <= radiation <= 50 or not -66 < latitude < 66):
        raise LiveSourceError('KMA_DAILY_PET_VALUE_INVALID')
    temperature = (minimum+maximum)/2
    saturation = lambda t: .6108*math.exp(17.27*t/(t+237.3))
    es = (saturation(minimum)+saturation(maximum))/2
    delta = 4098*saturation(temperature)/(temperature+237.3)**2
    gamma = .000665*pressure/10
    u2 = wind*4.87/math.log(67.8*height-5.42)
    j = day.timetuple().tm_yday
    phi = math.radians(latitude)
    declination = .409*math.sin(2*math.pi*j/365-1.39)
    sunset = math.acos(-math.tan(phi)*math.tan(declination))
    ra = 24*60/math.pi*.0820*(1+.033*math.cos(2*math.pi*j/365))*(
        sunset*math.sin(phi)*math.sin(declination)+math.cos(phi)*math.cos(declination)*math.sin(sunset))
    clear = (.75+2e-5*elevation)*ra
    ratio = min(1, max(.3, radiation/clear))
    longwave = 4.903e-9*((minimum+273.16)**4+(maximum+273.16)**4)/2*(.34-.14*math.sqrt(vapor))*(1.35*ratio-.35)
    net = .77*radiation-longwave
    et = (.408*delta*net+gamma*900/(temperature+273)*u2*(es-vapor))/(delta+gamma*(1+.34*u2))
    return {'referenceEtMmDay': max(0, et), 'unclippedEtMmDay': et, 'netRadiationMjM2': net,
            'extraterrestrialMjM2': ra, 'windAtTwoMetersMs': u2, 'soilHeatFluxMjM2': 0}


def observed_daily(start, end, key, fetch):
    day = start.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    if not day <= start < end <= day+timedelta(days=1):
        raise LiveSourceError('KMA_DAILY_PET_RANGE_INVALID')
    sources, stations = [], []
    for at in (day, day+timedelta(hours=23, minutes=59)):
        raw, meta = fetch(STATION_URL, {'inf': 'AWS', 'stn': '108', 'tm': at.strftime('%Y%m%d%H%M'), 'help': '1'}, key)
        stations.append(station(raw));sources.append((raw, meta))
    if stations[0] != stations[1]:
        raise LiveSourceError('KMA_PET_STATION_CHANGED')
    raw, meta = fetch(URL, {'tm1': day.strftime('%Y%m%d'), 'tm2': day.strftime('%Y%m%d'), 'stn': '108', 'help': '1'}, key)
    sources.append((raw, meta))
    text = raw.decode('euc-kr')
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if (not text.startswith('#START7777') or not text.strip().endswith('#7777END')
            or len(rows) != 1 or len(rows[0]) != 56 or rows[0][:2] != [day.strftime('%Y%m%d'), '108']
            or 'SI_DAY' not in text or 'PV_AVG' not in text):
        raise LiveSourceError('KMA_DAILY_PET_FORMAT_INVALID')
    f = rows[0]
    weather = {k: float(f[i]) for k, i in (('minimumC', 13), ('maximumC', 11), ('vaporHpa', 21),
                ('windMs', 2), ('pressureHpa', 25), ('solarMjM2', 35))}
    s = stations[0]
    result = daily(day, s['latitude'], s['elevationM'], weather['minimumC'], weather['maximumC'],
                   weather['vaporHpa']/10, weather['windMs'], weather['pressureHpa'], s['windHeightM'], weather['solarMjM2'])
    return {'method': METHOD, 'ratesMmDay': [result['referenceEtMmDay']]*int((end-start).total_seconds()/60),
            'station': s, 'days': [{'date': day.date().isoformat(), 'weather': weather, **result}],
            'timePolicy': 'ARCHIVED_DAILY_MEAN_HELD_WITHIN_DAY_NOT_LIVE',
            'evidence': 'DERIVED_REFERENCE_GRASS_ET_NOT_SITE_MEASUREMENT',
            'sourceHashes': [m['sha256'] for _, m in sources], 'sourceRequests': [m for _, m in sources],
            'implementationHashes': {'daily_evaporation.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'references': ['https://www.fao.org/4/x0490e/x0490e08.htm', 'https://www.fao.org/4/x0490e/x0490e07.htm'],
            'assumptions': ['서울 108 지점 기상 대표성·시설별 증발 보정 미검증', '일 기준 증발산의 일중 균등 적용; 분별 증발 관측 아님',
                            '일 전체 확정 기상 사용; 실시간 계산에 사용 금지', '일 토양 열플럭스 0·구름비 0.3~1·음수 증발산 0 제한']}, sources
