package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.rainfall.mapper.KmaObservationMapper;
import io.waterleague.rainfall.repository.KmaLiveRepository;
import io.waterleague.rainfall.service.LiveRainfallService;
import java.time.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class LiveRainfallTests {
  private static String row(Instant at, String rainfall) {
    return KmaObservationMapper.TIME.format(at.atZone(KmaObservationMapper.KST))
        + " 421 0 0 0 0 0 0 20 0 "
        + rainfall
        + " 0 5 5 60 1000 1010 10";
  }

  private static String response(String rows) {
    return "#START7777\n# RN-15m RN-60m RN-12H RN-DAY\n" + rows + "\n#7777END\n";
  }

  @Test
  void preservesObservedZeroAndMissingWithoutFilling() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    var zero = KmaObservationMapper.parse(response(row(at, "0")), at).get("421");
    assertThat(zero.fifteenMinuteMm()).isZero();
    assertThat(zero.dayMm()).isEqualByComparingTo("5");
    assertThat(zero.observedAt()).isEqualTo(at);
    assertThat(zero.complete()).isTrue();
    var missing = KmaObservationMapper.parse(response(row(at, "-99.9")), at).get("421");
    assertThat(missing.fifteenMinuteMm()).isNull();
    assertThat(missing.complete()).isFalse();
  }

  @Test
  void rejectsDuplicateWrongTimeAndInvalidValues() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    for (String bad : List.of("-1", "NaN", "Infinity", "5001"))
      assertThatThrownBy(() -> KmaObservationMapper.parse(response(row(at, bad)), at))
          .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> KmaObservationMapper.parse(response(row(at, "0") + "\n" + row(at, "0")), at))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> KmaObservationMapper.parse(response(row(at.minusSeconds(60), "0")), at))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> KmaObservationMapper.parse("invalid provider output", at))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void fetchesEveryRequestAndNeverFallsBackAfterFailure() {
    var source = mock(KmaLiveRepository.class);
    var districts = mock(DistrictRepository.class);
    when(districts.all())
        .thenReturn(
            List.of(
                new io.waterleague.district.entity.District(
                    "2419947", "성동구", "map", "hash", List.of(0.0, 0.0), "421", "성동")));
    when(source.fetch(any()))
        .thenAnswer(call -> response(row(call.getArgument(0), "0")))
        .thenThrow(new DomainException(ErrorCode.RAINFALL_UNAVAILABLE));
    var service = new LiveRainfallService(source, districts);
    assertThat(service.latest().districts().getFirst().status()).isEqualTo("CURRENT");
    assertThatThrownBy(service::latest).isInstanceOf(DomainException.class);
    verify(source, times(2)).fetch(any());
  }
}
