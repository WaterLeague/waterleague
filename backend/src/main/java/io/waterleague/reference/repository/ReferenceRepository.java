package io.waterleague.reference.repository;

import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class ReferenceRepository {
  private final JsonNode report;
  private final String source;
  private final String ledger;
  private final String hash;

  public ReferenceRepository(JsonService json) throws java.io.IOException {
    source = read("cpu-reference.json");
    ledger = read("cpu-search-ledger.json");
    report = json.tree(source);
    hash = json.hash(source);
    if (!report.path("ledgerSha256").asString().equals(json.hash(ledger))
        || report.path("official").asBoolean()
        || !report.path("validationLevel").asString().equals("EXPLORATORY")
        || !report.path("kind").asString().equals("CPU_REFERENCE"))
      throw new IllegalStateException("CPU 기준안 등록 계약 불일치");
  }

  private static String read(String name) throws java.io.IOException {
    try (var stream = new ClassPathResource("models/" + name).getInputStream()) {
      byte[] bytes = stream.readNBytes(2 * 1024 * 1024 + 1);
      if (bytes.length > 2 * 1024 * 1024) throw new IllegalStateException("CPU 자료 크기 초과");
      return new String(bytes, StandardCharsets.UTF_8);
    }
  }

  public JsonNode report() {
    return report;
  }

  public String source() {
    return source;
  }

  public String ledger() {
    return ledger;
  }

  public String hash() {
    return hash;
  }
}
