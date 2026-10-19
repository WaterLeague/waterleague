package io.waterleague.spatial.service;

import io.waterleague.spatial.repository.NativePlayRepository;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnWebApplication
public class NativeGameWarmup implements SmartInitializingSingleton {
  private final NativePlayRepository repository;
  public NativeGameWarmup(NativePlayRepository repository) { this.repository = repository; }
  @Override
  public void afterSingletonsInstantiated() {
    // 웹 요청을 받기 전에 원형 자료를 검증하고 비웹 마이그레이션은 파일 복원을 생략한다.
    repository.metadata();
  }
}
