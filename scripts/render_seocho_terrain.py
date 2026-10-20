"""보관된 서초 지형·두 해상도의 계산 결과 그림 생성."""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LogNorm
import numpy as np

from prepare_seocho_terrain import GEOREFERENCE, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.run/'manifest.json').read_bytes())
    if args.font:
        from matplotlib import font_manager
        font_manager.fontManager.addfont(str(args.font))
        plt.rcParams['font.family'] = FontProperties(fname=args.font).get_name()
    plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 10})
    location = json.loads(GEOREFERENCE.read_bytes())
    assert sha(GEOREFERENCE) == manifest['terrain']['georeferenceSha256']
    origin = manifest['terrain']['domainBounds'][:2]
    fig, axes = plt.subplots(1, 3, figsize=(15, 8))
    for i, key in enumerate(('20m-1s', '20m-1s', '10m-1s')):
        raw = (args.run/key/'observed-surface-input.json').read_bytes()
        import hashlib
        assert hashlib.sha256(raw).hexdigest() == manifest['files'][f'{key}/observed-surface-input.json']
        model = json.loads(raw)['surface']
        vertices = np.asarray(model['verticesM'])
        triangles = np.asarray(model['triangles'])
        vertices[:, 1] += manifest['terrain']['domainBounds'][3]-origin[1]
        ax = axes[i]
        if i == 0:
            plot = ax.tripcolor(vertices[:, 0], vertices[:, 1], triangles,
                               np.asarray(model['elevationM']), shading='gouraud', cmap='terrain')
            label = '보간 표고 (m · 절대 기준 미확인)'
            title = '공개 등고선·표고점의 계산 지형'
        else:
            result_path = args.run/key/'observed-surface-result.json'
            assert sha(result_path) == manifest['files'][f'{key}/observed-surface-result.json']
            result = json.loads(result_path.read_bytes())
            depths = np.asarray(result['final']['depthM'])
            shown = np.ma.masked_less(depths, .001)
            plot = ax.tripcolor(vertices[:, 0], vertices[:, 1], triangles, facecolors=shown,
                               norm=LogNorm(.001, 2.), cmap='Blues')
            label = '종료 수심 (m · 1mm 미만 미표시)'
            title = f"{20 if i == 1 else 10}m 격자 · 종료 최대 {max(depths):.3f}m"
            ax.set_facecolor('#f2f3f3')
        for link in location['links']:
            xy = np.asarray(link['points'])-origin
            ax.plot(xy[:, 0], xy[:, 1], color='#414148', lw=.6, alpha=.7)
        ax.set_title(title, fontsize=12, pad=12)
        ax.set_aspect('equal')
        ax.set_xlabel('기준점에서 동쪽 거리 (m)')
        if i == 0:
            ax.set_ylabel('기준점에서 북쪽 거리 (m)')
        ax.tick_params(labelsize=8)
        bar = fig.colorbar(plot, ax=ax, fraction=.04, pad=.035)
        if i:
            bar.set_ticks([.001, .01, .1, 1., 2.], labels=['0.001', '0.01', '0.1', '1', '2'])
        bar.set_label(label, fontsize=9)
    request = json.loads((args.run/'20m-1s/observed-surface-input.json').read_bytes())['observedRainfall']
    start = datetime.fromisoformat(request['startUtc'])+timedelta(hours=9)
    end = datetime.fromisoformat(request['endUtc'])+timedelta(hours=9)
    cases = {c['name']: c for c in manifest['cases']}
    fig.suptitle('서초 공개 지형의 강우 계산 검증', fontsize=19, y=.975)
    fig.text(.5, .905, f'서초 AWS 401 · {start:%Y-%m-%d %H:%M}–{end:%H:%M} KST · 관망 미결합 · 현장 침수 예측 아님',
             ha='center', fontsize=11)
    fig.text(.04, .11,
        '실선은 위치 가정이 적용된 연구 관망입니다. 계산은 건조 시작·균일 조도·침투/증발/건물 차폐 없이 수행했습니다.\n'
        f"같은 관측 강우 {cases['20m-1s']['observedRainfall']['expectedSurfaceRainfallM3']:,.0f}m³ 외에 전달 경계에서 "
        f"20m 격자 {cases['20m-1s']['final']['boundaryNetInflowM3']:.3f}m³, "
        f"10m 격자 {cases['10m-1s']['final']['boundaryNetInflowM3']:.3f}m³가 순유입됐습니다.\n"
        '격자 간격은 계산 해상도이며 관측 정확도가 아닙니다. 서초 지형과 원 관망 높이의 자동 보정은 적용하지 않았습니다.',
        fontsize=10, linespacing=1.7)
    fig.text(.04, .035, f'좌표 기준점: EPSG:5186 ({origin[0]:.0f}, {origin[1]:.0f}) · '
             '수치지형도 배포일 2026-03-07 · 물수지 검사 통과, 현장 정확도 미검증', fontsize=9, color='#555')
    fig.subplots_adjust(left=.05, right=.97, top=.85, bottom=.30, wspace=.42)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160, facecolor='white', bbox_inches='tight', pad_inches=.15)
    plt.close(fig)


if __name__ == '__main__':
    main()
