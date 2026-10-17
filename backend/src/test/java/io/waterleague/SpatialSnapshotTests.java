package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.account.entity.Account;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.spatial.mapper.SpatialMapper;
import io.waterleague.spatial.repository.SpatialSnapshotRepository;
import io.waterleague.spatial.service.SpatialService;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import tools.jackson.databind.ObjectMapper;

class SpatialSnapshotTests {
  private final ClassPathResource data = new ClassPathResource("spatial/seongsu-buildings.json");
  private final ClassPathResource digest =
      new ClassPathResource("spatial/seongsu-buildings.sha256");

  @Test
  void servesBundledOfficialSnapshotWithoutReadingOrFetchingOnEachRequest() {
    var repository = spy(new SpatialSnapshotRepository(data, digest));
    var limits = mock(RateLimitService.class);
    var actor = mock(Account.class);
    when(actor.id()).thenReturn(UUID.randomUUID());
    var service = new SpatialService(repository, new SpatialMapper(new ObjectMapper()), limits);
    var first = service.buildings(actor);
    var second = service.buildings(actor);
    assertThat(second).isSameAs(first);
    assertThat(first.buildings()).hasSize(246);
    assertThat(first.dataYear()).isEqualTo(2025);
    assertThat(first.snapshotHash())
        .isEqualTo("c9939a2cc22961daf9834e2ad76e91c14cf8c85f8c9535dd7c2e0e5f70e858a2");
    verify(repository, times(1)).snapshot();
    verify(limits, times(2)).check("spatial-account:" + actor.id(), 60, 60);
  }

  @Test
  void rejectsTamperedMissingAndOversizedDataBeforeServing() {
    assertThatThrownBy(
            () ->
                new SpatialSnapshotRepository(
                    new ByteArrayResource("tampered".getBytes(StandardCharsets.UTF_8)), digest))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> new SpatialSnapshotRepository(new ClassPathResource("missing.json"), digest))
        .isInstanceOf(DomainException.class)
        .hasMessageNotContaining("missing.json");
    assertThatThrownBy(
            () -> new SpatialSnapshotRepository(new ByteArrayResource(new byte[2_000_001]), digest))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> new SpatialSnapshotRepository(data, new ByteArrayResource(new byte[0])))
        .isInstanceOf(DomainException.class);
  }
}
