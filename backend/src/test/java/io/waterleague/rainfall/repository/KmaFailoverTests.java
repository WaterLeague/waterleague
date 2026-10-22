package io.waterleague.rainfall.repository;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.rainfall.exception.RainfallException;
import java.io.IOException;
import java.net.http.*;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.*;
import java.util.*;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class KmaFailoverTests {
  @TempDir Path root;
  private static final String PRIMARY = "PRIMARY_TEST_SECRET", BACKUP = "BACKUP_TEST_SECRET";
  private static final Instant NOW = Instant.parse("2026-10-22T14:59:50Z");
  private final Clock clock = mock(Clock.class);
  private final HttpClient http = mock(HttpClient.class);
  private final List<String> sent = Collections.synchronizedList(new ArrayList<>());
  private ExternalRequestStore store;
  private int primaryStatus = 200, backupStatus = 200;
  private boolean timeout;
  private String body = "observed response";

  @BeforeEach
  @SuppressWarnings("unchecked")
  void setup() throws Exception {
    when(clock.instant()).thenReturn(NOW);
    store = new ExternalRequestStore(root, clock);
    when(http.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenAnswer(
            call -> {
              HttpRequest request = call.getArgument(0);
              boolean primary = request.uri().getQuery().contains("authKey=" + PRIMARY);
              sent.add(primary ? PRIMARY : BACKUP);
              if (primary && timeout) throw new IOException();
              HttpResponse<String> response = mock(HttpResponse.class);
              when(response.statusCode()).thenReturn(primary ? primaryStatus : backupStatus);
              when(response.headers()).thenReturn(HttpHeaders.of(Map.of(), (a, b) -> true));
              when(response.body()).thenReturn(body);
              return response;
            });
  }

  private KmaLiveRepository repository() {
    return new KmaLiveRepository(PRIMARY, BACKUP, store, http);
  }

  private ExternalRequestStore.Policy policy(String key) {
    return ExternalRequestStore.policy("KMA", key, 20000, 5_000_000_000L);
  }

  @Test
  void primarySuccessLeavesBackupUnused() {
    assertThat(repository().fetch(NOW).body()).isEqualTo(body);
    assertThat(sent).containsExactly(PRIMARY);
  }

  @Test
  void failureSwitchesOnceAndConcurrentConsumersShareBodyAndTimestamp() throws Exception {
    primaryStatus = 403;
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<java.util.concurrent.Future<ExternalRequestStore.Response>>();
      for (int i = 0; i < 6; i++) futures.add(pool.submit(() -> repository().fetch(NOW)));
      for (var future : futures)
        assertThat(future.get()).isEqualTo(new ExternalRequestStore.Response(body, NOW));
    }
    assertThat(sent).containsExactly(PRIMARY, BACKUP);
    repository().fetchPresentWeather(NOW);
    assertThat(sent).containsExactly(PRIMARY, BACKUP, BACKUP);
  }

  @Test
  void bothKeysHaveIndependentTwentyThousandLimit() throws Exception {
    for (String key : List.of(PRIMARY, BACKUP)) store.reserve(policy(key), 1);
    try (var db = DriverManager.getConnection("jdbc:sqlite:" + root.resolve("requests.sqlite3"));
        var statement = db.createStatement()) {
      statement.executeUpdate("UPDATE budget SET calls=19999,bytes=0");
    }
    repository().fetch(NOW);
    repository().fetchPresentWeather(NOW);
    assertThatThrownBy(() -> repository().fetch(NOW.minusSeconds(60)))
        .isInstanceOf(RainfallException.class);
    assertThat(sent).containsExactly(PRIMARY, BACKUP);
    try (var db = DriverManager.getConnection("jdbc:sqlite:" + root.resolve("requests.sqlite3"));
        var statement = db.createStatement();
        var rows = statement.executeQuery("SELECT calls FROM budget")) {
      while (rows.next()) assertThat(rows.getInt(1)).isEqualTo(20000);
    }
  }

  @Test
  void bothFailuresPersistAcrossRepositoryInstancesWithoutMoreHttpCalls() {
    primaryStatus = 403;
    backupStatus = 503;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThatThrownBy(() -> repository().fetchPresentWeather(NOW))
        .isInstanceOf(RainfallException.class);
    assertThat(sent).containsExactly(PRIMARY, BACKUP);
  }

  @Test
  void primaryReturnsAfterMidnightWhileOriginalCacheRemainsReusable() {
    store.block(policy(PRIMARY), 403, 60);
    var previous = repository().fetch(NOW);
    when(clock.instant()).thenReturn(NOW.plusSeconds(20));
    assertThat(repository().fetch(NOW)).isEqualTo(previous);
    repository().fetch(NOW.plusSeconds(60));
    assertThat(sent).containsExactly(BACKUP, PRIMARY);
  }

  @Test
  void absentOrDuplicateBackupDoesNotRepeatPrimary() {
    primaryStatus = 403;
    assertThatThrownBy(() -> new KmaLiveRepository(PRIMARY, PRIMARY, store, http).fetch(NOW))
        .isInstanceOf(RainfallException.class);
    assertThatThrownBy(
            () -> new KmaLiveRepository(PRIMARY, "", store, http).fetch(NOW.plusSeconds(60)))
        .isInstanceOf(RainfallException.class);
    assertThat(sent).containsExactly(PRIMARY);
  }

  @Test
  void transportFailureCanUseBackup() {
    timeout = true;
    assertThat(repository().fetch(NOW).body()).isEqualTo(body);
    assertThat(sent).containsExactly(PRIMARY, BACKUP);
  }

  @Test
  void invalidRequestDoesNotConsumeBackup() {
    primaryStatus = 400;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).containsExactly(PRIMARY);
  }

  @Test
  void responseContainingEitherSecretIsRejectedWithoutFallback() {
    body = BACKUP;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).containsExactly(PRIMARY);
  }
}
