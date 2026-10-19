"""API·계산이 같은 불변 원형과 설치 조건을 읽는 조회 경계."""
import copy
from contextlib import closing
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from shapely.geometry import box

from ..engine.swmm import SimulationQualityError
from .geometry import cell_geometry
from .playing_profile import FACILITY_ORDER
from . import reference_conditions


class NativeCatalogError(ValueError):
    pass


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path):
    value = path.stat()
    # 읽기만으로 바뀌는 접근 시각은 원본 변경 판정에서 제외한다.
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


class NativePlayCatalog:
    def __init__(self, path, expected_sha256):
        path = Path(path).absolute()
        try:
            before = file_identity(path)
            if (not re.fullmatch('[a-f0-9]{64}', expected_sha256)
                    or path != path.resolve() or not path.is_file()
                    or not 4096 <= before[2] <= 16 * 1024**3
                    or file_hash(path) != expected_sha256 or file_identity(path) != before):
                raise NativeCatalogError('NATIVE_CATALOG_INVALID')
            self.path, self.sha256 = path, expected_sha256
            self._file_identity = before
            with closing(self.connection()) as database:
                if database.execute('PRAGMA user_version').fetchone() != (1,):
                    raise NativeCatalogError('NATIVE_CATALOG_VERSION_INVALID')
                self._metadata = json.loads(database.execute(
                    "SELECT value FROM metadata WHERE key='catalog'").fetchone()[0])
            if (self._metadata['id'] != 'SEOUL_NGII_REFERENCE_PLAY_V1'
                    or self._metadata['coordinateSystem'] != 'EPSG:5186'
                    or self._metadata['referenceScenario'] != reference_conditions.reference()
                    or self._metadata['policy']['externalInflowConnected'] is not False):
                raise NativeCatalogError('NATIVE_CATALOG_CONDITIONS_INVALID')
        except (OSError, KeyError, TypeError, IndexError, sqlite3.DatabaseError, json.JSONDecodeError):
            raise NativeCatalogError('NATIVE_CATALOG_INVALID') from None

    def connection(self):
        if self.path.resolve() != self.path or file_identity(self.path) != self._file_identity:
            raise NativeCatalogError('NATIVE_CATALOG_CHANGED')
        database = sqlite3.connect('file:' + quote(str(self.path)) + '?mode=ro&immutable=1', uri=True)
        database.execute('PRAGMA trusted_schema=OFF')
        database.execute('PRAGMA query_only=ON')
        database.execute('PRAGMA cache_size=-8192')
        return database

    def metadata(self):
        return copy.deepcopy(self._metadata)

    @staticmethod
    def district(value):
        if type(value) is not str or not re.fullmatch('11[0-9]{3}', value):
            raise NativeCatalogError('NATIVE_DISTRICT_INVALID')
        return value

    def require(self, site_id, district=None):
        if type(site_id) is not str or not re.fullmatch('C[a-f0-9]{24}', site_id):
            raise NativeCatalogError('NATIVE_SITE_INVALID')
        with closing(self.connection()) as database:
            row = database.execute('SELECT body,district_id FROM sites WHERE id=?', (site_id,)).fetchone()
        if row is None or (district is not None and row[1] != self.district(district)):
            raise NativeCatalogError('NATIVE_SITE_NOT_FOUND')
        return json.loads(row[0])

    def bounds(self, bounds, *, district=None, kind=None, limit=512, include_unsupported=False):
        if (not isinstance(bounds, (tuple, list)) or len(bounds) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10_000_000 for v in bounds)
                or not 0 < bounds[2] - bounds[0] <= 2000 or not 0 < bounds[3] - bounds[1] <= 2000
                or type(limit) is not int or not 1 <= limit <= 2000 or type(include_unsupported) is not bool):
            raise NativeCatalogError('NATIVE_VIEWPORT_INVALID')
        clauses, values = [], [bounds[0], bounds[2], bounds[1], bounds[3]]
        if district is not None:
            clauses.append('s.district_id=?')
            values.append(self.district(district))
        if kind is not None:
            if kind not in ('ROOF', 'GROUND'):
                raise NativeCatalogError('NATIVE_KIND_INVALID')
            clauses.append('s.kind=?')
            values.append(kind)
        if not include_unsupported:
            clauses.append('s.allowed_mask<>0')
        query = '''SELECT s.body FROM site_bounds b CROSS JOIN sites s ON s.fid=b.fid
            WHERE b.maxx>=? AND b.minx<=? AND b.maxy>=? AND b.miny<=?'''
        if clauses:
            query += ' AND ' + ' AND '.join(clauses)
        query += ' ORDER BY b.fid LIMIT 20001'
        viewport, result = box(*bounds), []
        with closing(self.connection()) as database:
            for scanned, (body,) in enumerate(database.execute(query, values), 1):
                if scanned > 20000:
                    raise NativeCatalogError('NATIVE_VIEWPORT_TOO_DENSE')
                cell = json.loads(body)
                if cell_geometry(cell).intersects(viewport):
                    result.append(cell)
                    if len(result) > limit:
                        raise NativeCatalogError('NATIVE_VIEWPORT_TOO_DENSE')
        return result

    def placement(self, site_id, facility, area_m2, *, district):
        cell = self.require(site_id, district)
        if facility not in FACILITY_ORDER or facility not in cell['allowedTypes']:
            raise NativeCatalogError('NATIVE_FACILITY_UNSUPPORTED')
        try:
            if type(area_m2) not in (int, float, str, Decimal) or len(str(area_m2)) > 64:
                raise ValueError()
            area = Decimal(str(area_m2))
            maximum = cell['maxAreaM2']
            if facility in ('VEGETATIVE_SWALE', 'INFILTRATION_TRENCH'):
                key = 'swaleDesign' if facility == 'VEGETATIVE_SWALE' else 'trenchDesign'
                maximum = cell['physicalInputs'][key]['maxAreaM2']
            if (not area.is_finite() or not 0 < area <= Decimal(str(maximum))
                    or area != area.quantize(Decimal('.01'))):
                raise ValueError()
            cost = area * Decimal(str(self._metadata['unitCosts'][facility]))
        except (ValueError, InvalidOperation):
            raise NativeCatalogError('NATIVE_PLACEMENT_AREA_INVALID') from None
        return {'cellId': site_id, 'facilityType': facility, 'areaM2': float(area),
                'costKrw': str(cost), 'catalogSha256': self.sha256}

    def model(self, site_id, *, district):
        cell = self.require(site_id, district)
        if not cell['allowedTypes']:
            raise NativeCatalogError('NATIVE_FACILITY_UNSUPPORTED')
        try:
            reference_conditions.validate(cell)
        except SimulationQualityError:
            raise NativeCatalogError('NATIVE_CATALOG_CONDITIONS_INVALID') from None
        keys = ('hydrology', 'unitCosts', 'costModel', 'costSourceSha256', 'budget', 'budgetPolicy',
                'facilityDesignSet', 'initializationPolicy')
        model = {key: copy.deepcopy(self._metadata[key]) for key in keys}
        model.update(cells=[cell], mapId='SEOUL_NGII_REFERENCE_PLAY_V1',
            geometrySource={'playCatalogSha256': self.sha256, 'sitesSha256': self._metadata['sourceSitesSha256'],
                'objectsSha256': self._metadata['sourceObjectsSha256'], 'geometrySha256': cell['geometrySha256'],
                'coordinateSystem': 'EPSG:5186', 'sourceObjectId': cell['sourceObjectId']},
            sharedSiteSource={'districtId': district, 'siteCatalogHash': self.sha256,
                'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}, referenceScenario=copy.deepcopy(self._metadata['referenceScenario']),
            assumptions=copy.deepcopy(self._metadata['limitations']))
        return model
