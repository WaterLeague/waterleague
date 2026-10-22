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

class KmaSingleKeyTests {
  @TempDir Path root;
  private static final String KEY = "PRIMARY_TEST_SECRET";
  private static final Instant NOW = Instant.parse("2026-10-22T14:59:50Z");
  private final Clock clock = mock(Clock.class);
  private final HttpClient http = mock(HttpClient.class);
  private final List<String> sent = Collections.synchronizedList(new ArrayList<>());
  private ExternalRequestStore store;
  private int status = 200;
  private boolean timeout;
  private String body = "observed response";

  @BeforeEach
  @SuppressWarnings("unchecked")
  void setup() throws Exception {
    when(clock.instant()).thenReturn(NOW);
    store = new ExternalRequestStore(root, clock);
    when(http.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenAnswer(call -> {
          HttpRequest request = call.getArgument(0);
          sent.add(request.uri().getQuery());
          if (timeout) throw new IOException();
          HttpResponse<String> response = mock(HttpResponse.class);
          when(response.statusCode()).thenReturn(status);
          when(response.headers()).thenReturn(HttpHeaders.of(Map.of(), (a, b) -> true));
          when(response.body()).thenReturn(body);
          return response;
        });
  }

  private KmaLiveRepository repository() {
    return new KmaLiveRepository(KEY, store, http);
  }

  private ExternalRequestStore.Policy policy() {
    return ExternalRequestStore.policy("KMA", KEY, 18000, 4_500_000_000L);
  }

  @Test
  void concurrentConsumersShareBodyAndTimestamp() throws Exception {
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<java.util.concurrent.Future<ExternalRequestStore.Response>>();
      for (int i = 0; i < 6; i++) futures.add(pool.submit(() -> repository().fetch(NOW)));
      for (var future : futures)
        assertThat(future.get()).isEqualTo(new ExternalRequestStore.Response(body, NOW));
    }
    assertThat(sent).hasSize(1).allMatch(query -> query.contains("authKey=" + KEY));
  }

  @Test
  void stopsAtEighteenThousandAndRetainsCachedResponse() throws Exception {
    store.reserve(policy(), 1);
    try (var db = DriverManager.getConnection("jdbc:sqlite:" + root.resolve("requests.sqlite3"));
        var statement = db.createStatement()) {
      statement.executeUpdate("UPDATE budget SET calls=17999,bytes=0");
    }
    var cached = repository().fetch(NOW);
    assertThat(repository().fetch(NOW)).isEqualTo(cached);
    assertThatThrownBy(() -> repository().fetchPresentWeather(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).hasSize(1);
    try (var db = DriverManager.getConnection("jdbc:sqlite:" + root.resolve("requests.sqlite3"));
        var statement = db.createStatement();
        var rows = statement.executeQuery("SELECT calls FROM budget")) {
      assertThat(rows.next()).isTrue();
      assertThat(rows.getInt(1)).isEqualTo(18000);
    }
  }

  @Test
  void byteLimitStopsBeforeNetwork() throws Exception {
    store.reserve(policy(), 1);
    try (var db = DriverManager.getConnection("jdbc:sqlite:" + root.resolve("requests.sqlite3"));
        var statement = db.createStatement()) {
      statement.executeUpdate("UPDATE budget SET bytes=4500000000-2097152+1");
    }
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).isEmpty();
  }

  @Test
  void accessDeniedPersistsAcrossRepositoryInstancesWithoutMoreCalls() {
    status = 403;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThatThrownBy(() -> repository().fetchPresentWeather(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).hasSize(1);
  }

  @Test
  void midnightRestoresPrimaryWhileOriginalCacheRemainsReusable() {
    var previous = repository().fetch(NOW);
    store.block(policy(), 403, 60);
    assertThatThrownBy(() -> repository().fetchPresentWeather(NOW)).isInstanceOf(RainfallException.class);
    when(clock.instant()).thenReturn(NOW.plusSeconds(20));
    assertThat(repository().fetch(NOW)).isEqualTo(previous);
    repository().fetch(NOW.plusSeconds(60));
    assertThat(sent).hasSize(2);
  }

  @Test
  void transportFailureBacksOffAcrossDifferentRequests() {
    timeout = true;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThatThrownBy(() -> repository().fetchPresentWeather(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).hasSize(1);
  }

  @Test
  void responseContainingSecretIsRejectedWithoutCaching() {
    body = KEY;
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThatThrownBy(() -> repository().fetch(NOW)).isInstanceOf(RainfallException.class);
    assertThat(sent).hasSize(1);
  }
}
