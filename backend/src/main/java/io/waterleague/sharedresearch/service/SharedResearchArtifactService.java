package io.waterleague.sharedresearch.service;

import io.waterleague.budget.view.BudgetRecordEvidence;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.sharedresearch.entity.SharedResearchJob;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class SharedResearchArtifactService {
  private final Path root;
  private final JsonService json;

  public SharedResearchArtifactService(
      @Value("${waterleague.artifacts}") String root, JsonService json) {
    this.root = Path.of(root).toAbsolutePath().normalize();
    this.json = json;
  }

  private DomainException invalid() {
    return new DomainException(ErrorCode.SIMULATION_UNAVAILABLE);
  }

  private byte[] read(Path p, int max) throws IOException {
    return io.waterleague.common.storage.ArtifactFiles.read(p, max);
  }

  private String hash(byte[] bytes) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (Exception e) {
      throw invalid();
    }
  }

  private JsonNode tree(byte[] bytes) {
    return json.tree(new String(bytes, StandardCharsets.UTF_8));
  }

  private record Archive(Path directory, byte[] manifestBytes, JsonNode manifest) {}

  private Archive archive(SharedResearchJob job) throws IOException {
    if (job.leaseToken() == null || job.manifestHash() == null)
      throw new DomainException(ErrorCode.CONFLICT);
    var dir =
        root.resolve("shared-physics")
            .resolve(job.id().toString())
            .resolve(job.leaseToken().toString());
    if (!dir.toRealPath().equals(dir)) throw invalid();
    var bytes = read(dir.resolve("manifest.json"), 8 * 1024 * 1024);
    if (!hash(bytes).equals(job.manifestHash())) throw invalid();
    var manifest = tree(bytes);
    if (!manifest.isObject() || manifest.size() > 50000) throw invalid();
    for (String required :
        List.of("request.json", "model-source.json", "forcing.json", "result.json", "weekly.py"))
      if (!manifest.has(required)) throw invalid();
    var archive = new Archive(dir, bytes, manifest);
    var requestBytes = file(archive, "request.json");
    if (!hash(requestBytes).equals(job.inputHash())) throw invalid();
    var req = tree(requestBytes);
    var placement = req.path("placement");
    if (!req.path("installationId").asString().equals(job.installationId().toString())
        || !req.path("siteModelHash").asString().equals(job.siteModelHash())
        || !placement.path("cellId").asString().equals(job.cellId())
        || !placement.path("facilityType").asString().equals(job.facilityType())
        || placement.path("areaM2").decimalValue().compareTo(job.areaM2()) != 0
        || !req.path("modelSha256").asString().equals(manifest.path("model-source.json").asString())
        || !req.path("forcingSha256").asString().equals(manifest.path("forcing.json").asString())
        || !req.path("weeklyCodeSha256").asString().equals(manifest.path("weekly.py").asString()))
      throw invalid();
    return archive;
  }

  private byte[] file(Archive a, String name) throws IOException {
    if (!name.matches("[a-z0-9][a-z0-9_.-]{0,80}")
        || name.contains("..")
        || name.equals("manifest.json")) throw invalid();
    var bytes = read(a.directory().resolve(name), 64 * 1024 * 1024);
    String actual = hash(bytes);
    if (!actual.equals(a.manifest().path(name).asString())
        || (name.matches("[a-f0-9]{64}\\.txt") && !actual.equals(name.substring(0, 64))))
      throw invalid();
    return bytes;
  }

  public Map<String, Object> detail(SharedResearchJob job) {
    try {
      var archive = archive(job);
      var model = tree(file(archive, "model-source.json"));
      var forcing = tree(file(archive, "forcing.json"));
      var result = tree(file(archive, "result.json"));
      if (!java.time.Instant.parse(forcing.path("start").asString()).equals(job.simulationStart())
          || !java.time.Instant.parse(forcing.path("end").asString())
              .equals(job.simulatedThrough())) throw invalid();
      var contribution = result.path("contribution");
      var baseline = result.path("baseline").path("samples");
      var design = result.path("strategy").path("samples");
      if (!contribution.isArray()
          || contribution.size() != baseline.size()
          || design.size() != baseline.size()
          || design.isEmpty()) throw invalid();
      var frames = new ArrayList<Map<String, Object>>();
      int stride = Math.max(1, (int) Math.ceil(design.size() / 359.0));
      for (int i = 0; i < design.size(); i++)
        if (i % stride == 0 || i == design.size() - 1)
          frames.add(
              Map.of(
                  "baseline",
                  baseline.get(i),
                  "strategy",
                  design.get(i),
                  "contribution",
                  contribution.get(i)));
      var value = new LinkedHashMap<String, Object>();
      value.put("request", tree(file(archive, "request.json")));
      var modelView = new LinkedHashMap<String, Object>();
      for (String key :
          List.of(
              "cells",
              "hydrology",
              "physicsEvidence",
              "unitCosts",
              "costModel",
              "budget",
              "budgetPolicy",
              "assumptions",
              "sharedSiteSource")) modelView.put(key, model.path(key));
      value.put("model", modelView);
      value.put("summary", json.tree(job.result()));
      value.put("initialization", result.get("initialization"));
      value.put("facilityDesign", result.get("facilityDesign"));
      value.put("runoffComparison", result.get("runoffComparison"));
      value.put("sourceArchive", forcing.path("sourceArchive"));
      value.put("baselineFinal", result.path("baseline").path("final"));
      value.put("strategyFinal", result.path("strategy").path("final"));
      value.put(
          "evaporation",
          Map.of(
              "method",
              forcing.path("evaporation").path("method"),
              "assumptions",
              forcing.path("evaporation").path("assumptions"),
              "sourceHashes",
              forcing.path("evaporation").path("sourceHashes")));
      value.put("frames", frames);
      value.put("sampleCount", design.size());
      value.put("frameStride", stride);
      value.put("manifestSha256", job.manifestHash());
      return value;
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw invalid();
    }
  }

  public byte[] bundle(
      SharedResearchJob job, Map<String, Object> scope, BudgetRecordEvidence ledger) {
    try {
      var a = archive(job);
      var output = new ByteArrayOutputStream();
      long total = 0;
      var exportHashes = new TreeMap<String, String>();
      exportHashes.put("manifest.json", hash(a.manifestBytes()));
      try (var zip = new ZipOutputStream(output)) {
        zip.putNextEntry(new ZipEntry("manifest.json"));
        zip.write(a.manifestBytes());
        zip.closeEntry();
        for (String name : a.manifest().propertyNames()) {
          if (Set.of("access-scope.json", "budget-ledger.json", "export-manifest.json")
              .contains(name)) throw invalid();
          var bytes = file(a, name);
          total += bytes.length;
          if (total > 512L * 1024 * 1024) throw invalid();
          zip.putNextEntry(new ZipEntry(name));
          zip.write(bytes);
          zip.closeEntry();
          exportHashes.put(name, hash(bytes));
          if (output.size() > 64 * 1024 * 1024) throw invalid();
        }
        zip.putNextEntry(new ZipEntry("access-scope.json"));
        var scopeBytes = json.write(scope).getBytes(StandardCharsets.UTF_8);
        zip.write(scopeBytes);
        zip.closeEntry();
        exportHashes.put("access-scope.json", hash(scopeBytes));
        zip.putNextEntry(new ZipEntry("budget-ledger.json"));
        var ledgerBytes = json.write(ledger).getBytes(StandardCharsets.UTF_8);
        zip.write(ledgerBytes);
        zip.closeEntry();
        exportHashes.put("budget-ledger.json", hash(ledgerBytes));
        zip.putNextEntry(new ZipEntry("export-manifest.json"));
        zip.write(
            json.write(
                    Map.of(
                        "schemaVersion",
                        1,
                        "calculationManifestSha256",
                        job.manifestHash(),
                        "files",
                        exportHashes))
                .getBytes(StandardCharsets.UTF_8));
        zip.closeEntry();
      }
      if (output.size() > 64 * 1024 * 1024) throw invalid();
      return output.toByteArray();
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw invalid();
    }
  }
}
