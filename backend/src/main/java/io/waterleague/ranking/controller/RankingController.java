package io.waterleague.ranking.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.ranking.service.SubmissionService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.security.Principal;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
public class RankingController {
  private final AccountService accounts;
  private final SubmissionService submissions;

  public RankingController(AccountService a, SubmissionService s) {
    accounts = a;
    submissions = s;
  }

  public record Submission(@NotNull UUID jobId) {}

  @GetMapping("/api/v1/leaderboard")
  public Object board(@RequestParam(required = false) String modelHash) {
    return submissions.leaderboard(modelHash);
  }

  @PostMapping("/api/v1/submissions")
  public Object submit(@Valid @RequestBody Submission dto, Principal p) {
    return submissions.submit(accounts.current(p.getName()).id(), dto.jobId());
  }
}
