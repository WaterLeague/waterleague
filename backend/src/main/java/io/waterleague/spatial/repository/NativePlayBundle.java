package io.waterleague.spatial.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.Function;
import java.util.zip.GZIPInputStream;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

@Component
public class NativePlayBundle {
  public static final String MANIFEST_SHA256 =
      "9cf8102058e282034d1f5f56d74c666e11703a9a6c3b83e94aee5be0a11d21dc";
  private static final int CHUNK_BYTES = 32 * 1024 * 1024;
  private static final Object CACHE_LOCK = new Object();
  private final Path cache;
  private final Function<String, Resource> resources;
  private final JsonNode manifest;
  private volatile Path ready;

  @Autowired
  public NativePlayBundle(
      JsonService json,
      @Value("${waterleague.native-spatial-cache:${java.io.tmpdir}/waterleague-native-spatial}")
          String cache) {
    this(json, Path.of(cache), new ClassPathResource("native-play/v1/manifest.json"),
        MANIFEST_SHA256, name -> new ClassPathResource("native-play/v1/" + name));
  }

  public NativePlayBundle(JsonService json, Path cache, Resource source, String checksum,
      Function<String, Resource> resources) {
    this.cache = cache.toAbsolutePath().normalize();
    this.resources = resources;
    try {
      byte[] raw;
      try (var input = source.getInputStream()) {
        raw = input.readNBytes(128 * 1024 + 1);
      }
      if (raw.length > 128 * 1024 || !hash(raw).equals(checksum)) invalid();
      manifest = json.tree(new String(raw, java.nio.charset.StandardCharsets.UTF_8));
      validateManifest(manifest);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  public JsonNode manifest() {
    return manifest.deepCopy();
  }

  public Path database() {
    synchronized (CACHE_LOCK) { return restore(); }
  }

  private Path restore() {
    if (ready != null) return ready;
    Path temporary = null;
    try {
      Files.createDirectories(cache);
      var base = cache.toRealPath();
      var directory = base.resolve(manifest.path("databaseSha256").asString());
      if (Files.isSymbolicLink(directory)) invalid();
      if (!Files.exists(directory))
        Files.createDirectory(directory, PosixFilePermissions.asFileAttribute(
            PosixFilePermissions.fromString("rwx------")));
      var permissions = Files.getPosixFilePermissions(directory);
      if (!Collections.disjoint(permissions, PosixFilePermissions.fromString("---rwxrwx"))) invalid();
      Path path = directory.resolve("play.sqlite"), lock = directory.resolve(".lock");
      // Python lockf와 같은 POSIX 잠금으로 API와 워커의 동시 복원을 직렬화한다.
      try (var channel = FileChannel.open(lock,
          Set.of(StandardOpenOption.CREATE, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS),
          PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
          var ignored = channel.lock()) {
        // 중단된 이전 복원의 자체 임시 파일만 공통 잠금 안에서 정리한다.
        try (var pending = Files.newDirectoryStream(directory, "play-*.part")) {
          for (var file : pending) {
            if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) invalid();
            Files.delete(file);
          }
        }
        if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
          if (Files.isSymbolicLink(path) || !Files.isRegularFile(path)
              || Files.size(path) != manifest.path("databaseBytes").asLong()
              || !hash(path).equals(manifest.path("databaseSha256").asString())) invalid();
          ready = path;
          return path;
        }
        temporary = Files.createTempFile(directory, "play-", ".part",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        var digest = MessageDigest.getInstance("SHA-256");
        long written = 0;
        try (var target = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
          for (var chunk : manifest.path("chunks")) {
            int compressed = chunk.path("gzipBytes").asInt();
            byte[] payload;
            try (var input = resources.apply(chunk.path("file").asString()).getInputStream()) {
              payload = input.readNBytes(compressed + 1);
            }
            if (payload.length != compressed || !hash(payload).equals(chunk.path("gzipSha256").asString())) invalid();
            byte[] raw;
            try (var input = new GZIPInputStream(new ByteArrayInputStream(payload))) {
              raw = input.readNBytes(chunk.path("bytes").asInt() + 1);
            }
            if (raw.length != chunk.path("bytes").asInt() || !hash(raw).equals(chunk.path("sha256").asString())) invalid();
            digest.update(raw);
            var buffer = ByteBuffer.wrap(raw);
            while (buffer.hasRemaining()) target.write(buffer);
            written += raw.length;
          }
          if (written != manifest.path("databaseBytes").asLong()
              || !HexFormat.of().formatHex(digest.digest()).equals(manifest.path("databaseSha256").asString())) invalid();
          target.force(true);
        }
        Files.setPosixFilePermissions(temporary, PosixFilePermissions.fromString("r--------"));
        Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE);
        ready = path;
        return path;
      }
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    } finally {
      if (temporary != null) {
        try { Files.deleteIfExists(temporary); } catch (IOException ignored) { }
      }
    }
  }

  private static void validateManifest(JsonNode root) {
    if (root.path("schemaVersion").asInt() != 1
        || !root.path("id").asString().equals("SEOUL_NGII_REFERENCE_PLAY_V1")
        || !root.path("coordinateSystem").asString().equals("EPSG:5186")
        || !root.path("databaseSha256").asString().matches("[a-f0-9]{64}")
        || !root.path("databaseBytes").isIntegralNumber()
        || root.path("databaseBytes").asLong() < 4096 || root.path("databaseBytes").asLong() > 16L * 1024 * 1024 * 1024
        || root.path("chunkBytes").asInt() != CHUNK_BYTES
        || !root.path("chunks").isArray() || root.path("chunks").isEmpty() || root.path("chunks").size() > 512) invalid();
    long total = 0;
    int index = 0;
    for (var chunk : root.path("chunks")) {
      long size = chunk.path("bytes").asLong(), compressed = chunk.path("gzipBytes").asLong();
      if (!chunk.path("file").asString().equals("part-%03d.sqlite.gz".formatted(index))
          || !chunk.path("bytes").isIntegralNumber() || !chunk.path("gzipBytes").isIntegralNumber()
          || size < 1 || size > CHUNK_BYTES || compressed < 1 || compressed > 40 * 1024 * 1024
          || (index < root.path("chunks").size() - 1 && size != CHUNK_BYTES)
          || !chunk.path("sha256").asString().matches("[a-f0-9]{64}")
          || !chunk.path("gzipSha256").asString().matches("[a-f0-9]{64}")) invalid();
      total += size;
      index++;
    }
    if (total != root.path("databaseBytes").asLong()) invalid();
  }

  public static String hash(Path path) throws Exception {
    var digest = MessageDigest.getInstance("SHA-256");
    try (var input = Files.newInputStream(path)) {
      byte[] block = new byte[65536];
      for (int count; (count = input.read(block)) >= 0;) digest.update(block, 0, count);
    }
    return HexFormat.of().formatHex(digest.digest());
  }

  private static String hash(byte[] raw) throws Exception {
    return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
  }

  private static void invalid() { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
}
