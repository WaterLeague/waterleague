"""실제 실행 산출물의 공통 설계 계약·원형·같은 평가 경계 대조."""
import hashlib
import json
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.spatial.play_bundle import open_catalog
from waterleague_sim.engine.flow_connections import validate


def verify(test, directory):
    native = open_catalog()
    folders = [directory] if (directory / 'model.json').is_file() else directory.rglob('model.json')
    count = 0
    for item in folders:
        folder = item if item.is_dir() else item.parent
        model = json.loads((folder / 'model.json').read_bytes())
        result = json.loads((folder / 'result.json').read_bytes())
        cell = model['cells'][0]
        test.assertEqual(cell, native.require(cell['id'], cell['districtId']))
        raw = (folder / 'design-contract.json').read_bytes()
        record = result['designContract']
        test.assertEqual(record, {'sha256': hashlib.sha256(raw).hexdigest(), **json.loads(raw)})
        test.assertEqual(record['spatial']['playCatalogSha256'], native.sha256)
        test.assertEqual(record['spatial']['geometrySha256'], cell['geometrySha256'])
        test.assertEqual(record['evaluation']['start'], result['baseline']['initial']['at'])
        test.assertEqual(record['evaluation']['end'], result['strategy']['final']['at'])
        test.assertEqual(record['units']['coordinate'], 'm')
        test.assertIsNone(record['connection']['drainageNode'])
        test.assertIsNone(record['connection']['externalCatchment'])
        for name, sha in record['inputFiles'].items():
            test.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), sha)
        manifest = json.loads((folder / 'manifest.json').read_bytes())
        comparison = result['runoffComparison']
        assessment = comparison['metricComparison']
        test.assertEqual(len(assessment['metrics']), 9)
        test.assertEqual(assessment['window']['start'], result['baseline']['initial']['at'])
        test.assertEqual(assessment['window']['end'], result['strategy']['final']['at'])
        metrics = {m['id']: m for m in assessment['metrics']}
        primary = metrics['surfaceAccountedVolumeM3']
        test.assertEqual(primary['baseline'], result['baseline']['final']['accountedDischargeM3'])
        test.assertEqual(primary['strategy'], result['strategy']['final']['accountedDischargeM3'])
        test.assertEqual(primary['signedImprovement'], comparison['accountedReductionM3'])
        test.assertEqual(metrics['networkFloodingM3']['reason'], 'NO_CONVEYANCE_NETWORK')
        test.assertIsNone(metrics['networkFloodingM3']['baseline'])
        test.assertEqual(metrics['reusedVolumeM3']['reason'], 'NO_USE_DEMAND')
        test.assertFalse(assessment['relativeUsedForRanking'])
        test.assertEqual(manifest['raw_metrics.py'], hashlib.sha256((ROOT/'simulation/waterleague_sim/evaluation/raw_metrics.py').read_bytes()).hexdigest())
        (ROOT/'tmp/raw-metrics-native-last.json').write_text(json.dumps({
            'evidence': 'ACTUAL_NATIVE_WORKER_RESULT_PROJECTION',
            'sourceResultSha256': hashlib.sha256((folder/'result.json').read_bytes()).hexdigest(),
            'sourceModelSha256': manifest['model.json'], 'sourceManifestSha256': hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),
            'comparison': comparison, 'contract': record}, ensure_ascii=False, indent=2)+'\n')
        test.assertEqual(manifest['design-contract.json'], record['sha256'])
        graph = record['flowGraph']
        graph_raw = (folder / 'flow-graph.json').read_bytes()
        test.assertEqual(graph, {'sha256': hashlib.sha256(graph_raw).hexdigest(), **json.loads(graph_raw)})
        validate(graph)
        test.assertEqual(graph['mode'], 'NATIVE_DIRECT_SURFACE')
        test.assertEqual(manifest['flow-graph.json'], graph['sha256'])
        test.assertEqual(graph['sourceHashes']['siteCatalog'], native.sha256)
        test.assertEqual(graph['sourceHashes']['candidateGeometry'], cell['geometrySha256'])
        test.assertEqual(graph['implementationSha256'], manifest['flow_connections.py'])
        test.assertEqual(graph['evaluationPoints'][0]['start'], record['evaluation']['start'])
        test.assertEqual(graph['evaluationPoints'][0]['end'], record['evaluation']['end'])
        for name, sha in record['inputFiles'].items():
            test.assertEqual(graph['sourceHashes'][name], sha)
        for binding in graph['inputBindings']:
            value = json.loads((folder/binding['source']).read_bytes())
            for part in binding['pointer'].strip('/').split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
        count += 1
    test.assertGreater(count, 0)
