package io.waterleague.gameanalysis.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.gameanalysis.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class GameAnalysisController {
  private final GameAnalysisService analyses;
  private final GameSummaryService summaries;
  private final AccountService accounts;
  private final RateLimitService rates;

  public GameAnalysisController(
      GameAnalysisService analyses,
      GameSummaryService summaries,
      AccountService accounts,
      RateLimitService rates) {
    this.analyses = analyses;
    this.summaries = summaries;
    this.accounts = accounts;
    this.rates = rates;
  }

  public record SummaryRequest(@NotNull @Pattern(regexp = "[a-f0-9]{64}") String snapshotHash) {}

  private ResponseEntity<Object> response(Object value) {
    return ResponseEntity.ok().header("Cache-Control", "no-store").body(value);
  }

  @GetMapping("/admin/results/weekly/analytics")
  public Object weekly(Principal p, @RequestParam LocalDate week) {
    return response(analyses.weekly(accounts.current(p.getName()), week));
  }

  @GetMapping("/admin/results/historical/{event}/analytics")
  public Object historical(Principal p, @PathVariable String event) {
    return response(analyses.historical(accounts.current(p.getName()), event));
  }

  @GetMapping("/competitions/{id}/analytics")
  public Object competition(Principal p, @PathVariable UUID id) {
    return response(analyses.competition(accounts.current(p.getName()), id));
  }

  @PostMapping("/admin/results/weekly/analytics/summary")
  public Object weeklySummary(
      Principal p, @RequestParam LocalDate week, @Valid @RequestBody SummaryRequest request) {
    var a = accounts.current(p.getName());
    var data = analyses.weekly(a, week);
    rates.check("game-summary:" + a.id(), 12, 3600);
    return response(summaries.summarize(data, request.snapshotHash()));
  }

  @PostMapping("/admin/results/historical/{event}/analytics/summary")
  public Object historicalSummary(
      Principal p, @PathVariable String event, @Valid @RequestBody SummaryRequest request) {
    var a = accounts.current(p.getName());
    var data = analyses.historical(a, event);
    rates.check("game-summary:" + a.id(), 12, 3600);
    return response(summaries.summarize(data, request.snapshotHash()));
  }

  @PostMapping("/competitions/{id}/analytics/summary")
  public Object competitionSummary(
      Principal p, @PathVariable UUID id, @Valid @RequestBody SummaryRequest request) {
    var a = accounts.current(p.getName());
    var data = analyses.competition(a, id);
    rates.check("game-summary:" + a.id(), 12, 3600);
    return response(summaries.summarize(data, request.snapshotHash()));
  }
}
