package io.waterleague.weekly.service;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.weekly.repository.WeeklySettlementRepository;
import io.waterleague.weekly.view.WeeklyView;
import java.time.LocalDate;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class WeeklySettlementService {
  private final WeeklyService weekly;
  private final WeeklySettlementRepository repository;
  private final DistrictRepository districts;

  public WeeklySettlementService(
      WeeklyService weekly, WeeklySettlementRepository repository, DistrictRepository districts) {
    this.weekly = weekly;
    this.repository = repository;
    this.districts = districts;
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public WeeklyView dashboard(String username) {
    var value = weekly.dashboard(username);
    return new WeeklyView(
        value.generatedAt(),
        value.ruleVersion(),
        value.validationLevel(),
        value.scorePolicy(),
        settle(value.current(), false),
        settle(value.previous(), false));
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public WeeklyView.Period archived(LocalDate week, int page) {
    return settle(weekly.archived(week, page), true);
  }

  private WeeklyView.Period settle(WeeklyView.Period p, boolean archive) {
    var periods =
        repository.exclusions(p.weekStart(), archive).stream()
            .map(
                e ->
                    new WeeklyView.ExcludedPeriod(
                        e.districtId(),
                        districts.require(e.districtId()).name(),
                        e.stationId(),
                        e.startsAt(),
                        e.endsAt(),
                        e.installationCount(),
                        e.excludedSeconds()))
            .toList();
    long excluded = periods.stream().mapToLong(WeeklyView.ExcludedPeriod::excludedSeconds).sum();
    if (excluded < 0 || excluded > p.expectedSeconds() - p.evaluatedSeconds())
      throw new DomainException(ErrorCode.SIMULATION_UNAVAILABLE);
    String status = p.status();
    // 점수·원래 예상 시간은 보존하며 확인된 말단 결측만 정산 완료 조건에 더한다.
    if (status.equals("PROVISIONAL")
        && excluded > 0
        && p.evaluatedTarget().equals(p.endsAt())
        && p.evaluatedSeconds() + excluded == p.expectedSeconds()) status = "FINAL";
    var winners =
        status.equals("FINAL")
            ? p.districts().stream()
                .filter(
                    d ->
                        Integer.valueOf(1).equals(d.rank())
                            && d.scoreM3() != null
                            && d.scoreM3().signum() > 0)
                .map(WeeklyView.District::districtId)
                .toList()
            : List.<String>of();
    return new WeeklyView.Period(
        p.weekStart(),
        p.startsAt(),
        p.endsAt(),
        p.evaluatedTarget(),
        status,
        p.comparisonStatus(),
        p.comparisonReason(),
        p.comparisonGroupHash(),
        p.evaluatedSeconds(),
        p.expectedSeconds(),
        p.districts(),
        p.players(),
        p.participantCount(),
        p.own(),
        winners,
        new WeeklyView.Settlement(
            "CLOSED_WEEK_MISSING_SUFFIX_V1",
            excluded,
            periods.stream().mapToLong(WeeklyView.ExcludedPeriod::installationCount).sum(),
            periods));
  }
}
