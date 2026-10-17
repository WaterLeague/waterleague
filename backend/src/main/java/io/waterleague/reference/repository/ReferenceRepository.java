package io.waterleague.reference.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.reference.entity.ReferenceDocument;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class ReferenceRepository {
  private final Map<String, ReferenceDocument> byModel;
  private final List<ReferenceDocument> documents;

  public ReferenceRepository(JsonService json) throws java.io.IOException {
    var registry = json.tree(read("reference-catalog.json"));
    if (registry.path("schemaVersion").asInt() != 1
        || !registry.path("references").isArray()
        || registry.path("references").size() < 1
        || registry.path("references").size() > 20)
      throw new IllegalStateException("CPU 기준안 목록 오류");
    Map<String, ReferenceDocument> models = new HashMap<>();
    List<ReferenceDocument> entries = new ArrayList<>();
    Set<String> files = new HashSet<>();
    for (var entry : registry.path("references")) {
      String reportFile = entry.path("reportFile").asString(),
          ledgerFile = entry.path("ledgerFile").asString();
      for (String file : List.of(reportFile, ledgerFile))
        if (!file.matches("cpu-[a-z0-9-]{1,80}\\.json") || !files.add(file))
          throw new IllegalStateException("CPU 자료 파일명 오류");
      String source = read(reportFile), ledger = read(ledgerFile), hash = json.hash(source);
      var report = json.tree(source);
      if (!hash.equals(entry.path("reportSha256").asString())
          || !report.path("ledgerSha256").asString().equals(json.hash(ledger))
          || report.path("official").asBoolean()
          || !report.path("validationLevel").asString().equals("EXPLORATORY")
          || !report.path("kind").asString().equals("CPU_REFERENCE")
          || !report.path("modelHashes").equals(entry.path("modelHashes"))
          || !report.path("modelHashes").isArray()
          || report.path("modelHashes").size() < 2)
        throw new IllegalStateException("CPU 기준안 등록 계약 불일치");
      List<String> hashes = new ArrayList<>();
      for (var node : report.path("modelHashes")) {
        String modelHash = node.asString();
        if (!modelHash.matches("[a-f0-9]{64}") || hashes.contains(modelHash))
          throw new IllegalStateException("CPU 모델 식별자 오류");
        hashes.add(modelHash);
      }
      if (!hashes.contains(report.path("trainingModelHash").asString()))
        throw new IllegalStateException("CPU 탐색 모델 누락");
      var document = new ReferenceDocument(hash, source, ledger, report, List.copyOf(hashes));
      entries.add(document);
      for (String modelHash : hashes)
        if (models.putIfAbsent(modelHash, document) != null)
          throw new IllegalStateException("CPU 모델 중복 연결");
    }
    byModel = Map.copyOf(models);
    documents = List.copyOf(entries);
  }

  private static String read(String name) throws java.io.IOException {
    try (var stream = new ClassPathResource("models/" + name).getInputStream()) {
      byte[] bytes = stream.readNBytes(2 * 1024 * 1024 + 1);
      if (bytes.length > 2 * 1024 * 1024) throw new IllegalStateException("CPU 자료 크기 초과");
      return new String(bytes, StandardCharsets.UTF_8);
    }
  }

  public ReferenceDocument require(String modelHash) {
    var result = byModel.get(modelHash);
    if (result == null) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return result;
  }

  public List<ReferenceDocument> all() {
    return documents;
  }
}
