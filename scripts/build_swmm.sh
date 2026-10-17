#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
revision=7952ca837988b1c32f791812eccc9fd64547e093
mkdir -p tmp/swmm
curl --fail --location --silent --show-error --max-time 90 "https://api.github.com/repos/USEPA/Stormwater-Management-Model/tarball/$revision" -o tmp/swmm/source.tar.gz
tar -xzf tmp/swmm/source.tar.gz -C tmp/swmm --strip-components=1
options=('-DCMAKE_INSTALL_RPATH=$ORIGIN')
if [[ "$(uname)" == Darwin ]]; then
  omp_root="$(brew --prefix libomp)"
  options=("-DCMAKE_INSTALL_RPATH=@loader_path" "-DOpenMP_C_FLAGS=-Xpreprocessor -fopenmp -I$omp_root/include" "-DOpenMP_C_LIB_NAMES=omp" "-DOpenMP_omp_LIBRARY=$omp_root/lib/libomp.dylib")
fi
cmake -S tmp/swmm -B tmp/swmm-build -DCMAKE_BUILD_TYPE=Release "${options[@]}"
cmake --build tmp/swmm-build -j 4
cmake --install tmp/swmm-build
