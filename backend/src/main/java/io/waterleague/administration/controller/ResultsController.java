package io.waterleague.administration.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.administration.service.ResultsService;
import java.security.Principal;
import java.time.LocalDate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/admin/results")
public class ResultsController {
  private final AccountService accounts;
  private final ResultsService results;

  public ResultsController(AccountService accounts, ResultsService results) {
    this.accounts = accounts;
    this.results = results;
  }

  @GetMapping("/seasons")
  public Object seasons(Principal p) {
    return results.seasons(accounts.current(p.getName()));
  }

  @GetMapping("/weekly")
  public Object weekly(
      Principal p, @RequestParam LocalDate week, @RequestParam(defaultValue = "0") int page) {
    return results.weekly(accounts.current(p.getName()), week, page);
  }

  @GetMapping("/historical/{eventId}")
  public Object historical(
      Principal p, @PathVariable String eventId, @RequestParam(defaultValue = "0") int page) {
    return results.historical(accounts.current(p.getName()), eventId, page);
  }
}
