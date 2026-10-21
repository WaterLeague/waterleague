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
COPY simulation/pyproject.toml simulation/uv.lock /app/simulation/
COPY simulation/native/lid_snapshot.inc /app/simulation/native/lid_snapshot.inc
COPY scripts/local_config.py /app/scripts/local_config.py
COPY scripts/build_score_policy.py /app/scripts/build_score_policy.py
COPY backend/src/main/java/io/waterleague/evaluation/service/ScorePolicyService.java /app/backend/src/main/java/io/waterleague/evaluation/service/ScorePolicyService.java
COPY backend/src/main/java/io/waterleague/cost/repository/GamePriceCatalog.java /app/backend/src/main/java/io/waterleague/cost/repository/GamePriceCatalog.java
COPY backend/src/main/java/io/waterleague/cost/service/CostService.java /app/backend/src/main/java/io/waterleague/cost/service/CostService.java
COPY backend/src/main/java/io/waterleague/historical/service/HistoricalService.java /app/backend/src/main/java/io/waterleague/historical/service/HistoricalService.java
COPY backend/src/main/java/io/waterleague/historical/service/HistoricalDesignService.java /app/backend/src/main/java/io/waterleague/historical/service/HistoricalDesignService.java
COPY backend/src/main/java/io/waterleague/spatial/repository/NativePlayRepository.java /app/backend/src/main/java/io/waterleague/spatial/repository/NativePlayRepository.java
COPY backend/src/main/java/io/waterleague/installation/repository/CisternGameCatalog.java /app/backend/src/main/java/io/waterleague/installation/repository/CisternGameCatalog.java
COPY backend/src/main/java/io/waterleague/installation/entity/SiteSuitability.java /app/backend/src/main/java/io/waterleague/installation/entity/SiteSuitability.java
COPY backend/src/main/java/io/waterleague/installation/repository/SiteCatalogRepository.java /app/backend/src/main/java/io/waterleague/installation/repository/SiteCatalogRepository.java
COPY backend/src/main/java/io/waterleague/weekly/service/WeeklyService.java /app/backend/src/main/java/io/waterleague/weekly/service/WeeklyService.java
COPY backend/src/main/java/io/waterleague/weekly/repository/WeeklyRepository.java /app/backend/src/main/java/io/waterleague/weekly/repository/WeeklyRepository.java
COPY backend/src/main/java/io/waterleague/historical/service/HistoricalSubmissionService.java /app/backend/src/main/java/io/waterleague/historical/service/HistoricalSubmissionService.java
COPY backend/src/main/java/io/waterleague/historical/repository/HistoricalSubmissionRepository.java /app/backend/src/main/java/io/waterleague/historical/repository/HistoricalSubmissionRepository.java
COPY data/models /app/data/models
COPY backend/src/main/resources/shared-sites /app/backend/src/main/resources/shared-sites
COPY backend/src/main/resources/facilities /app/backend/src/main/resources/facilities
COPY backend/src/main/resources/native-play /app/backend/src/main/resources/native-play
COPY backend/src/main/resources/native-game /app/backend/src/main/resources/native-game
COPY backend/src/main/resources/native-weather /app/backend/src/main/resources/native-weather
COPY backend/src/main/resources/infrastructure/native-v1 /app/backend/src/main/resources/infrastructure/native-v1
COPY backend/src/main/resources/infrastructure/seoul-basin-footprints-*.json /app/backend/src/main/resources/infrastructure/
COPY backend/src/main/resources/districts /app/backend/src/main/resources/districts
COPY backend/src/main/resources/budget /app/backend/src/main/resources/budget
COPY backend/src/main/resources/evaluation /app/backend/src/main/resources/evaluation
COPY deploy/database.py /app/deploy/database.py
COPY deploy/worker-entrypoint.py /app/deploy/worker-entrypoint.py
ENV PYTHONPATH=/app/simulation PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SWMM_LIBRARY=/opt/swmm/bin/libswmm5.so LIVE_SWMM_LIBRARY=/opt/live-swmm/bin/libswmm5.so
USER 10001:10001
CMD ["python", "-m", "waterleague_sim.worker"]
