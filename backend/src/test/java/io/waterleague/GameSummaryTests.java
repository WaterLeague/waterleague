package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.common.service.JsonService;
import io.waterleague.gameanalysis.service.*;
import io.waterleague.gameanalysis.view.GameAnalysisView;
import io.waterleague.gameanalysis.view.GameAnalysisView.*;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.json.JsonMapper;

class GameSummaryTests {
  @TempDir Path root;
  final JsonService json = new JsonService(JsonMapper.builder().build());
  final String key = "up_TEST_SECRET_LOCAL_ONLY";
  final Instant now = Instant.parse("2026-10-22T08:00:00Z");
  final UpstageClient client = mock(UpstageClient.class);

  ExternalRequestStore store() {
    return new ExternalRequestStore(root, Clock.fixed(now, ZoneOffset.UTC));
  }

  GameSummaryService service() {
    return new GameSummaryService(key, json, store(), client);
  }

  GameAnalysisView snapshot(String hash) {
    return new GameAnalysisView(
        "weekly",
        "2026-10-19",
        now,
        hash,
        true,
        new Facts(
            "WEEKLY",
            "IN_PROGRESS",
            2,
            3,
            2,
            List.of(new Measure("RAIN_GARDEN", "RAIN_GARDEN", 3, BigDecimal.TEN)),
            List.of(),
            List.of(),
            List.of(
                new ScoreGroup(
                    "a".repeat(64),
                    2,
                    BigDecimal.ZERO,
                    BigDecimal.ONE.negate(),
                    BigDecimal.ONE,
                    1,
                    0,
                    1))));
  }

  String valid() {
    return json.write(
        Map.of(
            "model",
            GameSummaryService.MODEL,
            "choices",
            List.of(
                Map.of(
                    "finish_reason",
                    "stop",
                    "message",
                    Map.of(
                        "content",
                        json.write(
                            Map.of(
                                "overview",
                                "참여 기록과 점수 기록을 함께 확인할 수 있습니다.",
                                "findings",
                                List.of(
                                    Map.of("text", "음수와 양수 기록이 함께 있습니다.", "evidence", "scores")),
                                "cautions",
                                List.of("현재 계산 중인 기록을 최종 결과로 해석하지 마세요."))))))));
  }

  @Test
  void concurrentInstancesAndRestartReuseOneValidatedSummary() throws Exception {
    when(client.complete(anyString(), anyString()))
        .thenAnswer(
            call -> {
              Thread.sleep(100);
              return valid();
            });
    var data = snapshot("b".repeat(64));
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var a = pool.submit(() -> service().summarize(data, data.snapshotHash()));
      var b = pool.submit(() -> service().summarize(data, data.snapshotHash()));
      assertThat(a.get()).isEqualTo(b.get());
      assertThat(a.get().generatedAt()).isEqualTo(now);
    }
    assertThat(service().summarize(data, data.snapshotHash()).snapshotHash())
        .isEqualTo(data.snapshotHash());
    var payload = ArgumentCaptor.forClass(String.class);
    verify(client, times(1)).complete(eq(key), payload.capture());
    assertThat(payload.getValue())
        .doesNotContain(key, "nickname", "playerId", "owner_id", "2026-10-19");
    var request = json.tree(payload.getValue());
    assertThat(request.path("model").asString()).isEqualTo(GameSummaryService.MODEL);
    assertThat(request.path("response_format").path("json_schema").path("strict").asBoolean())
        .isTrue();
  }

  @Test
  void staleHashMissingKeyAndEmptyDataNeverCallProvider() {
    var data = snapshot("b".repeat(64));
    assertThatThrownBy(() -> service().summarize(data, "c".repeat(64)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                new GameSummaryService("", json, store(), client)
                    .summarize(data, data.snapshotHash()))
        .isInstanceOf(DomainException.class);
    var empty =
        new GameAnalysisView(
            data.scope(),
            data.scopeId(),
            now,
            data.snapshotHash(),
            true,
            new Facts("WEEKLY", "EMPTY", 0, 0, 0, List.of(), List.of(), List.of(), List.of()));
    assertThatThrownBy(() -> service().summarize(empty, empty.snapshotHash()))
        .isInstanceOf(DomainException.class);
    verifyNoInteractions(client);
  }

  @Test
  void providerFailureBlocksRetryAcrossInstancesWithoutLeakingDetails() {
    when(client.complete(anyString(), anyString())).thenThrow(new UpstageClient.Unavailable(429));
    var data = snapshot("b".repeat(64));
    assertThatThrownBy(() -> service().summarize(data, data.snapshotHash()))
        .isInstanceOf(DomainException.class)
        .hasMessageNotContaining(key);
    assertThatThrownBy(() -> service().summarize(data, data.snapshotHash()))
        .isInstanceOf(DomainException.class);
    verify(client, times(1)).complete(anyString(), anyString());
  }

  @Test
  void invalidOrSecretEchoResponseIsNotCached() {
    when(client.complete(anyString(), anyString()))
        .thenReturn(valid().replace("참여 기록", key).replace(key, "\\" + "u0075" + key.substring(1)));
    var data = snapshot("b".repeat(64));
    assertThatThrownBy(() -> service().summarize(data, data.snapshotHash()))
        .isInstanceOf(DomainException.class);
    when(client.complete(anyString(), anyString())).thenReturn(valid());
    assertThatThrownBy(() -> service().summarize(data, data.snapshotHash()))
        .isInstanceOf(DomainException.class);
    verify(client, times(1)).complete(anyString(), anyString());
  }

  @Test
  void dailyLimitStopsNewRequestsButKeepsStoredSummary() {
    when(client.complete(anyString(), anyString())).thenReturn(valid());
    var data = snapshot("b".repeat(64));
    service().summarize(data, data.snapshotHash());
    var policy = ExternalRequestStore.policy("upstage-game-summary", key, 100, 6_553_600);
    for (int i = 1; i < 100; i++) store().reserve(policy, 1);
    assertThat(service().summarize(data, data.snapshotHash()).overview()).isNotBlank();
    var changed = snapshot("c".repeat(64));
    assertThatThrownBy(() -> service().summarize(changed, changed.snapshotHash()))
        .isInstanceOf(DomainException.class);
    verify(client, times(1)).complete(anyString(), anyString());
  }
}
