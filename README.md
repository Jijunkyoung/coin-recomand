# Coin Recomand

비트코인 시장 국면과 업비트 KRW 알트코인을 매일 분석해 분할매수 후보를 선별하고, 정적 대시보드와 이메일 보고서를 만드는 프로그램입니다.

> 이 프로젝트의 결과는 정량 지표 기반 참고자료이며 수익을 보장하는 투자 자문이 아닙니다. 실제 주문은 실행하지 않습니다.

## 분석 항목

- 비트코인: Coin Metrics 기반 MVRV Z-Score, EMA20/EMA50 추세, RSI, MACD, 거래량 비율, 7일·30일 수익률
- 시장 심리: Alternative.me Crypto Fear & Greed Index
- 알트코인: RSI, MACD, EMA 추세, 7일·30일 모멘텀, 거래량 변화, 변동성, 유동성
- 커뮤니티: CoinGecko 인기 검색 + Reddit·디시인사이드 비트코인 갤러리·코인판 한국시간 당일 게시글 언급 노출도
- 프로젝트: 공식 GitHub 최근 30일 커밋·릴리스로 개발 진척 확인
- 토크노믹스: 유통 비율과 향후 토큰 언락 일정·규모를 공급 위험으로 반영
- 결과: `분할매수 후보`, `관찰`, `보류`와 항목별 점수·선정 사유·위험 요인
- 상세차트: 비트코인 또는 추천 코인을 클릭해 7일·30일·90일·전체 가격, EMA20·EMA50, 거래대금 확인

## 로컬 실행

Python 3.11 이상이 필요합니다.

```bash
python -m pip install -r requirements.txt
python -m src.main --output docs/data/latest.json
python -m http.server 8000 --directory docs
```

브라우저에서 `http://localhost:8000`을 열면 됩니다.

## GitHub Actions 설정

워크플로는 매일 한국시간 오전 7시 15분과 수동 실행 시 분석·메일 발송·GitHub Pages 배포를 수행합니다. 저장소의 **Settings → Pages → Source**를 `GitHub Actions`로 지정하세요.

이메일을 사용하려면 **Settings → Secrets and variables → Actions**에 아래 Repository secrets를 등록합니다.

| Secret | 설명 | Gmail 예시 |
|---|---|---|
| `SMTP_HOST` | SMTP 서버 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 포트 | `465` |
| `SMTP_USERNAME` | SMTP 로그인 계정 | 보내는 Gmail 주소 |
| `SMTP_PASSWORD` | SMTP 비밀번호 | Google 2단계 인증 후 만든 앱 비밀번호 |
| `EMAIL_FROM` | 발신 주소(선택) | 미설정 시 SMTP 계정 |
| `EMAIL_TO` | 수신 주소, 여러 개는 쉼표 구분 | `me@example.com` |

Reddit 언급 수는 선택 기능입니다. 사용하려면 Reddit의 script 앱을 만든 뒤 `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`을 추가하세요. 세 커뮤니티 모두 한국시간 당일 작성된 게시물만 반영합니다. 디시인사이드 비트코인 갤러리와 코인판은 별도 키 없이 게시글 제목을 표본 수집하며, 사이트 접근이 제한되면 0회로 간주하지 않고 `미수집`으로 표시합니다.

예정된 토큰 언락 날짜와 수량을 반영하려면 Mobula에서 API 키를 발급한 뒤 `MOBULA_API_KEY`를 Repository secret으로 추가하세요. 키가 없을 때도 CoinGecko의 총공급량 대비 유통 비율은 희석 위험에 반영되지만 정확한 언락 날짜는 `미수집`으로 표시됩니다. 공식 GitHub 개발 활동은 Actions의 기본 토큰을 사용하므로 별도 Secret이 필요하지 않습니다.

CoinGecko 키리스 API의 제한이 걸리는 환경에서는 무료 Demo 키를 발급해 `COINGECKO_API_KEY`로 등록할 수 있습니다.

MVRV Z-Score의 완전한 자동 수집에는 Glassnode API 키가 필요합니다. `GLASSNODE_API_KEY`를 Secret으로 등록하면 공식 MVRV Z-Score 엔드포인트를 사용합니다. 키가 없을 때는 Coin Metrics Community 데이터로 직접 계산을 시도하며, 실현 시가총액이 무료 범위에서 제공되지 않으면 해당 지표를 `미수집`으로 명확히 표시합니다.

## 추천 점수 원칙

- 상승장: 점수 상위 종목을 `분할매수 후보`로 표시
- 중립장: 기준을 더 높여 강한 종목만 후보로 표시
- 하락장: 신규 매수 후보를 내지 않고 모두 `관찰` 또는 `보류`
- 급등·과매수·저유동성·고변동성은 감점
- EMA·RSI·MACD·수익률처럼 연관된 상승 신호는 합산 최대 22점으로 제한
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
- [Coin Metrics Community API](https://docs.coinmetrics.io/api/v4)
- [CoinGecko Keyless Public API](https://docs.coingecko.com/docs/keyless-public-api)
- [Alternative.me Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/)
- [GitHub REST API](https://docs.github.com/rest/commits/commits)
- [Mobula Token Unlocks](https://docs.mobula.io/guides/token-unlock)
- [Reddit r/CryptoCurrency](https://www.reddit.com/r/CryptoCurrency/)
- [디시인사이드 비트코인 갤러리](https://gall.dcinside.com/board/lists/?id=bitcoins_new1)
- [코인판 자유게시판](https://coinpan.com/free)
coin recomand-01
