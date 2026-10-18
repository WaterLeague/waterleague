package io.waterleague.weekly.service;

import io.waterleague.weekly.repository.WeeklySeasonRepository;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class WeeklySeasonCloser {
  private final WeeklySeasonRepository repository;
  private final WeeklySeasonService seasons;

  public WeeklySeasonCloser(WeeklySeasonRepository repository, WeeklySeasonService seasons) {
    this.repository = repository;
    this.seasons = seasons;
  }

  @Scheduled(fixedDelay = 60000, initialDelay = 60000)
  public void close() {
    var owners = repository.dueOwners();
    for (var owner : owners) seasons.closeOwner(owner);
  }
}
