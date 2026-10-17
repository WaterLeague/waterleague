FROM amazoncorretto:25.0.4-al2023@sha256:c4348c3d4e9c2219d6e09c2e9e473c9a5bafe0492c4a7038cd60f2f6a473c16b AS build
# Wrapper의 ZIP 해시 검증을 유지하도록 압축 해제 도구 제공.
RUN dnf install -y unzip && dnf clean all
WORKDIR /build
COPY backend/ ./
RUN ./mvnw --batch-mode -DskipTests package
COPY deploy/HttpHealthCheck.java /health/HttpHealthCheck.java
RUN javac -d /health /health/HttpHealthCheck.java

FROM amazoncorretto:25.0.4-al2023@sha256:c4348c3d4e9c2219d6e09c2e9e473c9a5bafe0492c4a7038cd60f2f6a473c16b
WORKDIR /app
COPY --from=build /build/target/waterleague-api-0.0.1-SNAPSHOT.jar /app/api.jar
COPY --from=build /health/HttpHealthCheck.class /app/health/HttpHealthCheck.class
USER 10001:10001
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/api.jar"]
