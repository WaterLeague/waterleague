package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.common.repository.ExternalRequestStore.Unavailable;
import java.nio.file.Path;
import java.time.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExternalRequestStoreTests {
  @TempDir Path root;
  private static final Instant NOW = Instant.parse("2026-10-22T14:59:00Z");
  private final Clock clock = mock(Clock.class);

  private ExternalRequestStore store() {
    when(clock.instant()).thenReturn(NOW);
    return new ExternalRequestStore(root, clock);
  }

  private final ExternalRequestStore.Policy policy =
      ExternalRequestStore.policy("KMA", "test", 3, 1000);

  @Test
  void concurrentInstancesShareOneDownloadAndOriginalTimestamp() throws Exception {
    var store = store();
    var other = new ExternalRequestStore(root, clock);
    var calls = new AtomicInteger();
    java.util.function.Supplier<String> load =
        () -> {
          calls.incrementAndGet();
          try {
            Thread.sleep(150);
          } catch (InterruptedException e) {
            throw new RuntimeException(e);
          }
          return "source bytes";
        };
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var first =
          pool.submit(
              () -> store.acquire(policy, "station=421", Duration.ofSeconds(60), 100, load));
      var second =
          pool.submit(
              () -> other.acquire(policy, "station=421", Duration.ofSeconds(60), 100, load));
      assertThat(first.get()).isEqualTo(second.get());
      assertThat(first.get().fetchedAt()).isEqualTo(NOW);
    }
    assertThat(calls.get()).isEqualTo(1);
    when(clock.instant()).thenReturn(NOW.plusSeconds(30));
    assertThat(
            new ExternalRequestStore(root, clock)
                .acquire(policy, "station=421", Duration.ofSeconds(60), 100, load)
                .fetchedAt())
        .isEqualTo(NOW);
    assertThat(calls.get()).isEqualTo(1);
  }

  @Test
  void reservationsAreAtomicAcrossInstances() throws Exception {
    var store = store();
    var successes = new AtomicInteger();
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      for (int i = 0; i < 12; i++)
        pool.submit(
            () -> {
              try {
                new ExternalRequestStore(root, clock).reserve(policy, 100);
                successes.incrementAndGet();
              } catch (Unavailable expected) {
              }
            });
    }
    assertThat(successes.get()).isEqualTo(3);
    assertThatThrownBy(() -> store.reserve(policy, 100)).isInstanceOf(Unavailable.class);
  }

  @Test
  void authorizationFailureBlocksOtherRequestsUntilKoreanMidnight() {
    var store = store();
    store.reserve(policy, 100);
    store.block(policy, 403, 60);
    assertThatThrownBy(() -> new ExternalRequestStore(root, clock).reserve(policy, 100))
        .isInstanceOf(Unavailable.class);
    store.reserve(ExternalRequestStore.policy("SEOUL_URBAN", "PUBLIC", 3, 1000), 100);
    when(clock.instant()).thenReturn(NOW.plusSeconds(60));
    assertThat(store.reserve(policy, 100)).isEqualTo("2026-10-23");
  }

  @Test
  void expiredSuccessDoesNotHideFailedRefreshAndFailureIsShared() {
    var store = store();
    var calls = new AtomicInteger();
    assertThat(
            store.acquire(policy, "station=421", Duration.ofSeconds(60), 100, () -> "valid").body())
        .isEqualTo("valid");
    when(clock.instant()).thenReturn(NOW.plusSeconds(61));
    java.util.function.Supplier<String> failed =
        () -> {
          calls.incrementAndGet();
          throw new IllegalStateException();
        };
    assertThatThrownBy(
            () -> store.acquire(policy, "station=421", Duration.ofSeconds(60), 100, failed))
        .isInstanceOf(Unavailable.class);
    assertThatThrownBy(
            () -> store.acquire(policy, "station=421", Duration.ofSeconds(60), 100, failed))
        .isInstanceOf(Unavailable.class);
    assertThat(calls.get()).isEqualTo(1);
  }

  @Test
  void byteCeilingStopsCallsAndSuccessfulBodiesReleaseUnusedReservation() {
    var store = store();
    var small = ExternalRequestStore.policy("TEST", "public", 100, 150);
    store.acquire(small, "a", Duration.ofSeconds(60), 100, () -> "x");
    store.reserve(small, 100);
    assertThatThrownBy(() -> store.reserve(small, 100)).isInstanceOf(Unavailable.class);
  }

  @Test
  void providerRetryAfterRemainsBlockedAcrossMidnight() {
    var store = store();
    store.block(policy, 429, 180);
    when(clock.instant()).thenReturn(NOW.plusSeconds(61));
    assertThatThrownBy(() -> store.reserve(policy, 100)).isInstanceOf(Unavailable.class);
    when(clock.instant()).thenReturn(NOW.plusSeconds(181));
    assertThat(store.reserve(policy, 100)).isEqualTo("2026-10-23");
  }
}
