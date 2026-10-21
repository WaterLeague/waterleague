import { useState, type ReactNode } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Compass,
  Database,
  Flag,
  Layers3,
  Trophy,
} from 'lucide-react';
import { followLink } from '../../../shared/controller/useAppLocation';
import { facilities } from '../../game/service/gameService';
import { facilityIcons } from '../../facility/view/facilityIcons';
import { homeFacilities, homeModes } from '../service/homeContent';
import { HomePreview } from './HomePreview';
import './home.css';

function HomeLink({
  href,
  children,
  className = '',
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a className={className} href={href} onClick={(event) => followLink(event, href)}>
      {children}
    </a>
  );
}

export function HomePage() {
  const [facilityIndex, setFacilityIndex] = useState(0);
  const selected = homeFacilities[facilityIndex];
  return (
    <main className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-copy">
          <span className="home-eyebrow">서울에서 시작하는 빗물 전략 게임</span>
          <h1 id="home-title">
            작은 설계로,
            <br />
            도시의 물길을
            <br />
            <em>바꿔볼까요?</em>
          </h1>
          <p>
            우리 동네에 빗물 시설을 놓고,
            <br />
            실제 관측된 비로 설계의 변화를 확인해요.
            <br />
            수달과 물총새가 첫걸음을 함께할게요.
          </p>
          <div className="home-actions">
            <HomeLink href="/weekly" className="home-button primary">
              게임 시작하기 <ArrowUpRight size={18} />
            </HomeLink>
            <a href="#home-modes" className="home-button secondary">
              먼저 둘러보기 <ArrowRight size={16} />
            </a>
          </div>
          <span className="home-hero-note">서울 25개 구 · 두 가지 게임 모드 · 7종의 시설</span>
        </div>
        <figure className="home-hero-art">
          <img
            src="/brand/seoul-hero.png"
            alt="한강과 남산을 배경으로 수달과 물총새가 함께하는 WATER LEAGUE"
            width="1650"
            height="953"
            fetchPriority="high"
          />
        </figure>
      </section>

      <section className="home-guides" aria-labelledby="home-guide-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">처음이라도 괜찮아요</span>
          <h2 id="home-guide-title">빗물의 여행을 함께 바꿔요.</h2>
          <p>어디에 놓을지, 무엇을 놓을지. 여러분의 선택에서 시작됩니다.</p>
        </div>
        <div className="home-guide-grid">
          <article className="home-guide otter">
            <img
              src="/brand/otter.png"
              width="300"
              height="299"
              loading="lazy"
              alt="물방울 지팡이를 든 수달 안내자"
            />
            <div>
              <span className="home-guide-name">수달의 첫 번째 안내</span>
              <h3>“빗물이 잠시 머물 곳을 만들어줘!”</h3>
              <p>
                지붕과 도로, 식재 공간을 찾아 시설을 놓아보세요. 예산 안에서 종류와 면적을 고르고,
                설치 전후 빗물의 변화를 비교하는 게임이에요.
              </p>
            </div>
          </article>
          <article className="home-guide kingfisher">
            <img
              src="/brand/kingfisher.png"
              width="1383"
              height="1137"
              loading="lazy"
              alt="바위 위의 파란 물총새 안내자"
            />
            <div>
              <span className="home-guide-name">물총새의 두 번째 안내</span>
              <h3>“같은 비에도 설계는 달라질 수 있어!”</h3>
              <p>
                지도를 살펴보고, 시간을 돌려 보고, 다른 기록과 비교해 보세요. 실제 공개 지도와 관측
                강우를 바탕으로 나만의 배치를 찾아갈 수 있어요.
              </p>
            </div>
          </article>
        </div>
      </section>

      <section className="home-modes" id="home-modes" aria-labelledby="home-modes-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">두 가지 플레이 방식</span>
          <h2 id="home-modes-title">오늘의 비, 그리고 그날의 비.</h2>
          <p>우리 구와 한 주를 함께하거나, 과거의 호우에 새로운 설계로 도전하세요.</p>
        </div>
        <div className="home-mode-grid">
          {homeModes.map((mode) => (
            <article className="home-mode" key={mode.id}>
              <HomePreview mode={mode.id} label={mode.title} />
              <div className="home-mode-copy">
                <span className="home-eyebrow">
                  {mode.number} / {mode.tag}
                </span>
                <h3>{mode.title}</h3>
                <p>{mode.intro}</p>
                <ul>
                  {mode.rules.map((rule) => (
                    <li key={rule}>
                      <Check size={15} />
                      {rule}
                    </li>
                  ))}
                </ul>
                <HomeLink href={mode.href} className="home-text-link">
                  {mode.link}
                  <ArrowUpRight size={18} />
                </HomeLink>
              </div>
            </article>
          ))}
        </div>
        <p className="home-caption">
          3D 장면은 게임 방식의 이해를 돕는 모형입니다. 실제 관측·계산 결과는 게임에서 확인할 수
          있어요.
        </p>
      </section>

      <section className="home-facilities" aria-labelledby="home-facilities-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">나만의 빗물 도구 상자</span>
          <h2 id="home-facilities-title">7가지 시설, 서로 다른 역할.</h2>
          <p>시설을 골라 3D로 돌려 보고, 어디에서 어떤 역할을 하는지 알아보세요.</p>
        </div>
        <div className="home-facility-picker" role="group" aria-label="소개할 시설 선택">
          {homeFacilities.map((item, index) => {
            const Icon = facilityIcons[item.type];
            return (
              <button
                type="button"
                key={item.type}
                aria-pressed={index === facilityIndex}
                aria-controls="home-facility-detail"
                onClick={() => setFacilityIndex(index)}
              >
                <Icon size={18} />
                {facilities[item.type].name}
              </button>
            );
          })}
        </div>
        <div className="home-facility-detail" id="home-facility-detail">
          <HomePreview facility={selected.type} label={facilities[selected.type].name} />
          <div className="home-facility-copy" aria-live="polite">
            <span className="home-eyebrow">
              FACILITY {String(facilityIndex + 1).padStart(2, '0')} / 07
            </span>
            <h3>{facilities[selected.type].name}</h3>
            <p>{selected.action}</p>
            <div className="home-placement">
              <Compass size={18} />
              <div>
                <span>어디에 설치하나요?</span>
                <strong>{selected.place}</strong>
              </div>
            </div>
            <p className="home-caption">
              지도에서 표시되는 허용 후보에 설치해요. 모형은 시설의 역할을 설명하며 실제 시공
              제원이나 가능 여부를 뜻하지 않아요.
            </p>
            <HomeLink href="/weekly" className="home-text-link">
              지도에서 배치해 보기 <ArrowUpRight size={18} />
            </HomeLink>
          </div>
        </div>
      </section>

      <section className="home-features" aria-labelledby="home-features-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">플레이를 더 넓게</span>
          <h2 id="home-features-title">살펴보고, 비교하고, 함께 도전해요.</h2>
        </div>
        <div className="home-feature-grid">
          {[
            {
              Icon: Layers3,
              title: '내가 사는 서울을 입체로',
              text: '2D·3D 지도, 현재 위치 이동, 공개 시설과 강우 정보를 함께 살펴봐요.',
              href: '/weekly',
              link: '서울 지도 열기',
            },
            {
              Icon: Trophy,
              title: '기록으로 만나는 다른 설계',
              text: '주간 우리 구 순위와 과거 재해의 제출 기록을 같은 조건끼리 비교해요.',
              href: '/rankings',
              link: '랭킹 보기',
            },
            {
              Icon: Flag,
              title: '함께 만드는 대회',
              text: '대회에 참가하고 정해진 조건에 도전하세요. 승인된 기업·기관은 직접 개최할 수 있어요.',
              href: '/competitions',
              link: '대회 둘러보기',
            },
            {
              Icon: Database,
              title: '게임의 근거까지 투명하게',
              text: '지도·강우·시설 비용은 어디에서 왔는지, 자료와 계산의 근거를 확인해요.',
              href: '/data',
              link: '데이터 살펴보기',
            },
          ].map(({ Icon, title, text, href, link }) => (
            <article key={href}>
              <Icon size={24} />
              <h3>{title}</h3>
              <p>{text}</p>
              <HomeLink href={href} className="home-text-link">
                {link}
                <ArrowUpRight size={16} />
              </HomeLink>
            </article>
          ))}
        </div>
      </section>

      <section className="home-start">
        <div>
          <span className="home-eyebrow">첫 번째 시설을 놓을 시간</span>
          <h2>
            우리 동네의 물길,
            <br />
            지금 함께 바꿔봐요.
          </h2>
          <p>재해 모드는 로그인 없이도 시설 배치를 체험할 수 있어요.</p>
        </div>
        <HomeLink href="/disaster" className="home-button primary">
          무료로 체험하기 <ArrowUpRight size={19} />
        </HomeLink>
      </section>
      <footer className="home-footer">
        <img src="/brand/wordmark.png" alt="WATER LEAGUE" width="160" height="64" />
        <p>
          서울 공개자료와 관측 강우로 즐기는 빗물 전략 게임.
          <br />
          게임의 효과는 탐색 계산이며 실제 현장 침수 예측이나 시공 승인을 대신하지 않습니다.
        </p>
        <HomeLink href="/data">
          자료와 계산 근거 <ArrowUpRight size={14} />
        </HomeLink>
      </footer>
    </main>
  );
}
