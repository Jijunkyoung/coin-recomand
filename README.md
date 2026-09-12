# Coin Recomand

비트코인 시장 국면과 업비트 KRW 알트코인을 분석해 분할매수 후보를 선별하고, 1분 기술순위·매시간 종합순위·매일 이메일 보고서를 제공하는 프로그램입니다.

상단 메뉴에서 코인·미국주식·국내주식을 전환할 수 있습니다. 주식 페이지는 한국투자증권 Open API의 일봉으로 EMA20·EMA50, RSI, MACD, 거래량, 모멘텀, 변동성과 대표지수 국면을 평가하고 종목 검색 및 상세 캔들차트를 제공합니다.

> 이 프로젝트의 결과는 정량 지표 기반 참고자료이며 수익을 보장하는 투자 자문이 아닙니다. 실제 주문은 실행하지 않습니다.

## 분석 항목

- 비트코인: Blockchain.com 공개 MVRV·시가총액 기반 MVRV Z-Score, EMA20/EMA50 추세, RSI, MACD, 거래량 비율, 7일·30일 수익률
- 시장 심리: Alternative.me Crypto Fear & Greed Index 현재값과 최근 30일 일별 꺾은선 추이
- 알트코인: RSI, MACD, EMA 추세, 7일·30일 모멘텀, 거래량 변화, 변동성, 유동성
- 전체 분석 대상 검색: 종목명·심볼로 순위, 100점 환산 점수, 판정, 가감 근거, 커뮤니티·개발·언락 정보와 상세차트 조회
- 커뮤니티: CoinGecko 인기 검색 + Reddit·디시인사이드 비트코인 갤러리·코인판 한국시간 당일 게시글 언급 노출도
- 프로젝트: 공식 GitHub 최근 30일 커밋·릴리스로 개발 진척 확인
- 토크노믹스: 유통 비율과 향후 토큰 언락 일정·규모를 공급 위험으로 반영
- 결과: `분할매수 후보`, `관찰`, `보류`와 항목별 점수·선정 사유·위험 요인
- 주요 이슈: 최근 24시간 한국어 코인 뉴스의 출처·분류·관련 종목·영향 방향과 원문 링크
- 예정 이벤트: CoinMarketCal에서 향후 7일 BTC·ETH·추천 코인의 업그레이드·출시·규제 일정 수집
- 시장 유동성: DefiLlama DeFi TVL·스테이블코인 공급의 7일 변화
- 상세차트: 비트코인·추천 코인·검색 코인을 클릭해 7일·30일·90일·전체 캔들, 볼린저밴드, EMA20·EMA50, 거래대금, MACD(12·26·9), RSI(14) 확인
- 실시간 갱신: 업비트 WebSocket 가격을 받아 일봉 기반 EMA·RSI·MACD·수익률과 기술순위를 1분마다 브라우저에서 재계산

## 로컬 실행

Python 3.11 이상이 필요합니다.

```bash
python -m pip install -r requirements.txt
python -m src.main --output docs/data/latest.json
python -m http.server 8000 --directory docs
```

브라우저에서 `http://localhost:8000`을 열면 됩니다.

## GitHub Actions 설정

워크플로는 매시간 종합 분석·GitHub Pages 배포를 수행하고, 한국시간 오전 7시 30분 예약 또는 사용자가 직접 수동 실행했을 때만 이메일을 발송합니다. 코드 변경에 따른 자동 배포에서는 이메일을 보내지 않습니다. 저장소의 **Settings → Pages → Source**를 `GitHub Actions`로 지정하세요.

이메일을 사용하려면 **Settings → Secrets and variables → Actions**에 아래 Repository secrets를 등록합니다.

| Secret | 설명 | Gmail 예시 |
|---|---|---|
| `SMTP_HOST` | SMTP 서버 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 포트 | `465` |
| `SMTP_USERNAME` | SMTP 로그인 계정 | 보내는 Gmail 주소 |
| `SMTP_PASSWORD` | SMTP 비밀번호 | Google 2단계 인증 후 만든 앱 비밀번호 |
| `EMAIL_FROM` | 발신 주소(선택) | 미설정 시 SMTP 계정 |
| `EMAIL_TO` | 수신 주소, 여러 개는 쉼표·세미콜론·줄바꿈 구분 | `me@example.com,team@example.com` |
| `KIS_APP_KEY` | 한국투자증권 Open API App Key | KIS Developers에서 발급 |
| `KIS_APP_SECRET` | 한국투자증권 Open API App Secret | KIS Developers에서 발급 |

### 미국·국내주식 최초 설정

1. 한국투자증권 계좌를 준비하고 [KIS Developers](https://apiportal.koreainvestment.com/)에서 Open API 서비스를 신청합니다.
2. 발급된 App Key와 App Secret을 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 각각 `KIS_APP_KEY`, `KIS_APP_SECRET`으로 등록합니다.
3. 저장소 **Actions → Analyze, email and deploy → Run workflow**를 한 번 실행합니다.
4. 배포가 끝나면 상단 `미국주식`, `국내주식` 메뉴에서 결과를 확인합니다.

키는 GitHub Actions 서버에서 시세 조회에만 사용되고 정적 페이지나 분석 JSON에는 포함되지 않습니다. 이 프로젝트는 주문 API를 호출하지 않습니다. 키가 없을 때 주식 페이지는 임의 가격을 표시하지 않고 설정 절차를 안내합니다.

Reddit 언급 수는 선택 기능입니다. 사용하려면 Reddit의 script 앱을 만든 뒤 `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`을 추가하세요. 세 커뮤니티 모두 한국시간 당일 작성된 게시물만 반영합니다. 디시인사이드 비트코인 갤러리와 코인판은 별도 키 없이 게시글 제목을 표본 수집하며, 사이트 접근이 제한되면 0회로 간주하지 않고 `미수집`으로 표시합니다.

예정된 토큰 언락 날짜와 수량을 반영하려면 Mobula에서 API 키를 발급한 뒤 `MOBULA_API_KEY`를 Repository secret으로 추가하세요. 키가 없을 때도 CoinGecko의 총공급량 대비 유통 비율은 희석 위험에 반영되지만 정확한 언락 날짜는 `미수집`으로 표시됩니다. 공식 GitHub 개발 활동은 Actions의 기본 토큰을 사용하므로 별도 Secret이 필요하지 않습니다.

CoinGecko 키리스 API의 제한이 걸리는 환경에서는 무료 Demo 키를 발급해 `COINGECKO_API_KEY`로 등록할 수 있습니다.

CoinMarketCal 예정 이벤트를 사용하려면 GitHub Secret에 `COINMARKETCAL_API_KEY`를 등록합니다. 무료 플랜의 향후 7일·상위 100개 코인 범위에서 BTC·ETH와 추천 코인 관련 일정만 이메일에 표시합니다. DefiLlama의 DeFi TVL·스테이블코인 공급 지표는 무료 공개 API를 사용하므로 별도 키가 필요하지 않습니다. 두 자료는 중복가산을 막기 위해 현재 추천 점수에는 넣지 않고 이메일의 보조자료로 제공합니다.

예약 워크플로는 매시간 종합자료를 새로 생성하되, 매일 오전 7시 30분(KST) 실행에서만 `EMAIL_TO`에 등록된 모든 주소로 보고서를 발송합니다. GitHub Actions 대기 및 분석 시간 때문에 실제 반영·수신은 보통 예약 시각보다 몇 분 늦을 수 있습니다. 대시보드의 `메일 수신 설정`에서 복수 주소를 검증·복사한 뒤 GitHub Actions Secret `EMAIL_TO`에 붙여넣을 수 있습니다. 정적 페이지에서는 Secret을 직접 수정할 수 없으므로 최초 등록이나 주소 변경 시 GitHub에서 저장하는 단계가 필요합니다.

주요 코인 이슈는 별도 키 없이 Google News 한국어 RSS의 최근 24시간 제목을 수집합니다. 추천 종목 심볼과 보안·규제·ETF·상장·개발·토크노믹스 핵심어를 기준으로 분류하며, 한 매체가 목록을 독점하지 않도록 매체별 최대 2건으로 제한합니다. 영향 방향은 제목 기반 참고 분류이므로 반드시 메일의 원문 링크에서 사실관계와 맥락을 확인하세요.

MVRV Z-Score는 별도 키 없이 Blockchain.com 공개 차트의 MVRV와 BTC 시가총액으로 계산합니다. `GLASSNODE_API_KEY`가 등록돼 있고 요금제 권한이 있으면 Glassnode 공식 값을 우선 사용하며, 키가 없거나 요청이 실패하면 무료 계산값으로 자동 전환합니다. 데이터 제공처별 산정·표본 방식 차이로 Glassnode 값과 소폭 다를 수 있습니다.

## 추천 점수 원칙

- 상승장: 점수 상위 종목을 `분할매수 후보`로 표시
- 중립장: 기준을 더 높여 강한 종목만 후보로 표시
- 하락장: 신규 매수 후보를 내지 않고 모두 `관찰` 또는 `보류`
- 급등·과매수·저유동성·고변동성은 감점
- EMA·RSI·MACD·수익률처럼 연관된 상승 신호는 합산 최대 22점으로 제한
- 알트 내부 원점수의 이론상 최고 77점을 최종 100점으로 환산하며 판정선도 같은 비율로 적용
- 공식 개발 커밋·최근 릴리스는 합산 최대 4점으로 제한하고, 장기 개발 정체는 감점
- 60일 이내 토큰 언락과 낮은 유통 비율은 규모에 따라 감점하며, 임박 언락의 수량 미확인도 보수적으로 감점
- 커뮤니티는 한국시간 당일 언급만 반영하고 최대 5점으로 제한
- 데이터 일부가 없으면 숨기지 않고 `data_quality.warnings`와 화면의 데이터 상태에 표시

설정값은 [`config/settings.json`](config/settings.json)에서 조정할 수 있습니다.

동일 티커가 여러 CoinGecko 자산에 쓰이는 경우 `coingecko_id_overrides`에 현재 자산 ID를 지정합니다. PROS는 폐기된 `prosper` 대신 현재 자산인 `prosper-2`로 고정되어 있습니다. 프로젝트가 공개 GitHub를 제공하지 않으면 개발량을 추정하지 않고 `공개 GitHub 없음`으로 표시합니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 데이터 출처

- [Upbit Open API](https://global-docs.upbit.com/reference/list-tickers)
- [Blockchain.com Charts API](https://www.blockchain.com/explorer/api/charts_api)
- [CoinGecko Keyless Public API](https://docs.coingecko.com/docs/keyless-public-api)
- [Alternative.me Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/)
- [GitHub REST API](https://docs.github.com/rest/commits/commits)
- [Mobula Token Unlocks](https://docs.mobula.io/guides/token-unlock)
- [Reddit r/CryptoCurrency](https://www.reddit.com/r/CryptoCurrency/)
- [디시인사이드 비트코인 갤러리](https://gall.dcinside.com/board/lists/?id=bitcoins_new1)
- [코인판 자유게시판](https://coinpan.com/free)
- [Google News 한국어 RSS](https://news.google.com/)
- [CoinMarketCal API](https://coinmarketcal.com/developer)
- [DefiLlama API](https://api-docs.defillama.com/)
coin recomand-01
