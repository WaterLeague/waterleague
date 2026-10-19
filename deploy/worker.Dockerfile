FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS build
RUN apt-get update && apt-get install --yes --no-install-recommends build-essential cmake curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /source
RUN curl --fail --location --silent --show-error --max-time 90 https://api.github.com/repos/USEPA/Stormwater-Management-Model/tarball/7952ca837988b1c32f791812eccc9fd64547e093 -o source.tar.gz \
    && echo '3f76a199573088ce47ff02491c529afb73d9953ee9d948dfc89dcd4981b4c0c0  source.tar.gz' | sha256sum -c - \
    && tar -xzf source.tar.gz --strip-components=1 \
    && cmake -S . -B /build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/swmm '-DCMAKE_INSTALL_RPATH=$ORIGIN' \
    && cmake --build /build -j 2 && cmake --install /build \
    && cp -L "$(gcc -print-file-name=libgomp.so.1)" /opt/swmm/bin/libgomp.so.1
COPY deploy/requirements.lock /source/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes --prefix=/dependencies -r /source/requirements.lock
COPY scripts/build_live_swmm.py /live/scripts/build_live_swmm.py
COPY simulation/native/lid_snapshot.inc /live/simulation/native/lid_snapshot.inc
RUN mkdir -p /live/tmp/swmm && cp /source/source.tar.gz /live/tmp/swmm/source.tar.gz \
    && python /live/scripts/build_live_swmm.py \
    && cp -a /live/tmp/live-swmm-build/install /opt/live-swmm \
    && cp -L "$(gcc -print-file-name=libgomp.so.1)" /opt/live-swmm/bin/libgomp.so.1

FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
COPY --from=build /dependencies /usr/local
COPY --from=build /opt/swmm /opt/swmm
COPY --from=build /opt/live-swmm /opt/live-swmm
WORKDIR /app
COPY simulation/waterleague_sim /app/simulation/waterleague_sim
COPY simulation/native/lid_snapshot.inc /app/simulation/native/lid_snapshot.inc
COPY scripts/local_config.py /app/scripts/local_config.py
COPY data/models /app/data/models
COPY backend/src/main/resources/shared-sites /app/backend/src/main/resources/shared-sites
COPY backend/src/main/resources/facilities /app/backend/src/main/resources/facilities
COPY backend/src/main/resources/infrastructure/seoul-basin-footprints-*.json /app/backend/src/main/resources/infrastructure/
COPY backend/src/main/resources/districts /app/backend/src/main/resources/districts
COPY deploy/database.py /app/deploy/database.py
ENV PYTHONPATH=/app/simulation PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SWMM_LIBRARY=/opt/swmm/bin/libswmm5.so LIVE_SWMM_LIBRARY=/opt/live-swmm/bin/libswmm5.so
USER 10001:10001
CMD ["python", "-m", "waterleague_sim.worker"]
