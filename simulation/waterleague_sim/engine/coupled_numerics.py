"""시설 합성 입력을 보존하는 명시적 수치 설정 파생."""
from pathlib import Path

from ..ingestion import network_variant
from ..ingestion.published_network import digest


def compile(model):
    raw, profile = network_variant.derive_compiled(model['network']['inputText'].encode(), model['networkNumericalProfile'])
    metadata = {'schemaVersion': 1, 'profile': profile,
        'adapterSha256': digest(Path(__file__).read_bytes()),
        'compilerSha256': digest(Path(network_variant.__file__).read_bytes()),
        'scope': 'EXPLICIT_NUMERICAL_VARIANT_SAME_PHYSICAL_INPUTS', 'rankingEligible': False}
    return model | {'network': model['network'] | {'inputText': raw.decode()}}, metadata
