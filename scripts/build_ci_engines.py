"""전체 수치 회귀 시험에 필요한 고정 EPA 확장 엔진 빌드."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    builders = [
        ('build_live_swmm.py',),
        ('build_network_swmm.py',),
        ('build_network_swmm.py', '--exchange'),
        ('build_network_swmm.py', '--metrics'),
        ('build_surface_infiltration.py',),
        ('build_rainfall_swmm.py',),
        ('build_facility_swmm.py',),
        ('build_facility_metrics_swmm.py',),
        ('build_coupled_facility_swmm.py',),
        ('build_coupled_rainfall_facility_swmm.py',),
        ('build_pump_network_swmm.py',),
        ('build_coupled_pump_swmm.py',),
        ('build_inlet_network_swmm.py',),
    ]
    for name, *arguments in builders:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / name), *arguments],
                       cwd=ROOT, check=True, timeout=300)


if __name__ == '__main__':
    main()
