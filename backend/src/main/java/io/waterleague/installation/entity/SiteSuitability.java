package io.waterleague.installation.entity;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import java.net.URI;
import java.security.MessageDigest;
import java.util.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

public record SiteSuitability(
    String version,
    String policySha256,
    String status,
    boolean explorationAllowed,
    boolean constructionApproved,
    List<Check> checks) {
  public record Evidence(String title, String url, String sha256, String reference) {}

  public record Check(String id, String status, String reason, Evidence evidence) {}

  private static final JsonNode POLICY;
  private static final String POLICY_HASH;

  static {
    try (var input =
        SiteSuitability.class.getResourceAsStream("/facilities/site-suitability-v1.json")) {
      var raw = Objects.requireNonNull(input).readAllBytes();
      POLICY = new ObjectMapper().readTree(raw);
      POLICY_HASH = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
    } catch (Exception e) {
      throw new ExceptionInInitializerError("설치 적합성 정책 읽기 실패");
    }
  }

  public static SiteSuitability assess(JsonNode cell) {
    String kind = cell.path("kind").asString();
    if (!Set.of("GROUND", "ROOF").contains(kind)) throw invalid();
    var definitions = new LinkedHashSet<String>();
    for (var row : POLICY.path("conditions"))
      for (var k : row.path("kinds"))
        if (k.asString().equals(kind)) definitions.add(row.path("id").asString());
    var supplied = cell.path("siteConditions");
    if (!supplied.isMissingNode()
        && (!supplied.isObject() || !definitions.containsAll(supplied.propertyNames())))
      throw invalid();
    var checks = new ArrayList<Check>();
    for (var id : definitions) {
      var row = supplied.path(id);
      if (row.isMissingNode()) {
        checks.add(new Check(id, "UNKNOWN", POLICY.path("unknownReason").asString(), null));
        continue;
      }
      if (!row.isObject()
          || !Set.copyOf(row.propertyNames()).equals(Set.of("status", "reason", "evidence")))
        throw invalid();
      String state = status(row.path("status")), reason = text(row.path("reason"), 500);
      var source = row.path("evidence");
      Evidence evidence = null;
      if (!source.isNull()) {
        if (!source.isObject()
            || !Set.copyOf(source.propertyNames())
                .equals(Set.of("title", "url", "sha256", "reference"))) throw invalid();
        String title = text(source.path("title"), 300), url = text(source.path("url"), 2000),
            hash = text(source.path("sha256"), 64), reference = text(source.path("reference"), 500);
        try {
          var uri = URI.create(url);
          if (!"https".equals(uri.getScheme())
              || uri.getHost() == null
              || uri.getUserInfo() != null
              || !hash.matches("[a-f0-9]{64}")) throw invalid();
        } catch (IllegalArgumentException e) {
          throw invalid();
        }
        evidence = new Evidence(title, url, hash, reference);
      } else if (!state.equals("UNKNOWN")) throw invalid();
      checks.add(new Check(id, state, reason, evidence));
    }
    var states = new HashSet<String>();
    checks.forEach(check -> states.add(check.status()));
    for (var key : List.of("siteEligibility", "constructionEligibility")) {
      if (cell.has(key)) {
        String state = status(cell.path(key));
        if (state.equals("PROHIBITED") || state.equals("CONDITIONAL")) states.add(state);
      }
    }
    String combined = null;
    for (var state : POLICY.path("priority"))
      if (combined == null && states.contains(state.asString())) combined = state.asString();
    if (combined == null) throw invalid();
    boolean allowed = false;
    for (var state : POLICY.path("explorationAllowed"))
      if (state.asString().equals(combined)) allowed = true;
    return new SiteSuitability(
        POLICY.path("version").asString(), POLICY_HASH, combined, allowed, false, List.copyOf(checks));
  }

  public void requireExplorable() {
    if (!explorationAllowed) throw new DomainException(ErrorCode.SITE_SUITABILITY_RESTRICTED);
  }

  private static String status(JsonNode value) {
    if (value.isString())
      for (var allowed : POLICY.path("priority"))
        if (allowed.asString().equals(value.asString())) return value.asString();
    throw invalid();
  }

  private static String text(JsonNode value, int limit) {
    if (!value.isString() || value.asString().isBlank() || value.asString().length() > limit)
      throw invalid();
    return value.asString();
  }

  private static DomainException invalid() {
    return new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
  }
}
