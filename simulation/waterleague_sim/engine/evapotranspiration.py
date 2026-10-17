"""FAO-56 식 28·31·39·45·46·47·53의 시간별 기준 증발산."""
import math
from datetime import timedelta

REFERENCE = 'https://www.fao.org/4/x0490e/x0490e08.htm'
METEOROLOGY_REFERENCE = 'https://www.fao.org/4/x0490e/x0490e07.htm'


def solar_hour(end, latitude, longitude, elevation):
    midpoint = end-timedelta(minutes=30)
    day = midpoint.timetuple().tm_yday
    phi = math.radians(latitude)
    declination = .409*math.sin(2*math.pi*day/365-1.39)
    distance = 1+.033*math.cos(2*math.pi*day/365)
    b = 2*math.pi*(day-81)/364
    correction = .1645*math.sin(2*b)-.1255*math.cos(b)-.025*math.sin(b)
    meridian = midpoint.utcoffset().total_seconds()/3600*15
    angle = math.pi/12*(midpoint.hour+midpoint.minute/60+.06667*(longitude-meridian)+correction-12)
    sunset = math.acos(max(-1, min(1, -math.tan(phi)*math.tan(declination))))
    first, last = max(-sunset, min(sunset, angle-math.pi/24)), max(-sunset, min(sunset, angle+math.pi/24))
    ra = max(0, 12*60/math.pi*.0820*distance*((last-first)*math.sin(phi)*math.sin(declination)
                                            +math.cos(phi)*math.cos(declination)*(math.sin(last)-math.sin(first))))
    return {'extraterrestrialMjM2': ra, 'clearSkyMjM2': (.75+2e-5*elevation)*ra,
            'beforeSunsetReference': sunset-.79 <= angle <= sunset-.52}


def hourly(temperature, humidity, wind, pressure, wind_height, radiation, clear_sky, cloud_ratio):
    values = (temperature, humidity, wind, pressure, wind_height, radiation, clear_sky, cloud_ratio)
    if (not all(math.isfinite(v) for v in values) or not -90 <= temperature <= 60
            or not 0 <= humidity <= 100 or not 0 <= wind <= 150 or not 300 <= pressure <= 1100
            or not .1 <= wind_height <= 100 or radiation < 0 or clear_sky < 0 or not .3 <= cloud_ratio <= 1):
        raise ValueError('LIVE_PET_INPUT_INVALID')
    u2 = wind*4.87/math.log(67.8*wind_height-5.42)
    es = .6108*math.exp(17.27*temperature/(temperature+237.3))
    ea = es*humidity/100
    delta = 4098*es/(temperature+237.3)**2
    gamma = .000665*(pressure/10)
    longwave = 4.903e-9/24*(temperature+273.16)**4*(.34-.14*math.sqrt(ea))*(1.35*cloud_ratio-.35)
    net = .77*radiation-longwave
    heat = (.1 if clear_sky > 0 else .5)*net
    raw = (.408*delta*(net-heat)+gamma*37/(temperature+273)*u2*(es-ea))/(delta+gamma*(1+.34*u2))
    # 응결을 음수 증발 입력으로 보내지 않는다. 원 계산값은 재현 결과에 보존한다.
    return {'referenceEtMmHour': max(0, raw), 'unclippedEtMmHour': raw, 'windAtTwoMetersMs': u2,
            'netRadiationMjM2': net, 'soilHeatFluxMjM2': heat, 'cloudRatio': cloud_ratio}
