package io.waterleague.historical.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.entity.HistoricalExperiment;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class HistoricalArtifactService {
  private final Path root;
  private final JsonService json;

  public HistoricalArtifactService(
      @Value("${waterleague.artifacts}") String path, JsonService json) {
    root = Path.of(path).toAbsolutePath().normalize();
    this.json = json;
  }

  private DomainException invalid() {
    return new DomainException(ErrorCode.SIMULATION_UNAVAILABLE);
  }

  private byte[] read(Path path, int max) throws IOException {
    if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
        || !path.toRealPath().equals(path)
        || Files.size(path) > max) throw invalid();
    try (var in = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
      byte[] value = in.readNBytes(max + 1);
      if (value.length > max) throw invalid();
      return value;
    }
  }

  public byte[] bundle(HistoricalExperiment job) {
    if (!job.state().equals("SUCCEEDED") || job.leaseToken() == null)
      throw new DomainException(ErrorCode.CONFLICT);
    try {
      Path directory =
          root.resolve("historical")
              .resolve(job.id().toString())
              .resolve(job.leaseToken().toString());
      if (!directory.toRealPath().equals(directory)) throw invalid();
      boolean submission =
          !json.tree(job.placements()).isEmpty()
              && json.tree(job.placements()).get(0).has("submissionPolicy");
      byte[] manifestBytes =
          read(directory.resolve("manifest.json"), (submission ? 1024 : 256) * 1024);
      var manifest = json.tree(new String(manifestBytes, StandardCharsets.UTF_8));
      if (!manifest.isObject() || manifest.size() > (submission ? 5000 : 2000)) throw invalid();
      for (String required :
          submission
              ? List.of(
                  "request.json",
                  "result.json",
                  "submission.py",
                  "historical.py",
                  "submission-rules.json",
                  "submission-request.json")
              : List.of("request.json", "result.json", "rainfall-model.json", "historical.py"))
        if (!manifest.has(required)) throw invalid();
      if (!submission && !manifest.path("rainfall-model.json").asString().equals(job.modelHash()))
        throw invalid();
      if (submission
          && !manifest
              .path("submission-rules.json")
              .asString()
              .equals(json.tree(job.placements()).get(0).path("submissionRulesHash").asString()))
        throw invalid();
      var head = json.tree(job.placements()).get(0);
      if (submission
          && head.has("submissionDesignSnapshotSha256")
          && !manifest
              .path("submission-design.json")
              .asString()
              .equals(head.path("submissionDesignSnapshotSha256").asString())) throw invalid();
      byte[] requestBytes =
          read(directory.resolve("request.json"), (submission ? 2048 : 256) * 1024);
      var request = json.tree(new String(requestBytes, StandardCharsets.UTF_8));
      if (!request.path("inputHash").asString().equals(job.inputHash())
          || !request.path("modelHash").asString().equals(job.modelHash())
          || !request.path("placements").asString().equals(job.placements())) throw invalid();
      var output = new ByteArrayOutputStream();
      long total = 0;
      try (var zip = new ZipOutputStream(output)) {
        zip.putNextEntry(new ZipEntry("manifest.json"));
        zip.write(manifestBytes);
        zip.closeEntry();
        for (String name : manifest.propertyNames()) {
          String pattern =
              submission
                  ? "(?:(?:[0-9]{7}/)?[0-9]{1,2}/|[0-9]{7}/)?[a-z][a-z0-9_.-]{0,70}"
                  : "(?:[0-9]{1,2}/|sensitivity/)?[a-z][a-z0-9_.-]{0,70}";
          if (!name.matches(pattern) || name.contains("..")) throw invalid();
          byte[] bytes = read(directory.resolve(name), 64 * 1024 * 1024);
          total += bytes.length;
          if (total > 512L * 1024 * 1024) throw invalid();
          String hash =
              HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
          if (!hash.equals(manifest.path(name).asString())) throw invalid();
          if (name.equals("result.json")
              && !json.tree(new String(bytes, StandardCharsets.UTF_8))
                  .equals(json.tree(job.result()))) throw invalid();
          zip.putNextEntry(new ZipEntry(name));
          zip.write(bytes);
          zip.closeEntry();
          if (output.size() > 64 * 1024 * 1024) throw invalid();
        }
      }
      return output.toByteArray();
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw invalid();
    }
  }
}
