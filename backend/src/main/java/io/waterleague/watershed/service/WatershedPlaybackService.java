package io.waterleague.watershed.service;

import io.waterleague.account.service.AccountService;
import io.waterleague.watershed.repository.WatershedPlaybackRepository;
import io.waterleague.watershed.view.WatershedPlaybackView;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class WatershedPlaybackService {
  private final AccountService accounts;
  private final WatershedService jobs;
  private final WatershedPlaybackRepository playback;

  public WatershedPlaybackService(
      AccountService accounts, WatershedService jobs, WatershedPlaybackRepository playback) {
    this.accounts = accounts;
    this.jobs = jobs;
    this.playback = playback;
  }

  public WatershedPlaybackView.Catalog catalog(String name, UUID id) {
    var job = jobs.require(accounts.current(name).id(), id);
    var result = playback.catalog(job);
    jobs.require(accounts.current(name).id(), id);
    return result;
  }

  public WatershedPlaybackView.Frame frame(String name, UUID id, double seconds) {
    var job = jobs.require(accounts.current(name).id(), id);
    var result = playback.frame(job, seconds);
    jobs.require(accounts.current(name).id(), id);
    return result;
  }
}
