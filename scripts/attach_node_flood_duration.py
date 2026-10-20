"""동결 관망 관측기는 보존하고 별도 월류 시간 관측기를 빌드에 결속."""
import hashlib
from pathlib import Path


def attach(raw, root):
    duration = (root/'simulation/native/node_flood_duration.inc').read_bytes()
    hooks = (
        (b'WL_NETWORK_EXPORT void wl_networkRelease(void)\n{',
         b'WL_NETWORK_EXPORT void wl_networkRelease(void)\n{\n    wl_floodDurationRelease();'),
        (b'    return 0;\n}\n\nstatic int wl_observedStep',
         b'    return wl_floodDurationBegin();\n}\n\nstatic int wl_observedStep'),
        (b'    return 0;\n}\n\nWL_NETWORK_EXPORT int wl_networkAdvance',
         b'    wl_floodDurationObserve(before / 1000.0);\n    return 0;\n}\n\nWL_NETWORK_EXPORT int wl_networkAdvance'),
    )
    for old, new in hooks:
        if raw.count(old) != 1:
            raise ValueError('NODE_FLOOD_DURATION_HOOK_MISMATCH')
        raw = raw.replace(old, new)
    declarations = (b'static void wl_floodDurationRelease(void);\n'
                    b'static int wl_floodDurationBegin(void);\n'
                    b'static void wl_floodDurationObserve(double before);\n')
    return declarations + raw + b'\n' + duration, {
        'nodeFloodDurationVersion': 2,
        'nodeFloodDurationSha256': hashlib.sha256(duration).hexdigest(),
        'nodeFloodDurationBuilderSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
