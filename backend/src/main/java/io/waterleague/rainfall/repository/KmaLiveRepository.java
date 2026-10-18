package io.waterleague.rainfall.repository;

import io.waterleague.common.exception.ErrorCode;
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
  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(5))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public KmaLiveRepository(@Value("${waterleague.kma-key:}") String key) {
    this.key = key;
  }

  public String fetch(Instant at) {
    return fetch(ENDPOINT, at, "");
  }

  public String fetchPresentWeather(Instant at) {
    return fetch(ENDPOINT + "_ww1", at, "&itv=1&range=1");
  }

  private String fetch(String endpoint, Instant at, String extra) {
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
      var response =
          client.send(
              HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(15)).GET().build(),
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8), 2 * 1024 * 1024));
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
