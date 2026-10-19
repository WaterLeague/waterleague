"""동일 원 관망에 결속한 지표·지하 설계의 추가 행 결합."""
from pathlib import Path

from waterleague_sim.engine.connected_storage import append_section
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.evaluation.values import digest as model_digest
from waterleague_sim.ingestion.published_network import digest, records

METHOD = 'SOURCE_BOUND_BASIN_STORAGE_COMPOSITION_V1'


def compose_storage(original, basin_model, storage_raw, storage_metadata):
    from waterleague_sim.engine.surface_basin import compile_basin

    expected_basin, _ = compile_basin(original)
    require(basin_model == expected_basin, 'COMPOSITION_BASIN_INPUT_MISMATCH')
    original_raw = original['network']['inputText'].encode()
    require(storage_metadata['sourceNetworkSha256'] == digest(original_raw)
            and storage_metadata['derivedNetworkSha256'] == digest(storage_raw)
            and storage_metadata['design'] == original['connectedStorageDesign'],
            'COMPOSITION_STORAGE_INPUT_MISMATCH')
    original_sections = records(original_raw)[1]
    storage_sections = records(storage_raw)[1]
    allowed = {'STORAGE', 'CURVES', 'ORIFICES', 'XSECTIONS'}
    names = {row['nodeId'].upper() for row in storage_metadata['facilities']}
    names |= {row['nodeId'].upper()+'_A' for row in storage_metadata['facilities']}
    names |= {port['linkId'].upper() for row in storage_metadata['facilities'] for port in row['ports'].values()}
    text, basin_sections = records(basin_model['network']['inputText'].encode())
    existing_tokens = {token.upper() for rows in basin_sections.values() for row in rows for token in row['tokens']}
    require(not names.intersection(existing_tokens), 'COMPOSITION_IDENTIFIER_COLLISION')
    additions = {}
    for section in sorted(set(original_sections) | set(storage_sections)):
        before = [row['tokens'] for row in original_sections.get(section, [])]
        after = [row['tokens'] for row in storage_sections.get(section, [])]
        added = [row for row in after if row[0].upper() in names]
        retained = [row for row in after if row[0].upper() not in names]
        require(retained == before and (not added or section in allowed), 'COMPOSITION_SOURCE_MUTATION')
        if added:
            additions[section] = added
    require(set(additions) == allowed, 'COMPOSITION_STORAGE_ROWS_MISSING')
    # 원본에 검증된 추가 행만 합치며 사용자 설계의 원본 해시를 파생 해시로 재작성하지 않는다.
    ending = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    for section, rows in additions.items():
        append_section(lines, section, [' '.join(row) for row in rows], ending)
    raw = ''.join(lines).encode()
    require(len(raw) <= 2_000_000, 'COMPOSITION_INPUT_TOO_LARGE')
    return raw, {'schemaVersion': 1, 'method': METHOD,
        'sourceModelSha256': model_digest(original), 'sourceNetworkSha256': digest(original_raw),
        'basinModelSha256': model_digest(basin_model),
        'basinNetworkSha256': digest(basin_model['network']['inputText'].encode()),
        'storageNetworkSha256': digest(storage_raw), 'composedNetworkSha256': digest(raw),
        'compilerSha256': digest(Path(__file__).read_bytes()),
        'addedRows': additions, 'rainfallOwnershipUnchanged': True,
        'connectionScope': 'SHARED_EXISTING_NETWORK_NODES',
        'rankingEligible': False, 'historicalReconstructionEligible': False}
