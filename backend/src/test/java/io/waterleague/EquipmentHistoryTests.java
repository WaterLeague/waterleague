package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.disaster.repository.DisasterRepository;
import io.waterleague.disaster.view.DisasterView;
import io.waterleague.infrastructure.entity.EquipmentHistory;
import io.waterleague.infrastructure.repository.*;
import io.waterleague.infrastructure.service.EquipmentHistoryService;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class EquipmentHistoryTests {
  private final JsonService json = new JsonService(new ObjectMapper());

  EquipmentHistoryRepository repository() throws Exception {
    return new EquipmentHistoryRepository(json, new InfrastructureRepository(json));
  }

  EquipmentHistory row(int number) throws Exception {
    return repository().records().stream().filter(r -> r.sourceRow() == number).findFirst().orElseThrow();
  }

  @Test
  void publicRowsPreserveGroupsYearsAndUnresolvedMixedUnits() throws Exception {
    var records = repository().records();
    assertThat(records).hasSize(9);
    assertThat(records.stream().map(EquipmentHistory::assetId).distinct()).hasSize(5);
    assertThat(records.stream().mapToInt(EquipmentHistory::motorCount).sum()).isEqualTo(30);
    assertThat(row(2).installedYear()).isEqualTo(2012);
    assertThat(row(3).installedYear()).isEqualTo(1994);
    assertThat(row(3).expandedYear()).isNull();
    assertThat(row(2).sizeUnitRaw()).isEqualTo("kW(HP)");
    assertThat(json.write(records)).doesNotContain("관리기관연락처", "전기요금", "capacityM3", "02-450");
  }

  @Test
  void futureEquipmentAndLaterExpansionCannotBeUsedAsPastSpecification() throws Exception {
    for (String date : List.of("2010-09-21", "2011-07-27")) {
      var result = EquipmentHistoryService.assess(row(2), LocalDate.parse(date));
      assertThat(result.temporalStatus()).isEqualTo("NOT_INSTALLED_YET");
      assertThat(result.simulationIncluded()).isFalse();
      assertThat(EquipmentHistoryService.assess(row(1), LocalDate.parse(date)).temporalStatus())
          .isEqualTo("LATER_EXPANSION");
    }
  }

  @Test
  void yearPrecisionNeverInventsCommissioningDayOrContinuousOperation() throws Exception {
    for (String date : List.of("2011-01-01", "2011-07-27", "2011-12-31"))
      assertThat(EquipmentHistoryService.assess(row(9), LocalDate.parse(date)).temporalStatus())
          .isEqualTo("INSTALLATION_DATE_UNCERTAIN");
    assertThat(EquipmentHistoryService.assess(row(1), LocalDate.parse("2013-08-01")).temporalStatus())
        .isEqualTo("EXPANSION_DATE_UNCERTAIN");
    assertThat(EquipmentHistoryService.assess(row(9), LocalDate.parse("2010-12-31")).temporalStatus())
        .isEqualTo("NOT_INSTALLED_YET");
    var later = EquipmentHistoryService.assess(row(9), LocalDate.parse("2022-08-08"));
    assertThat(later.temporalStatus()).isEqualTo("INSTALLATION_PRECEDES_EVENT");
    assertThat(later.sourcePrecedesEvent()).isTrue();
    assertThat(later.simulationIncluded()).isFalse();
  }

  @Test
  void onlyServerEventDateUsedAndCurrentReferenceDoesNotClaimCurrentOperation() throws Exception {
    var events = mock(DisasterRepository.class);
    when(events.all()).thenReturn(new DisasterView(List.of(new DisasterView.Event(
        "seoul-20110727", "2011 집중호우", "2011-07-27", "", "", "", List.of()))));
    var service = new EquipmentHistoryService(repository(), events);
    var current = service.view(null);
    assertThat(current.eventDate()).isNull();
    assertThat(current.records()).allSatisfy(r -> {
      assertThat(r.temporalStatus()).isEqualTo("SOURCE_REFERENCE");
      assertThat(r.simulationIncluded()).isFalse();
    });
    var past = service.view("seoul-20110727");
    assertThat(past.eventDate()).isEqualTo("2011-07-27");
    assertThat(past.records().stream().filter(r -> r.temporalStatus().equals("NOT_INSTALLED_YET")))
        .hasSize(1);
    assertThat(json.hash(json.write(current))).isNotEqualTo(json.hash(json.write(past)));
    assertThatThrownBy(() -> service.view("2030-01-01")).isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> service.view("")).isInstanceOf(DomainException.class);
  }
}
