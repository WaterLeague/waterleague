package io.waterleague.rainfall.repository;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.common.repository.ExternalRequestStore.Response;
import io.waterleague.rainfall.exception.RainfallException;
import io.waterleague.rainfall.mapper.KmaObservationMapper;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.List;
import java.util.stream.Stream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

@Repository
public class KmaLiveRepository {
  private static final String ENDPOINT =
      "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min";
  private static final int MAXIMUM = 2 * 1024 * 1024;
  private final List<String> keys;
  private final ExternalRequestStore store;
  private final HttpClient client;

  @org.springframework.beans.factory.annotation.Autowired
  public KmaLiveRepository(
      @Value("${waterleague.kma-key:}") String key,
      @Value("${waterleague.kma-backup-key:}") String backup,
      ExternalRequestStore store) {
    this(
        key,
        backup,
        store,
        HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build());
  }

  KmaLiveRepository(String key, String backup, ExternalRequestStore store, HttpClient client) {
    this.keys =
        Stream.of(key, backup).map(String::strip).filter(v -> !v.isEmpty()).distinct().toList();
    this.store = store;
    this.client = client;
  }

  public Response fetch(Instant at) {
    return fetch(ENDPOINT, at, "");
  }

  public Response fetchPresentWeather(Instant at) {
    return fetch(ENDPOINT + "_ww1", at, "&itv=1&range=1");
  }

  private Response fetch(String endpoint, Instant at, String extra) {
    if (keys.isEmpty()) throw new RainfallException(ErrorCode.RAINFALL_ACCESS_UNAVAILABLE);
    String previous =
        KmaObservationMapper.TIME.format(at.minusSeconds(240).atZone(KmaObservationMapper.KST));
    String time = KmaObservationMapper.TIME.format(at.atZone(KmaObservationMapper.KST));
    String request =
        endpoint + "?tm1=" + previous + "&tm2=" + time + "&stn=0&disp=0&help=1" + extra;
    try {
      return store.acquireCached(
          policy(keys.getFirst()),
          request,
          Duration.ofSeconds(60),
          MAXIMUM,
          () -> fetchAvailable(request));
    } catch (ExternalRequestStore.Unavailable e) {
      throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
    }
  }

  private ExternalRequestStore.Policy policy(String key) {
    return ExternalRequestStore.policy("KMA", key, 20000, 5_000_000_000L);
  }

  private String fetchAvailable(String request) {
    for (String key : keys) {
      var policy = policy(key);
      try {
        var uri =
            URI.create(request + "&authKey=" + URLEncoder.encode(key, StandardCharsets.UTF_8));
        return store.request(policy, MAXIMUM, () -> request(uri, policy));
      } catch (ExternalRequestStore.Unavailable e) {
        // 소진·차단된 키는 HTTP 요청 없이 예비 키로 넘어간다.
      } catch (RainfallException e) {
        if (e.code() != ErrorCode.RAINFALL_ACCESS_UNAVAILABLE
            && e.code() != ErrorCode.RAINFALL_UNAVAILABLE) throw e;
      }
      if (Thread.currentThread().isInterrupted()) break;
    }
    throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
  }

  private String request(URI uri, ExternalRequestStore.Policy policy) {
    try {
      var response =
          client.send(
              HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(15)).GET().build(),
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8), MAXIMUM));
      if (response.statusCode() != 200)
        store.block(
            policy,
            response.statusCode(),
            ExternalRequestStore.retrySeconds(
                response.headers().firstValue("Retry-After").orElse("")));
      if (response.statusCode() == 401 || response.statusCode() == 403)
        throw new RainfallException(ErrorCode.RAINFALL_ACCESS_UNAVAILABLE);
      if (response.statusCode() == 408
          || response.statusCode() == 429
          || response.statusCode() >= 500)
        throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
      if (response.statusCode() != 200 || keys.stream().anyMatch(response.body()::contains))
        throw new RainfallException(ErrorCode.RAINFALL_DATA_INVALID);
      return response.body();
    } catch (RainfallException e) {
      throw e;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
    } catch (Exception e) {
      throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
    }
  }
}
