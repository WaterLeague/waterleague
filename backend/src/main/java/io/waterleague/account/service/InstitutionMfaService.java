package io.waterleague.account.service;

import io.waterleague.account.repository.MfaRepository;
import io.waterleague.common.exception.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Instant;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class InstitutionMfaService {
  private final MfaRepository repo;
  private final String key;

  public InstitutionMfaService(MfaRepository r, @Value("${waterleague.mfa-key:}") String k) {
    repo = r;
    key = k;
  }

  public static String code(byte[] secret, long counter) {
    try {
      var mac = Mac.getInstance("HmacSHA1");
      mac.init(new SecretKeySpec(secret, "HmacSHA1"));
      byte[] h = mac.doFinal(ByteBuffer.allocate(8).putLong(counter).array());
      int offset = h[h.length - 1] & 15;
      int value = ByteBuffer.wrap(h, offset, 4).getInt() & 0x7fffffff;
      return String.format(Locale.ROOT, "%06d", value % 1000000);
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("OTP_ALGORITHM_UNAVAILABLE");
    }
  }

  public void verify(UUID account, String supplied) {
    if (supplied == null || !supplied.matches("[0-9]{6}")) denied();
    String encrypted =
        repo.encrypted(account)
            .orElseThrow(() -> new DomainException(ErrorCode.CREDENTIALS_INVALID));
    byte[] secret = decrypt(account, encrypted);
    long current = Instant.now().getEpochSecond() / 30, match = -1;
    try {
      for (long c = current - 1; c <= current + 1; c++)
        if (MessageDigest.isEqual(
            code(secret, c).getBytes(StandardCharsets.US_ASCII),
            supplied.getBytes(StandardCharsets.US_ASCII))) match = c;
    } finally {
      Arrays.fill(secret, (byte) 0);
    }
    if (match < 0 || !repo.consume(account, match)) denied();
  }

  public String provision(UUID account) {
    byte[] secret = new byte[20];
    new SecureRandom().nextBytes(secret);
    try {
      repo.provision(account, encrypt(account, secret));
      return base32(secret);
    } finally {
      Arrays.fill(secret, (byte) 0);
    }
  }

  private SecretKeySpec master() {
    try {
      byte[] bytes = Base64.getDecoder().decode(key);
      if (bytes.length != 32) throw new IllegalArgumentException();
      return new SecretKeySpec(bytes, "AES");
    } catch (IllegalArgumentException e) {
      throw new DomainException(ErrorCode.CREDENTIALS_INVALID);
    }
  }

  private String encrypt(UUID id, byte[] secret) {
    try {
      byte[] nonce = new byte[12];
      new SecureRandom().nextBytes(nonce);
      var c = Cipher.getInstance("AES/GCM/NoPadding");
      c.init(Cipher.ENCRYPT_MODE, master(), new GCMParameterSpec(128, nonce));
      c.updateAAD(id.toString().getBytes(StandardCharsets.US_ASCII));
      byte[] encrypted = c.doFinal(secret);
      return Base64.getEncoder()
          .encodeToString(
              ByteBuffer.allocate(nonce.length + encrypted.length)
                  .put(nonce)
                  .put(encrypted)
                  .array());
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("MFA_ENCRYPTION_FAILURE");
    }
  }

  private byte[] decrypt(UUID id, String value) {
    try {
      byte[] bytes = Base64.getDecoder().decode(value);
      var c = Cipher.getInstance("AES/GCM/NoPadding");
      c.init(
          Cipher.DECRYPT_MODE,
          master(),
          new GCMParameterSpec(128, Arrays.copyOfRange(bytes, 0, 12)));
      c.updateAAD(id.toString().getBytes(StandardCharsets.US_ASCII));
      return c.doFinal(Arrays.copyOfRange(bytes, 12, bytes.length));
    } catch (GeneralSecurityException | IllegalArgumentException e) {
      throw new DomainException(ErrorCode.CREDENTIALS_INVALID);
    }
  }

  private String base32(byte[] value) {
    String alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    StringBuilder out = new StringBuilder();
    int buffer = 0, bits = 0;
    for (byte b : value) {
      buffer = (buffer << 8) | (b & 255);
      bits += 8;
      while (bits >= 5) {
        bits -= 5;
        out.append(alphabet.charAt((buffer >> bits) & 31));
      }
    }
    return out.toString();
  }

  private void denied() {
    throw new DomainException(ErrorCode.CREDENTIALS_INVALID);
  }
}
