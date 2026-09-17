# Coin Recomand

비트코인 시장 국면과 업비트 KRW 알트코인을 분석해 분할매수 후보를 선별하고, 1분 기술순위·매시간 종합순위·매일 이메일 보고서를 제공하는 프로그램입니다.

상단 메뉴에서 코인·미국주식·국내주식을 전환할 수 있습니다. 주식 페이지는 보유종목의 최근 주요뉴스와 사용자가 선택한 섹터만 수집합니다. 선택 섹터 종목은 한국투자증권 Open API의 일봉으로 EMA20·EMA50, RSI, MACD, 거래량, 모멘텀, 변동성과 대표지수 국면을 평가하고 종목 검색 및 상세 캔들차트를 제공합니다.

> 이 프로젝트의 결과는 정량 지표 기반 참고자료이며 수익을 보장하는 투자 자문이 아닙니다. 실제 주문은 실행하지 않습니다.

## 분석 항목

- 비트코인: Blockchain.com 공개 MVRV·시가총액 기반 MVRV Z-Score, EMA20/EMA50 추세, RSI, MACD, 거래량 비율, 7일·30일 수익률
- 시장 심리: Alternative.me Crypto Fear & Greed Index 현재값과 최근 30일 일별 꺾은선 추이
- 알트코인: RSI, MACD, EMA 추세, 7일·30일 모멘텀, 거래량 변화, 변동성, 유동성
- 추천·검색 결과: 현재가 옆에 전일 종가 대비 일간 등락률 표시
- 전체 분석 대상 검색: 종목명·심볼로 순위, 100점 환산 점수, 판정, 가감 근거, 커뮤니티·개발·언락 정보와 상세차트 조회
- 커뮤니티: CoinGecko 인기 검색 + Reddit·디시인사이드 비트코인 갤러리·코인판 한국시간 당일 게시글 언급 노출도
- 프로젝트: 공식 GitHub 최근 30일 커밋·릴리스로 개발 진척 확인
- 토크노믹스: 유통 비율과 향후 토큰 언락 일정·규모를 공급 위험으로 반영
- 결과: `분할매수 후보`, `관찰`, `보류`와 항목별 점수·선정 사유·위험 요인
- 주요 이슈: 최근 24시간 한국어 코인 뉴스의 출처·분류·관련 종목·영향 방향과 원문 링크
- 주요 시장 이벤트: CoinMarketCal·최근 뉴스·고정 일정에서 법안·FOMC·경제지표·ETF·대규모 언락을 선별해 중요도, 상태, D-day, 긍정·부정 시나리오와 공식 출처 표시
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

## 회원가입·로그인(Supabase 웹 설정)

별도 프로그램 설치 없이 [Supabase 웹 대시보드](https://supabase.com/dashboard)만으로 연결할 수 있습니다. 회원 비밀번호는 애플리케이션 데이터베이스에 저장하지 않고 Supabase Auth가 처리하며, `user_preferences`에는 회원별 보유주식·관심 섹터·코인/주식 보고서 주소만 저장합니다. RLS 정책으로 로그인한 사용자는 자신의 행만 조회·수정할 수 있습니다.

1. Supabase에서 새 프로젝트를 만들고 **SQL Editor → New query**를 엽니다.
2. [`supabase/migrations/20260915_user_preferences.sql`](supabase/migrations/20260915_user_preferences.sql)의 전체 내용을 붙여넣어 **Run** 합니다.
3. **Authentication → Providers → Email**에서 Email 로그인을 켜고 **Confirm email**을 켭니다.
4. **Authentication → URL Configuration**에서 Site URL을 `https://jijunkyoung.github.io/coin-recomand/`로 지정하고 같은 주소와 `https://jijunkyoung.github.io/coin-recomand/**`를 Redirect URLs에 추가합니다.
5. **Project Settings → API**에서 Project URL과 publishable key(구 프로젝트는 anon key)를 확인합니다.
6. GitHub **Settings → Secrets and variables → Actions**에 각각 `SUPABASE_URL`, `SUPABASE_ANON_KEY`라는 이름으로 저장합니다. service_role/secret key는 브라우저용 Secret에 넣지 않습니다.
7. Actions에서 워크플로를 한 번 실행하거나 변경사항 배포가 끝나면 우측 상단의 `회원가입`으로 확인합니다.

`SUPABASE_ANON_KEY`는 GitHub Pages 브라우저에 전달되는 공개용 키입니다. 테이블 보호는 키 은닉이 아니라 위 SQL의 RLS 정책이 담당합니다. `service_role` 키는 RLS를 우회하므로 정적 페이지나 저장소 파일에 절대 넣지 않습니다.

## GitHub Actions 설정

워크플로는 매시간 종합 분석·GitHub Pages 배포를 수행하고, 한국시간 오전 7시 30분 예약 또는 사용자가 직접 수동 실행했을 때만 코인 보고서와 맞춤 주식 보고서를 각 수신주소로 분리 발송합니다. 코드 변경에 따른 자동 배포에서는 이메일을 보내지 않습니다. 저장소의 **Settings → Pages → Source**를 `GitHub Actions`로 지정하세요.

이메일을 사용하려면 **Settings → Secrets and variables → Actions**에 아래 Repository secrets를 등록합니다.

| Secret | 설명 | Gmail 예시 |
|---|---|---|
| `SMTP_HOST` | SMTP 서버 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 포트 | `465` |
| `SMTP_USERNAME` | SMTP 로그인 계정 | 보내는 Gmail 주소 |
| `SMTP_PASSWORD` | SMTP 비밀번호 | Google 2단계 인증 후 만든 앱 비밀번호 |
| `EMAIL_FROM` | 발신 주소(선택) | 미설정 시 SMTP 계정 |
| `EMAIL_TO` | 코인 보고서 수신주소, 복수 주소 지원 | `coin@example.com` |
| `STOCK_EMAIL_TO` | 주식 보고서 수신주소, 복수 주소 지원 | `stock@example.com` |
| `KIS_APP_KEY` | 한국투자증권 Open API App Key | KIS Developers에서 발급 |
| `KIS_APP_SECRET` | 한국투자증권 Open API App Secret | KIS Developers에서 발급 |
| `STOCK_HOLDINGS_US` | 미국 보유종목 뉴스 대상 | `AAPL\|애플,NVDA\|엔비디아` |
| `STOCK_HOLDINGS_KR` | 국내 보유종목 뉴스 대상 | `005930\|삼성전자,000660\|SK하이닉스` |
| `STOCK_SECTORS` | 분석·뉴스를 수집할 섹터 ID | `defense,semiconductor,energy` |
| `SUPABASE_URL` | Supabase Project URL | `https://...supabase.co` |
| `SUPABASE_ANON_KEY` | 브라우저용 publishable/anon key | `sb_publishable_...` 또는 기존 JWT anon key |

### 미국·국내주식 최초 설정

1. 한국투자증권 계좌를 준비하고 [KIS Developers](https://apiportal.koreainvestment.com/)에서 Open API 서비스를 신청합니다.
2. 발급된 App Key와 App Secret을 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 각각 `KIS_APP_KEY`, `KIS_APP_SECRET`으로 등록합니다.
3. 미국주식 또는 국내주식 페이지의 `맞춤 수집 설정`에서 보유종목과 섹터 체크박스, 주식 메일주소를 입력합니다.
4. 화면에서 복사한 값을 `STOCK_HOLDINGS_US`, `STOCK_HOLDINGS_KR`, `STOCK_SECTORS`, `STOCK_EMAIL_TO` Secret에 각각 저장합니다.
5. 저장소 **Actions → Analyze, email and deploy → Run workflow**를 한 번 실행합니다.
6. 배포가 끝나면 상단 `미국주식`, `국내주식` 메뉴에서 결과를 확인합니다.

키는 GitHub Actions 서버에서 시세 조회에만 사용되고 정적 페이지나 분석 JSON에는 포함되지 않습니다. 이 프로젝트는 주문 API를 호출하지 않습니다. 키가 없을 때 주식 페이지는 임의 가격을 표시하지 않고 설정 절차를 안내합니다.

### 로그인 계정의 한국투자증권 보유현황 자동 동기화

로그인한 소유자 계정은 주식 페이지 진입 시 Supabase Edge Function을 통해 한국투자증권 잔고를 자동 조회합니다. 최근 조회 결과는 같은 브라우저 탭에서 5분간 재사용하며 `내 설정 → 지금 동기화`로 즉시 갱신할 수 있습니다. 계좌번호와 API Secret은 브라우저·정적 JSON·데이터베이스에 저장하지 않고 Edge Function Secret에서만 읽습니다. 조회된 종목코드와 종목명만 `user_preferences`의 보유종목 목록에 반영하며 주문 API는 호출하지 않습니다.

1. Supabase **Authentication → Users**에서 자동 동기화를 허용할 내 회원의 UUID를 복사합니다.
2. Supabase **Edge Functions → Secrets**에 아래 값을 등록합니다.
   - `KIS_APP_KEY`: 한국투자증권 App Key
   - `KIS_APP_SECRET`: 한국투자증권 App Secret
   - `KIS_ACCOUNT_NO`: 계좌번호 앞 8자리(하이픈 제외)
   - `KIS_ACCOUNT_PRODUCT_CODE`: 계좌번호 뒤 2자리(일반적으로 `01`)
   - `KIS_OWNER_USER_ID`: 1단계에서 복사한 Supabase 회원 UUID
3. Supabase **Edge Functions → Deploy a new function → Via Editor**에서 함수명을 `kis-portfolio`로 만들고 [`supabase/functions/kis-portfolio/index.ts`](supabase/functions/kis-portfolio/index.ts)의 내용을 붙여넣어 배포합니다.
4. 함수의 JWT 검증은 기본값인 **활성화 상태**로 유지합니다. 함수 내부에서도 전달된 JWT를 다시 검증한 뒤 `KIS_OWNER_USER_ID`와 정확히 일치하는 회원만 허용합니다. 저장소의 [`supabase/config.toml`](supabase/config.toml)에도 같은 설정이 포함돼 있습니다.
5. 대시보드에서 로그아웃 후 다시 로그인하고 미국주식 또는 국내주식 페이지를 열어 `내 보유현황` 카드와 동기화 시각을 확인합니다.

GitHub Actions에 등록한 `KIS_APP_KEY`, `KIS_APP_SECRET`은 Supabase로 자동 복사되지 않으므로 2단계에 별도로 한 번 등록해야 합니다. 실전투자용 TR ID를 사용하므로 모의투자 App Key와 계좌는 지원하지 않습니다.

### 내 KIS 계좌 변동·개인 주식메일 연결

예약메일은 소유자 한 명의 실시간 KIS 잔고를 조회하고 약 24시간 전 스냅샷과 비교해 신규 매수·전량 매도·수량 증감을 표시합니다. 주식 메일 수신주소는 해당 회원의 `내 설정 → 주식 보고서 수신목록`을 우선 사용하며, 다른 회원의 계좌나 메일 설정은 조회하지 않습니다.

1. Supabase **SQL Editor**에서 [`supabase/migrations/20260917_kis_portfolio_snapshots.sql`](supabase/migrations/20260917_kis_portfolio_snapshots.sql)을 실행합니다.
2. 기존 `kis-portfolio` Edge Function 코드를 최신 [`supabase/functions/kis-portfolio/index.ts`](supabase/functions/kis-portfolio/index.ts)로 교체해 다시 배포합니다. JWT 검증은 계속 활성화합니다.
3. 충분히 긴 임의 문자열을 하나 만들어 `KIS_SCHEDULER_KEY`라는 이름으로 Supabase **Edge Functions → Secrets**와 GitHub **Actions secrets** 양쪽에 같은 값으로 등록합니다.
4. Supabase **Project Settings → API Keys**에서 `service_role` 또는 secret key를 확인해 GitHub Actions secret `SUPABASE_SERVICE_ROLE_KEY`로만 등록합니다. 이 키는 브라우저용 `SUPABASE_ANON_KEY`와 다르며 공개 페이지에 입력하지 않습니다.
5. 내 계정으로 로그인해 `내 설정 → 주식 보고서 수신목록`을 확인하고 저장합니다. 비어 있으면 가입 이메일을 사용합니다.
6. 다음 예약메일 또는 Actions 수동 메일 발송에서 실시간 보유현황과 변동내역이 포함되는지 확인합니다. 첫 실행은 비교 기준을 만드는 날이므로 두 번째 날부터 24시간 변동이 표시됩니다.

GitHub Actions는 service role key와 별도의 scheduler key가 모두 있어야 예약용 조회를 호출합니다. Edge Function은 고정된 `KIS_OWNER_USER_ID` 한 명만 처리하며 주문 API는 호출하지 않습니다.

Reddit 언급 수는 선택 기능입니다. 사용하려면 Reddit의 script 앱을 만든 뒤 `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`을 추가하세요. 세 커뮤니티 모두 한국시간 당일 작성된 게시물만 반영합니다. 디시인사이드 비트코인 갤러리와 코인판은 별도 키 없이 게시글 제목을 표본 수집하며, 사이트 접근이 제한되면 0회로 간주하지 않고 `미수집`으로 표시합니다.

예정된 토큰 언락 날짜와 수량을 반영하려면 Mobula에서 API 키를 발급한 뒤 `MOBULA_API_KEY`를 Repository secret으로 추가하세요. 키가 없을 때도 CoinGecko의 총공급량 대비 유통 비율은 희석 위험에 반영되지만 정확한 언락 날짜는 `미수집`으로 표시됩니다. 공식 GitHub 개발 활동은 Actions의 기본 토큰을 사용하므로 별도 Secret이 필요하지 않습니다.

CoinGecko 키리스 API의 제한이 걸리는 환경에서는 무료 Demo 키를 발급해 `COINGECKO_API_KEY`로 등록할 수 있습니다.

CoinMarketCal 예정 이벤트를 사용하려면 GitHub Secret에 `COINMARKETCAL_API_KEY`를 등록합니다. 무료 플랜의 향후 7일·상위 100개 코인 범위에서 BTC·ETH와 추천 코인 관련 일정만 이메일에 표시합니다. DefiLlama의 DeFi TVL·스테이블코인 공급 지표는 무료 공개 API를 사용하므로 별도 키가 필요하지 않습니다. 두 자료는 중복가산을 막기 위해 현재 추천 점수에는 넣지 않고 이메일의 보조자료로 제공합니다.

### 주요 시장 이벤트 관리

대시보드는 CoinMarketCal 일정과 최근 뉴스 제목에서 고영향 일정 후보를 자동 선별하고, 법안 표결처럼 반드시 놓치면 안 되는 일정은 [`config/major_events.json`](config/major_events.json)에 고정 등록합니다. 고정 일정은 `date`, `time_kst`, `importance`, `status`, `verification`, `related_symbols`, `bull_case`, `bear_case`, `source_url`을 수정해 관리할 수 있습니다. 상태는 `예정`, `확정`, `확인 필요`, `연기`, `완료`, `취소` 중 하나를 사용합니다.

대시보드의 `전체`, `7일 이내`, `확인 필요` 버튼으로 일정을 걸러볼 수 있으며, 오전 7시 30분 메일에도 중요 이벤트 최대 5건을 먼저 강조합니다. 뉴스에서 발견한 일정은 공식 단계·시각이 불명확할 수 있어 기본적으로 `확인 필요`로 표시합니다. 일정이 있다는 사실만으로 코인 점수를 올리지 않으며, 공식 결과가 확인되기 전까지 변동성·위험 관리 정보로만 사용합니다.

예약 워크플로는 매시간 종합자료를 새로 생성하되, 매일 오전 7시 30분(KST) 실행에서만 코인 보고서는 `EMAIL_TO`, 주식 보고서는 `STOCK_EMAIL_TO`에 등록된 주소로 각각 발송합니다. 주식 메일에는 보유종목·선택 섹터의 최근 24시간 뉴스와 선택 섹터의 기술분석만 포함됩니다. GitHub Actions 대기 및 분석 시간 때문에 실제 수신은 예약 시각보다 몇 분 늦을 수 있습니다. 정적 페이지에서는 Secret을 직접 수정할 수 없으므로 화면에서 만든 값을 복사한 뒤 GitHub에서 저장해야 합니다.

대시보드 입력란과 `브라우저 목록만 저장`은 주소 작성·복사를 돕는 로컬 기능이며 실제 발송 설정을 직접 변경하지 않습니다. 실제 주소는 `EMAIL_TO 값 복사` 후 `실제 발송주소 변경`에서 기존 `EMAIL_TO`의 **Update secret → Save changes** 순서로 수정해야 합니다. `테스트 발송 화면 열기`는 인증정보를 공개 페이지에 노출하지 않고 GitHub Actions 실행 화면만 엽니다. 버튼을 누르는 것만으로는 발송되지 않으며, `Run workflow`에서 `메일 발송`을 체크하고 초록색 `Run workflow`를 눌러야 현재 GitHub Secret에 등록된 주소로 최신 보고서가 한 번 발송됩니다.

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
