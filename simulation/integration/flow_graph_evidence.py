"""실제 공개 관망 산출물의 연결 원문·출처·면적·평가 경계 대조."""
import hashlib
import json

from waterleague_sim.engine.flow_connections import validate


def verify(test, folder, result):
    value = result['flowGraph']
    raw = (folder/'flow-graph.json').read_bytes()
    test.assertEqual(value, {'sha256': hashlib.sha256(raw).hexdigest(), **json.loads(raw)})
    validate(value)
    manifest = json.loads((folder/'manifest.json').read_bytes())
    test.assertEqual(manifest['flow-graph.json'], value['sha256'])
    test.assertEqual(value['implementationSha256'], manifest['flow_connections.py'])
    for name, sha in value['sourceHashes'].items():
        test.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(), sha)
        test.assertEqual(manifest[name], sha)
    for record in value['nodes'] + value['edges']:
        if 'rowSha256' in record:
            line = (folder/record['source']).read_bytes().decode('utf-8-sig').splitlines()[record['line']-1]
            test.assertEqual(hashlib.sha256(line.encode()).hexdigest(), record['rowSha256'])
    for case in result['cases']:
        metrics = case.get('evaluationMetrics')
        if metrics:
            points = [p for p in value['evaluationPoints'] if p['case'] == case['id']]
            test.assertEqual({p['nodeId'] for p in points},
                             {'node:' + k.upper() for k in metrics['specification']['networkOutfalls']})
            test.assertEqual({p['specificationSha256'] for p in points}, {metrics['specificationSha256']})
    test.assertEqual(value['spatialStatus']['nativeMapLink'], 'UNCONNECTED')
