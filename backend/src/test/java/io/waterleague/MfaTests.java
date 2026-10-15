package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.service.InstitutionMfaService;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class MfaTests {
  static String otp(String base32) {
    int buffer = 0, bits = 0;
    var out = new ByteArrayOutputStream();
    for (char c : base32.toCharArray()) {
      buffer = (buffer << 5) | "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(c);
      bits += 5;
      if (bits >= 8) {
        bits -= 8;
        out.write((buffer >> bits) & 255);
      }
    }
    return InstitutionMfaService.code(out.toByteArray(), Instant.now().getEpochSecond() / 30);
  }

  @Test
  void matchesRfc6238Sha1TestVectors() {
    byte[] secret = "12345678901234567890".getBytes(StandardCharsets.US_ASCII);
    long[] times = {59, 1111111109L, 1111111111L, 1234567890L, 2000000000L, 20000000000L};
    String[] codes = {"287082", "081804", "050471", "005924", "279037", "353130"};
    for (int i = 0; i < times.length; i++)
      assertThat(InstitutionMfaService.code(secret, times[i] / 30)).isEqualTo(codes[i]);
  }
}
