"""공개 관망 내부 관로의 저류조 연결 대상과 원 수리 제원 보존."""
import json
import sys
from pathlib import Path
from local_config import ROOT
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.published_network import load_archive, records, digest
from waterleague_sim.ingestion.network_variant import derive


def main():
    raw_catalog = (ROOT/'backend/src/main/resources/watersheds/seocho-published-v1.json').read_bytes()
    catalog = json.loads(raw_catalog)
    _, manifest_hash, entries = load_archive(ROOT, ROOT/'data/manifests/mendeley-seocho-network-v3.json')
    if manifest_hash != catalog['sourceManifestSha256']:
        raise ValueError('공개 관망 원문 불일치')
    original = next(e['raw'] for e in entries if e['member'] == catalog['sourceMember'])
    if digest(original) != catalog['sourceOriginalSha256']:
        raise ValueError('공개 관망 원문 불일치')
    base, _ = derive(original, catalog['numericalProfile'])
    sections = records(original)[1]
    nodes = {r['tokens'][0]: {'id': r['tokens'][0], 'invertM': float(r['tokens'][1]),
        'maxDepthM': float(r['tokens'][2])} for r in sections['JUNCTIONS']}
    connections = []
    for row in sections['CONDUITS']:
        t = row['tokens']
        if t[1] not in nodes or t[2] not in nodes: continue
        a, b = nodes[t[1]], nodes[t[2]]
        if max(a['invertM'], b['invertM']) >= min(a['invertM']+a['maxDepthM'], b['invertM']+b['maxDepthM']): continue
        connections.append({'id': t[0], 'inlet': a, 'receiver': b, 'sourceLine': row['line'], 'lengthM': float(t[3])})
    result = {'schemaVersion': 1, 'id': 'SEOUL_PUBLIC_NETWORK_STORAGE_CONNECTIONS_V1',
        'sourceCatalogSha256': digest(raw_catalog), 'sourceOriginalSha256': digest(original),
        'baseNetworkSha256': digest(base), 'sourceUrl': catalog['sourceUrl'],
        'generatorSha256': digest(Path(__file__).read_bytes()), 'connections': connections,
        'designBasis': 'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
        'facilityType': 'UNDERGROUND_STORAGE', 'completeInstalledCostKrw': None,
        'limitations': ['원 공개 관망의 내부 관로 양끝 절점이며 실제 저류조 부지 후보가 아님',
            '수치 모형 내부 기준고이며 EPSG·수직 기준·현장 관저고의 확인 아님',
            '덮개·차수·직육면체 설계, 무펌프 국부 오리피스 유입·배수·비상배수 사용',
            '공사비·시공 가능성 미확인, 지도 점유·예산 차감·순위 게시 제외']}
    data = (json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    target = ROOT/'backend/src/main/resources/watersheds/seocho-storage-connections-v1.json'
    if target.exists() and target.read_bytes() != data: raise ValueError('기존 연결 목록 변경 금지')
    target.write_bytes(data)
    print(digest(data),len(connections),digest(base))


if __name__ == '__main__': main()
