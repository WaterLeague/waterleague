package io.waterleague.infrastructure.service;

import io.waterleague.common.exception.*;
import io.waterleague.disaster.repository.DisasterRepository;
import io.waterleague.infrastructure.entity.EquipmentHistory;
import io.waterleague.infrastructure.repository.EquipmentHistoryRepository;
import io.waterleague.infrastructure.view.EquipmentHistoryView;
import java.time.LocalDate;
import org.springframework.stereotype.Service;

@Service
public class EquipmentHistoryService {
  private final EquipmentHistoryRepository repository;
  private final DisasterRepository disasters;

  public EquipmentHistoryService(EquipmentHistoryRepository repository, DisasterRepository disasters) {
    this.repository = repository;
    this.disasters = disasters;
  }

  public EquipmentHistoryView view(String eventId) {
    LocalDate date = eventId == null ? null : disasters.all().events().stream()
        .filter(e -> e.id().equals(eventId)).map(e -> LocalDate.parse(e.eventDate())).findFirst()
        .orElseThrow(() -> new DomainException(ErrorCode.REQUEST_INVALID));
    return new EquipmentHistoryView(EquipmentHistoryRepository.VERSION, EquipmentHistoryRepository.SHA256,
        "REFERENCE_HISTORY_ONLY", repository.source(), eventId, date == null ? null : date.toString(),
        repository.records().stream().map(row -> assess(row, date)).toList());
  }

  public static EquipmentHistoryView.Entry assess(EquipmentHistory row, LocalDate date) {
    String status = "SOURCE_REFERENCE";
    if (date != null) {
      int year = date.getYear();
      // 연 단위 설치·증설 기록에서 특정 가동일이나 과거 용량을 만들지 않는다.
      if (year < row.installedYear()) status = "NOT_INSTALLED_YET";
      else if (year == row.installedYear()) status = "INSTALLATION_DATE_UNCERTAIN";
      else if (row.expandedYear() != null && year < row.expandedYear()) status = "LATER_EXPANSION";
      else if (row.expandedYear() != null && year == row.expandedYear()) status = "EXPANSION_DATE_UNCERTAIN";
      else status = "INSTALLATION_PRECEDES_EVENT";
    }
    return new EquipmentHistoryView.Entry(row, status,
        date != null && date.isAfter(LocalDate.parse(row.referenceDate())), false);
  }
}
