package io.waterleague.physics.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.physics.repository.PhysicsRepository;
import io.waterleague.physics.view.PhysicsView;
import java.time.*;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PhysicsService {
  private final InstallationRepository installations;
  private final PhysicsRepository jobs;
  private final JsonService json;

  public PhysicsService(
      InstallationRepository installations, PhysicsRepository jobs, JsonService json) {
    this.installations = installations;
    this.jobs = jobs;
    this.json = json;
  }

  public PhysicsView latest(UUID id) {
    var installation =
        installations
            .find(id)
            .filter(i -> i.removedAt() == null)
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    var latest = jobs.latest(id).orElse(null);
    var complete = jobs.completed(id).orElse(null);
    var result = complete == null ? null : json.read(complete.result(), PhysicsView.Result.class);
    String status = "WAITING", message = "설치 이후의 관측 구간을 기다리고 있습니다";
    if (latest != null) {
      status =
          switch (latest.state()) {
            case "RUNNING" ->
                latest.leaseUntil() == null || !latest.leaseUntil().isAfter(Instant.now())
                    ? "UNAVAILABLE"
                    : "RUNNING";
            case "FAILED" -> "UNAVAILABLE";
            default ->
                Duration.between(latest.requestedThrough(), Instant.now()).toSeconds() > 300
                    ? "DELAYED"
                    : "READY";
          };
      message =
          switch (status) {
            case "RUNNING" -> "선행 기상과 설치 이후 강우를 이어서 계산하고 있습니다";
            case "UNAVAILABLE" ->
                latest.errorCode() != null && latest.errorCode().startsWith("KMA_")
                    ? "기상청 응답을 기다리고 있습니다. 강우를 0으로 대체하지 않습니다"
                    : latest.errorCode() != null && latest.errorCode().startsWith("AWS_")
                        ? "관측 결측·누적값 검사로 계산이 보류됐습니다"
                        : "물리 계산이 보류됐습니다. 재시도 후 갱신됩니다";
            case "DELAYED" -> "이전 계산 결과입니다. 최신 관측까지 계산이 진행 중입니다";
            default -> "관측 강우를 반영한 시설 내부 계산 결과";
          };
    }
    return new PhysicsView(
        installation.id(),
        status,
        message,
        latest == null ? null : latest.createdAt(),
        complete == null ? null : complete.requestedThrough(),
        result);
  }
}
