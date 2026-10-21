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
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

@Repository
public class KmaLiveRepository {
  private static final String ENDPOINT =
      "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min";
  private final String key;
  private final ExternalRequestStore store;
  private final ExternalRequestStore.Policy policy;
  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(5))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public KmaLiveRepository(
      @Value("${waterleague.kma-key:}") String key, ExternalRequestStore store) {
    this.key = key;
    this.store = store;
    this.policy = ExternalRequestStore.policy("KMA", key, 10000, 3_000_000_000L);
  }

  public Response fetch(Instant at) {
    return fetch(ENDPOINT, at, "");
  }

  public Response fetchPresentWeather(Instant at) {
    return fetch(ENDPOINT + "_ww1", at, "&itv=1&range=1");
  }

  private Response fetch(String endpoint, Instant at, String extra) {
    if (key.isBlank()) throw new RainfallException(ErrorCode.RAINFALL_ACCESS_UNAVAILABLE);
    String previous =
        KmaObservationMapper.TIME.format(at.minusSeconds(240).atZone(KmaObservationMapper.KST));
    String time = KmaObservationMapper.TIME.format(at.atZone(KmaObservationMapper.KST));
    var uri =
        URI.create(
            endpoint
                + "?tm1="
                + previous
                + "&tm2="
                + time
                + "&stn=0&disp=0&help=1"
                + extra
                + "&authKey="
                + URLEncoder.encode(key, StandardCharsets.UTF_8));
    try {
      return store.acquire(
          policy,
          endpoint + "?tm1=" + previous + "&tm2=" + time + "&stn=0&disp=0&help=1" + extra,
          Duration.ofSeconds(60),
          2 * 1024 * 1024,
          () -> request(uri));
    } catch (ExternalRequestStore.Unavailable e) {
      throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
    }
  }

  private String request(URI uri) {
    try {
      var response =
          client.send(
              HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(15)).GET().build(),
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8), 2 * 1024 * 1024));
      if (response.statusCode() != 200)
        store.block(
            policy,
            response.statusCode(),
            ExternalRequestStore.retrySeconds(
                response.headers().firstValue("Retry-After").orElse("")));
      if (response.statusCode() == 401 || response.statusCode() == 403)
        throw new RainfallException(ErrorCode.RAINFALL_ACCESS_UNAVAILABLE);
      if (response.statusCode() != 200) throw new RainfallException(ErrorCode.RAINFALL_UNAVAILABLE);
      if (response.body().contains(key))
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
