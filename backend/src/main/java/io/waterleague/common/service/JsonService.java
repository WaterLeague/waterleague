package io.waterleague.common.service;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
@Component
public class JsonService {
 private final ObjectMapper mapper;
 public JsonService(ObjectMapper mapper){this.mapper=mapper;}
 public String write(Object value){return mapper.writeValueAsString(value);}
 public <T> T read(String value,Class<T> type){return mapper.readValue(value,type);}
 public tools.jackson.databind.JsonNode tree(String value){return mapper.readTree(value);}
 public String hash(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
}
