package io.waterleague.common.repository;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.sql.*;
import java.time.*;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

@Repository
public class ExternalRequestStore {
  private static final ZoneId KST = ZoneId.of("Asia/Seoul");
  private final Path root;
  private final Clock clock;

  public record Policy(String account, long calls, long bytes) {}

  public record Response(String body, Instant fetchedAt) {}

  public static final class Unavailable extends RuntimeException {}

  @org.springframework.beans.factory.annotation.Autowired
  public ExternalRequestStore(
      @Value("${waterleague.external-request-state-dir:../data/private/external-requests}")
          String root) {
    this(Path.of(root), Clock.systemUTC());
  }

  public ExternalRequestStore(Path root, Clock clock) {
    this.root = root;
    this.clock = clock;
  }

  public static Policy policy(String provider, String key, long calls, long bytes) {
    return new Policy(hash((provider + "\n" + key).getBytes(StandardCharsets.UTF_8)), calls, bytes);
  }

  private static String hash(byte[] raw) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
    } catch (Exception e) {
      throw new Unavailable();
    }
  }

  private Connection database() throws Exception {
    Files.createDirectories(
        root, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
    Path path = root.resolve("requests.sqlite3");
    if (Files.isSymbolicLink(root) || Files.isSymbolicLink(path)) throw new Unavailable();
    try {
      Files.createFile(
          path, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
    } catch (FileAlreadyExistsException ignored) {
    }
    var db = DriverManager.getConnection("jdbc:sqlite:" + path.toAbsolutePath());
    try {
      execute(db, "PRAGMA busy_timeout=10000");
      execute(
          db,
          "CREATE TABLE IF NOT EXISTS budget(account TEXT,day TEXT,calls INTEGER NOT NULL,bytes"
              + " INTEGER NOT NULL,blocked_until REAL NOT NULL,PRIMARY KEY(account,day))");
      execute(
          db,
          "CREATE TABLE IF NOT EXISTS responses(account TEXT,id TEXT,raw BLOB,sha TEXT,fetched"
              + " REAL,expires REAL,lease TEXT,lease_until REAL,PRIMARY KEY(account,id))");
      return db;
    } catch (Exception e) {
      db.close();
      throw e;
    }
  }

  private static void execute(Connection db, String sql, Object... args) throws SQLException {
    try (var s = db.prepareStatement(sql)) {
      for (int i = 0; i < args.length; i++) s.setObject(i + 1, args[i]);
      s.execute();
    }
  }

  private static Object[] row(Connection db, String sql, Object... args) throws SQLException {
    try (var s = db.prepareStatement(sql)) {
      for (int i = 0; i < args.length; i++) s.setObject(i + 1, args[i]);
      try (var r = s.executeQuery()) {
        if (!r.next()) return null;
        Object[] result = new Object[r.getMetaData().getColumnCount()];
        for (int i = 0; i < result.length; i++) result[i] = r.getObject(i + 1);
        return result;
      }
    }
  }

  private static double number(Object value) {
    return value == null ? 0 : ((Number) value).doubleValue();
  }

  private String day() {
    return clock.instant().atZone(KST).toLocalDate().toString();
  }

  private double now() {
    return clock.instant().toEpochMilli() / 1000.0;
  }

  public String reserve(Policy policy, int maximum) {
    String day = day();
    try (var db = database()) {
      execute(db, "BEGIN IMMEDIATE");
      execute(db, "INSERT OR IGNORE INTO budget VALUES(?,?,0,0,0)", policy.account, day);
      var r =
          row(db, "SELECT calls,bytes FROM budget WHERE account=? AND day=?", policy.account, day);
      if (number(r[0]) >= policy.calls
          || number(r[1]) + maximum > policy.bytes
          || number(
                  row(
                      db,
                      "SELECT COALESCE(MAX(blocked_until),0) FROM budget WHERE account=?",
                      policy.account)[0])
              > now()) throw new Unavailable();
      execute(
          db,
          "UPDATE budget SET calls=calls+1,bytes=bytes+? WHERE account=? AND day=?",
          maximum,
          policy.account,
          day);
      execute(db, "COMMIT");
      return day;
    } catch (Exception e) {
      throw new Unavailable();
    }
  }

  private void settle(Policy policy, String day, int maximum, int actual) {
    try (var db = database()) {
      execute(
          db,
          "UPDATE budget SET bytes=bytes-? WHERE account=? AND day=?",
          Math.max(0, maximum - actual),
          policy.account,
          day);
    } catch (Exception e) {
      throw new Unavailable();
    }
  }

  public void block(Policy policy, int status, long retrySeconds) {
    Instant midnight =
        clock.instant().atZone(KST).toLocalDate().plusDays(1).atStartOfDay(KST).toInstant();
    double until =
        status == 401 || status == 403
            ? midnight.getEpochSecond()
            : now() + Math.max(60, retrySeconds);
    try (var db = database()) {
      execute(db, "INSERT OR IGNORE INTO budget VALUES(?,?,0,0,0)", policy.account, day());
      execute(
          db,
          "UPDATE budget SET blocked_until=MAX(blocked_until,?) WHERE account=? AND day=?",
          until,
          policy.account,
          day());
    } catch (Exception e) {
      throw new Unavailable();
    }
  }

  public Response acquire(
      Policy policy, String request, Duration ttl, int maximum, Supplier<String> loader) {
    String id = hash(request.getBytes(StandardCharsets.UTF_8)),
        token = UUID.randomUUID().toString();
    long deadline = System.nanoTime() + Duration.ofSeconds(35).toNanos();
    try {
      while (true) {
        try (var db = database()) {
          execute(db, "BEGIN IMMEDIATE");
          var r =
              row(
                  db,
                  "SELECT raw,sha,fetched,expires,lease_until FROM responses WHERE account=? AND"
                      + " id=?",
                  policy.account,
                  id);
          if (r != null && r[0] != null && number(r[3]) > now()) {
            byte[] raw = (byte[]) r[0];
            if (!hash(raw).equals(r[1])) throw new Unavailable();
            execute(db, "COMMIT");
            return new Response(
                new String(raw, StandardCharsets.UTF_8),
                Instant.ofEpochMilli((long) (number(r[2]) * 1000)));
          }
          if (r == null || number(r[4]) <= now()) {
            execute(
                db,
                "INSERT INTO responses(account,id,lease,lease_until) VALUES(?,?,?,?) ON"
                    + " CONFLICT(account,id) DO UPDATE SET"
                    + " lease=excluded.lease,lease_until=excluded.lease_until",
                policy.account,
                id,
                token,
                now() + 35);
            execute(db, "COMMIT");
            break;
          }
          execute(db, "COMMIT");
        }
        if (System.nanoTime() >= deadline) throw new Unavailable();
        Thread.sleep(100);
      }
      String day = reserve(policy, maximum);
      String body;
      try {
        body = loader.get();
      } catch (RuntimeException e) {
        block(policy, 0, 60);
        throw e;
      }
      byte[] raw = body.getBytes(StandardCharsets.UTF_8);
      if (raw.length > maximum) {
        block(policy, 0, 60);
        throw new Unavailable();
      }
      settle(policy, day, maximum, raw.length);
      Instant fetched = clock.instant().truncatedTo(java.time.temporal.ChronoUnit.MILLIS);
      double fetchedSeconds = fetched.toEpochMilli() / 1000.0;
      try (var db = database()) {
        execute(db, "BEGIN IMMEDIATE");
        execute(
            db,
            "DELETE FROM responses WHERE (expires<? OR expires IS NULL) AND (lease_until IS NULL OR"
                + " lease_until<?)",
            now(),
            now());
        long size =
            ((Number) row(db, "SELECT COALESCE(SUM(length(raw)),0) FROM responses")[0]).longValue();
        while (size + raw.length > 512_000_000) {
          var old =
              row(
                  db,
                  "SELECT account,id,length(raw) FROM responses WHERE raw IS NOT NULL AND"
                      + " (lease_until IS NULL OR lease_until<?) ORDER BY fetched LIMIT 1",
                  now());
          if (old == null) break;
          execute(db, "DELETE FROM responses WHERE account=? AND id=?", old[0], old[1]);
          size -= ((Number) old[2]).longValue();
        }
        execute(
            db,
            "UPDATE responses SET raw=?,sha=?,fetched=?,expires=?,lease=NULL,lease_until=NULL WHERE"
                + " account=? AND id=? AND lease=?",
            raw,
            hash(raw),
            fetchedSeconds,
            fetchedSeconds + ttl.toSeconds(),
            policy.account,
            id,
            token);
        execute(db, "COMMIT");
      }
      return new Response(body, fetched);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new Unavailable();
    } catch (Exception e) {
      throw new Unavailable();
    } finally {
      try (var db = database()) {
        execute(
            db,
            "UPDATE responses SET lease=NULL,lease_until=NULL WHERE account=? AND id=? AND lease=?",
            policy.account,
            id,
            token);
      } catch (Exception ignored) {
      }
    }
  }

  public static long retrySeconds(String value) {
    try {
      return Math.max(60, Long.parseLong(value));
    } catch (Exception e) {
      try {
        return Math.max(
            60,
            Duration.between(
                    Instant.now(),
                    ZonedDateTime.parse(
                            value, java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME)
                        .toInstant())
                .getSeconds());
      } catch (Exception ignored) {
        return 60;
      }
    }
  }
}
