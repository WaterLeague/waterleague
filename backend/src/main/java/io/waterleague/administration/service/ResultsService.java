package io.waterleague.administration.service;

import io.waterleague.account.entity.Account;
import io.waterleague.administration.repository.ResultsRepository;
import io.waterleague.common.exception.*;
import io.waterleague.historical.service.HistoricalSubmissionService;
import io.waterleague.weekly.service.WeeklyService;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class ResultsService {
  private final ResultsRepository repo;
  private final WeeklyService weekly;
  private final HistoricalSubmissionService historical;

  public ResultsService(
      ResultsRepository repo, WeeklyService weekly, HistoricalSubmissionService historical) {
    this.repo = repo;
    this.weekly = weekly;
    this.historical = historical;
  }

  private void admin(Account a) {
    if (!a.usable() || !a.role().equals("ADMIN"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  public Object seasons(Account a) {
    admin(a);
    return repo.seasons();
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public Object weekly(Account a, LocalDate week, int page) {
    admin(a);
    var period = weekly.archived(week, page);
    return Map.of(
        "period",
        period,
        "installations",
        repo.installations(week, period.players().stream().map(p -> p.playerId()).toList()),
        "page",
        page,
        "hasMore",
        period.participantCount() > (page + 1) * 100L);
  }

  public Object historical(Account a, String event, int page) {
    admin(a);
    return historical.board(event, page);
  }
}
