"""공개 연결 계산의 최종 수심·교환 간격 차이·양방향 체적 그림."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--fine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    read = lambda folder, name: json.loads((folder/name).read_bytes())
    model = read(args.reference, 'coupled-input.json')
    a = read(args.reference, 'surface/surface-result.json')
    b = read(args.fine, 'surface/surface-result.json')
    network = read(args.reference, 'network/network-result.json')
    nodes = network['final']['nodes']
    points = np.asarray(model['surface']['verticesM'])/1000
    triangles = np.asarray(model['surface']['triangles'])
    mesh = Triangulation(points[:, 0], points[:, 1], triangles)
    depth = np.asarray(a['final']['depthM'])
    delta = np.abs(depth-np.asarray(b['final']['depthM']))
    fig, axes = plt.subplots(1, 3, figsize=(14, 7), gridspec_kw={'width_ratios':[1, 1, 1.25]})
    for ax, values, title, cmap, unit in zip(axes[:2], (depth, delta*1000),
        ('Final depth · 1 s exchange', 'Final depth difference · 0.5 s vs 1 s'), ('Blues', 'magma'), ('m', 'mm')):
        image = ax.tripcolor(mesh, facecolors=values, cmap=cmap, vmin=0, rasterized=True)
        ax.set_aspect('equal'); ax.set_title(title, fontsize=11)
        ax.set_xlabel('Local easting (km)'); ax.set_ylabel('Local northing (km)')
        fig.colorbar(image, ax=ax, shrink=.7, label=unit)
    ports = model['ports']
    y = np.arange(len(ports))
    outward = [nodes[p['outfall']]['boundaryOutflowM3']/1000 for p in ports]
    inward = [nodes[p['outfall']]['boundaryInflowM3']/1000 for p in ports]
    axes[2].barh(y-.17, outward, height=.34, color='#236ba3', label='Sewer to surface')
    axes[2].barh(y+.17, inward, height=.34, color='#b76724', label='Surface to sewer')
    axes[2].set_yticks(y, [p['id'].removeprefix('PORT_') for p in ports], fontsize=8)
    axes[2].invert_yaxis(); axes[2].set_xlabel('Cumulative volume (1,000 m³)')
    axes[2].set_title('26 assumed exchange openings', fontsize=11, pad=30)
    axes[2].legend(fontsize=8, loc='lower center', bbox_to_anchor=(.5, 1.005), ncol=2, frameon=False)
    axes[2].grid(axis='x', alpha=.15); axes[2].set_axisbelow(True)
    fig.suptitle('Seocho public model + terrain · 86,339 s numerical comparison', fontsize=15, y=.99)
    fig.text(.5, .02, '0.6 m equivalent openings / Cd 0.62 · Unverified common datum · Reflective rectangle boundary\n'
             'Published rain and estimated external inflows · Numerical sensitivity, not observed flood reconstruction',
             ha='center', fontsize=9, color='#444444')
    fig.tight_layout(rect=(0, .08, 1, .96))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
