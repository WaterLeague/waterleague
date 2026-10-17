"""EPA 공개 참조 사례 실행·단위·인쇄 결과 대조."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.reference.epa import validate_reference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT/'tmp/epa-reference/applications.zip')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--require-reference-match', action='store_true')
    args = parser.parse_args()
    result = validate_reference(args.source, args.output, download=args.download)
    print(json.dumps({key: result[key] for key in ('executionStatus', 'internationalUnitStatus', 'engineUnitStatus', 'referenceStatus', 'summary')}, ensure_ascii=False))
    if args.require_reference_match and (result['referenceStatus'] != 'WITHIN_PRINT_PRECISION' or result['internationalUnitStatus'] != 'PASS'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
