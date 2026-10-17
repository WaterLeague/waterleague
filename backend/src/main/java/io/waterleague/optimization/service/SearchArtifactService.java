package io.waterleague.optimization.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.optimization.entity.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.zip.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SearchArtifactService {
  private static final long MAX_BYTES = 64L * 1024 * 1024;
  private static final List<String> FILES =
      List.of(
          "builder.py",
          "model-source.json",
          "model.json",
          "placements.json",
          "request.json",
          "result.json",
          "baseline.inp",
          "baseline.rpt",
          "baseline.out",
          "strategy.inp",
          "strategy.rpt",
          "strategy.out",
          "low.inp",
          "low.rpt",
          "low.out",
          "high.inp",
          "high.rpt",
          "high.out");
  private final Path root;
  private final JsonService json;

  public SearchArtifactService(@Value("${waterleague.artifacts}") String path, JsonService json) {
    root = Path.of(path).toAbsolutePath().normalize();
    this.json = json;
  }

  public byte[] bundle(
      ResearchSearch search, ResearchCandidate candidate, List<UUID> sources, Runnable authorize) {
    authorize.run();
    try {
      var dbResult = json.tree(candidate.result());
      String token = UUID.fromString(dbResult.path("artifactToken").asString()).toString();
      Path directory =
          root.resolve("research-candidates").resolve(candidate.id().toString()).resolve(token);
      if (!directory.toRealPath().equals(directory)) throw quality();
      byte[] rawManifest = read(directory.resolve("manifest.json"), 64 * 1024);
      var manifest = json.tree(new String(rawManifest, StandardCharsets.UTF_8));
      Set<String> names = new HashSet<>();
      manifest.propertyNames().forEach(names::add);
      if (!manifest.isObject() || !names.equals(new HashSet<>(FILES))) throw quality();
      Map<String, byte[]> entries = new LinkedHashMap<>();
      entries.put("manifest.json", rawManifest);
      long total = rawManifest.length;
      for (String name : FILES) {
        byte[] bytes = read(directory.resolve(name), MAX_BYTES - total);
        total += bytes.length;
        String expected = manifest.path(name).asString();
        if (!expected.matches("[a-f0-9]{64}") || !digest(bytes).equals(expected)) throw quality();
        entries.put(name, bytes);
      }
      if (!digest(entries.get("model-source.json")).equals(candidate.modelHash())) throw quality();
      var request = json.tree(new String(entries.get("request.json"), StandardCharsets.UTF_8));
      var placements = json.tree(candidate.placements());
      if (!candidate.modelHash().equals(request.path("modelHash").asString())
          || !candidate.inputHash().equals(request.path("inputHash").asString())
          || !request.path("placements").equals(placements)
          || !json.tree(new String(entries.get("placements.json"), StandardCharsets.UTF_8))
              .equals(placements)) throw quality();
      var fileResult = json.tree(new String(entries.get("result.json"), StandardCharsets.UTF_8));
      var publicResult =
          ((tools.jackson.databind.node.ObjectNode) dbResult.deepCopy())
              .without(List.of("artifactToken", "modelHash", "inputHash"));
      if (!fileResult.equals(publicResult)) throw quality();
      entries.put("search-provenance.json", search.provenance().getBytes(StandardCharsets.UTF_8));
      var scope = new LinkedHashMap<String, Object>();
      scope.put("purpose", "RESEARCH_PATTERN_SEARCH");
      scope.put("organizationId", search.organizationId());
      scope.put("searchId", search.id());
      scope.put("candidateId", candidate.id());
      scope.put("sourceJobIds", sources);
      scope.put("modelHash", candidate.modelHash());
      scope.put("inputHash", candidate.inputHash());
      scope.put("requestHash", search.requestHash());
      scope.put("provenanceHash", search.provenanceHash());
      scope.put("exportedAt", Instant.now());
      scope.put("notice", "가정 기반 연구 후보. 현장 효과·안전 승인 아님. 동의 철회는 이후 접근에 적용.");
      entries.put("access-scope.json", json.write(scope).getBytes(StandardCharsets.UTF_8));
      if (entries.values().stream().mapToLong(b -> b.length).sum() > MAX_BYTES) throw quality();
      var output = new ByteArrayOutputStream();
      try (var zip = new ZipOutputStream(output)) {
        for (var entry : entries.entrySet()) {
          zip.putNextEntry(new ZipEntry(entry.getKey()));
          zip.write(entry.getValue());
          zip.closeEntry();
        }
      }
      authorize.run();
      return output.toByteArray();
    } catch (DomainException e) {
      throw e;
    } catch (NoSuchFileException e) {
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    } catch (Exception e) {
      throw quality();
    }
  }

  private byte[] read(Path file, long maximum) throws IOException {
    if (maximum < 0
        || !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
        || Files.isSymbolicLink(file)) throw quality();
    if (Files.getFileStore(file).supportsFileAttributeView("unix")
        && ((Number) Files.getAttribute(file, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue()
            != 1) throw quality();
    // 크기 확인 후 파일이 증가해도 제한을 넘겨 메모리에 적재하지 않는다.
    try (var channel =
            Files.newByteChannel(file, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS));
        var output = new ByteArrayOutputStream()) {
      var buffer = ByteBuffer.allocate(65536);
      long count = 0;
      while (channel.read(buffer) != -1) {
        buffer.flip();
        count += buffer.remaining();
        if (count > maximum) throw quality();
        output.write(buffer.array(), 0, buffer.remaining());
        buffer.clear();
      }
      return output.toByteArray();
    }
  }

  private String digest(byte[] value) throws java.security.NoSuchAlgorithmException {
    return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
  }

  private static DomainException quality() {
    return new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
  }
}
