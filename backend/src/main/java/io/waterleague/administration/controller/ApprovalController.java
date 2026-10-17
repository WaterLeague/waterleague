package io.waterleague.administration.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.administration.dto.ReviewRequest;
import io.waterleague.administration.service.ApprovalService;
import io.waterleague.common.security.RateLimitService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import java.security.Principal;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/admin/members")
public class ApprovalController {
  private final AccountService accounts;
  private final ApprovalService approvals;
  private final RateLimitService rates;

  public ApprovalController(AccountService a, ApprovalService s, RateLimitService r) {
    accounts = a;
    approvals = s;
    rates = r;
  }

  @GetMapping
  public Object list(
      @RequestParam(defaultValue = "PENDING")
          @Pattern(regexp = "PENDING|APPROVED|REJECTED|SUSPENDED|ALL")
          String status,
      @RequestParam(defaultValue = "") @Pattern(regexp = "|[a-f0-9-]{36}") String after,
      Principal p) {
    return approvals.list(accounts.current(p.getName()), status, after);
  }

  @GetMapping("/{id}/reviews")
  public Object history(@PathVariable UUID id, Principal p) {
    return approvals.history(accounts.current(p.getName()), id);
  }

  @PostMapping("/{id}/reviews")
  public Object review(@PathVariable UUID id, @Valid @RequestBody ReviewRequest d, Principal p) {
    var a = accounts.current(p.getName());
    rates.check("approval:" + a.id(), 100, 3600);
    return approvals.review(a, id, d);
  }
}
