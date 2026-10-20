"""지도에서 선택한 공개 관망의 위치 가정·원본 결속."""
import json

from .engine.flood_errors import require
from .engine.swmm import ROOT
from .ingestion.published_network import digest

PROFILE = ROOT/'backend/src/main/resources/watersheds/seocho-georeference-v1.json'
HASH = '36a477f877d0d0fc4518f5e7664497e6e36798299745880932d5b43148ac01ab'
FIELDS = ('id', 'method', 'sourceLayoutSha256', 'sourceOriginalSha256', 'evidenceSha256',
          'assumedSourceCrs', 'horizontalCrs', 'sourceCrsVerified')


def verify(design, original_hash):
    if 'locationReference' not in design:
        return None
    raw = PROFILE.read_bytes()
    require(digest(raw) == HASH, 'WATERSHED_LOCATION_PROFILE_CHANGED')
    profile = json.loads(raw)
    expected = {'profileSha256': HASH, **{k: profile[k] for k in FIELDS}}
    require(design['locationReference'] == expected
            and profile['sourceCrsVerified'] is False
            and profile['sourceOriginalSha256'] == original_hash,
            'WATERSHED_LOCATION_REFERENCE_INVALID')
    return raw
