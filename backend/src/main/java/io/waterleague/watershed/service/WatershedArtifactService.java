package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.watershed.entity.WatershedExperiment;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class WatershedArtifactService {
  private final Path root;
  private final JsonService json;

  public WatershedArtifactService(
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

  public byte[] bundle(WatershedExperiment job) {
    if (!job.state().equals("SUCCEEDED") || job.leaseToken() == null)
      throw new DomainException(ErrorCode.CONFLICT);
    try {
      Path directory =
          root.resolve("watersheds")
              .resolve(job.id().toString())
              .resolve(job.leaseToken().toString());
      if (!directory.toRealPath().equals(directory)) throw invalid();
      byte[] manifestBytes = read(directory.resolve("manifest.json"), 256 * 1024);
      var manifest = json.tree(new String(manifestBytes, StandardCharsets.UTF_8));
      if (!manifest.isObject() || manifest.size() > 2000) throw invalid();
      var expectedFiles = json.tree(job.result()).path("artifactFiles");
      if (!expectedFiles.isObject() || manifest.size() != expectedFiles.size() + 1) throw invalid();
      for (String required :
          List.of(
              "request.json",
              "result.json",
              "catalog.json",
              "original.inp",
              "implementation.zip",
              "engine.bin",
              "engine-build.json",
              "engine-source.tar.gz")) if (!manifest.has(required)) throw invalid();
      if (!manifest.path("catalog.json").asString().equals(job.modelHash())) throw invalid();
      byte[] requestBytes = read(directory.resolve("request.json"), 256 * 1024);
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
          if (!name.matches("(?:baseline/|strategy/)?[a-z][a-z0-9_.-]{0,70}")
              || name.contains("..")) throw invalid();
          byte[] bytes = read(directory.resolve(name), 64 * 1024 * 1024);
          total += bytes.length;
          if (total > 512L * 1024 * 1024) throw invalid();
          String hash =
              HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
          if (!hash.equals(manifest.path(name).asString())) throw invalid();
          if (!name.equals("result.json") && !hash.equals(expectedFiles.path(name).asString()))
            throw invalid();
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
