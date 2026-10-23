FROM amazoncorretto:25.0.4-al2023@sha256:c4348c3d4e9c2219d6e09c2e9e473c9a5bafe0492c4a7038cd60f2f6a473c16b AS build
# Wrapper의 ZIP 해시 검증을 유지하도록 압축 해제 도구 제공.
RUN dnf install -y unzip && dnf clean all
WORKDIR /build
COPY backend/ ./
RUN ./mvnw --batch-mode -DskipTests package
RUN mkdir -p /native-library && unzip -p /root/.m2/repository/org/xerial/sqlite-jdbc/3.53.4.0/sqlite-jdbc-3.53.4.0.jar \
    "org/sqlite/native/Linux/$(uname -m)/libsqlitejdbc.so" > /native-library/libsqlitejdbc.so \
    && test -s /native-library/libsqlitejdbc.so
COPY deploy/HttpHealthCheck.java /health/HttpHealthCheck.java
RUN javac -d /health /health/HttpHealthCheck.java

FROM amazoncorretto:25.0.4-al2023@sha256:c4348c3d4e9c2219d6e09c2e9e473c9a5bafe0492c4a7038cd60f2f6a473c16b
LABEL io.waterleague.artifact-storage="gzip-v1"
WORKDIR /app
COPY --from=build /build/target/waterleague-api-0.0.1-SNAPSHOT.jar /app/api.jar
COPY --from=build /health/HttpHealthCheck.class /app/health/HttpHealthCheck.class
COPY --from=build /native-library /app/native-lib
USER 10001:10001
ENTRYPOINT ["java", "--enable-native-access=ALL-UNNAMED", "-Dorg.sqlite.lib.path=/app/native-lib", "-XX:MaxRAMPercentage=65", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/api.jar"]
