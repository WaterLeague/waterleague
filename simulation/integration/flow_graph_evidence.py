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
    assessment = result['metricComparison']
    test.assertEqual(len(assessment['metrics']), 9)
    test.assertIsNone(assessment['compositeScore'])
    test.assertFalse(assessment['relativeUsedForRanking'])
    before, after = result['cases']
    for m in assessment['metrics']:
        if m['status'] == 'COMPARABLE':
            test.assertEqual(m['signedImprovement'], m['baseline']-m['strategy'])
            if m['baseline'] <= 0:
                test.assertIsNone(m['relativeImprovementPercent'])
            else:
                test.assertAlmostEqual(m['relativeImprovementPercent'],m['signedImprovement']/m['baseline']*100)
        elif m['status'] == 'UNAVAILABLE':
            test.assertIsNone(m['baseline']);test.assertIsNone(m['strategy'])
        else:
            test.assertIsNone(result['signedReductionM3']);test.assertIsNone(result['signedPeakReductionM3s'])
    metric = next(m for m in assessment['metrics'] if m['id'] == 'networkFloodingM3')
    test.assertEqual(metric['baseline'], before['totals']['floodingM3'])
    test.assertEqual(metric['strategy'], after['totals']['floodingM3'])
    test.assertEqual(manifest['raw_metrics.py'], hashlib.sha256((folder/'raw_metrics.py').read_bytes()).hexdigest())
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
