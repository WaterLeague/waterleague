package io.waterleague.weekly.service;

import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.weekly.repository.WeeklySeasonRepository;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WeeklySeasonService {
  private final WeeklySeasonRepository repository;
  private final BudgetRepository budget;

  public WeeklySeasonService(WeeklySeasonRepository repository, BudgetRepository budget) {
    this.repository = repository;
    this.budget = budget;
  }

  public Instant now() {
    return repository.now();
  }

  public static Instant endFor(Instant instant) {
    return instant
        .atZone(ZoneId.of("Asia/Seoul"))
        .toLocalDate()
        .with(TemporalAdjusters.next(DayOfWeek.MONDAY))
        .atStartOfDay(ZoneId.of("Asia/Seoul"))
        .toInstant();
  }

  @Transactional
  public void closeOwner(UUID owner) {
    budget.lock(owner);
    closeLocked(owner, now());
  }

  @Transactional
  public void closeOwnerAt(UUID owner, Instant at) {
    budget.lock(owner);
    closeLocked(owner, at);
  }

  private void closeLocked(UUID owner, Instant at) {
    var ids = repository.lockExpired(owner, at);
    for (var id : ids) {
      repository.close(id);
      budget.release(id, owner);
    }
  }
}
