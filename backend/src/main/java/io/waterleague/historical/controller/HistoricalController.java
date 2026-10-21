package io.waterleague.historical.controller;

import io.waterleague.account.service.AccountService;
import io.waterleague.historical.dto.HistoricalRequest;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.historical.view.HistoricalView;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/historical")
public class HistoricalController {
  private final AccountService accounts;
  private final HistoricalService service;
  private final io.waterleague.historical.service.HistoricalArtifactService artifacts;
  private final io.waterleague.common.security.RateLimitService rates;
  private final io.waterleague.historical.service.HistoricalSubmissionService submissions;

  public HistoricalController(
      AccountService accounts,
      HistoricalService service,
      io.waterleague.historical.service.HistoricalArtifactService artifacts,
      io.waterleague.common.security.RateLimitService rates,
      io.waterleague.historical.service.HistoricalSubmissionService submissions) {
    this.accounts = accounts;
    this.service = service;
    this.artifacts = artifacts;
    this.rates = rates;
    this.submissions = submissions;
  }

  @PostMapping("/submissions")
  public ResponseEntity<io.waterleague.historical.view.HistoricalSubmissionView> submit(
      Principal p,
      @Valid @RequestBody io.waterleague.historical.dto.HistoricalSubmissionRequest dto) {
    var owner = accounts.current(p.getName()).id();
    rates.check("historical-submit:" + owner, 20, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(submissions.submit(owner, dto));
  }

  @PostMapping("/designs/{eventId}/submissions")
  public ResponseEntity<io.waterleague.historical.view.HistoricalSubmissionView> submitSaved(
      Principal p,
      @PathVariable String eventId,
      @Valid @RequestBody io.waterleague.historical.dto.HistoricalDesignSubmissionRequest dto,
      @RequestParam(required = false) UUID competitionId) {
    var owner = accounts.current(p.getName()).id();
    rates.check("historical-submit:" + owner, 20, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(submissions.submitSaved(owner, eventId, dto, competitionId));
  }

  @GetMapping("/submissions")
  public ResponseEntity<List<io.waterleague.historical.view.HistoricalSubmissionView>> submissions(
      Principal p,
      @RequestParam String eventId,
      @RequestParam(required = false) UUID competitionId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(submissions.list(accounts.current(p.getName()).id(), eventId, competitionId));
  }

  @GetMapping("/submissions/{id}")
  public ResponseEntity<io.waterleague.historical.view.HistoricalSubmissionView> submission(
      Principal p, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(submissions.get(accounts.current(p.getName()).id(), id));
  }

  @GetMapping("/leaderboard/{eventId}")
  public ResponseEntity<Object> board(Principal p, @PathVariable String eventId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(submissions.board(eventId, 0, p == null ? null : accounts.current(p.getName()).id()));
  }

  @GetMapping
  public ResponseEntity<List<HistoricalView>> list(
      Principal p, @RequestParam(required = false) UUID competitionId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.list(accounts.current(p.getName()).id(), competitionId));
  }

  @GetMapping("/{id}")
  public ResponseEntity<HistoricalView> get(Principal p, @PathVariable UUID id) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(service.view(service.require(accounts.current(p.getName()).id(), id)));
  }

  @PostMapping
  public ResponseEntity<HistoricalView> create(
      Principal p,
      @Valid @RequestBody HistoricalRequest dto,
      @RequestParam(required = false) UUID competitionId) {
    rates.check("historical:" + accounts.current(p.getName()).id(), 40, 3600);
    return ResponseEntity.accepted()
        .cacheControl(CacheControl.noStore())
        .body(service.create(accounts.current(p.getName()).id(), dto, competitionId));
  }

  @GetMapping("/{id}/bundle")
  public ResponseEntity<byte[]> bundle(Principal p, @PathVariable UUID id) {
    var owner = accounts.current(p.getName()).id();
    rates.check("historical-bundle:" + owner, 20, 3600);
    var value = artifacts.bundle(service.require(owner, id));
    accounts.current(p.getName());
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=waterleague-historical-" + id + ".zip")
        .contentType(MediaType.parseMediaType("application/zip"))
        .body(value);
  }
}
