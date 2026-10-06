# 토스 집 PC 동기화와 일별 엑셀 자동 저장

이미 설치한 경우 API 키나 GitHub Secret을 다시 입력하지 마세요.
압축을 모두 풀고 `enable-daily-excel.cmd`를 한 번 실행하세요. `enable-browser-sync.cmd`도 같은 업데이트를 적용합니다.
기존 키·계좌·오전 7시 10분 예약을 유지하면서 엑셀 자동 저장과 버튼 연결을 등록합니다.

동기화 성공 후 **문서\CoinRecomand\portfolio-excel** 폴더에 `portfolio-history-YYYY-MM-DD.xlsx`를 저장합니다.
다른 날짜의 파일은 보존하고, 같은 날 다시 갱신하면 그 날짜의 파일만 최신 기록으로 교체합니다. 열려 있는 엑셀 파일은 먼저 닫아 주세요.
파일에는 총 보유자산 추이, 최근 상위 10개 종목의 원화 환산금액 그래프, 일별 총액 표, 전체 종목별 기록 표가 있습니다.
최근 366일의 기록을 포함하며, 이전 주식 기록도 보존합니다. 통합 자산 기록은 기능 적용일부터 쌓입니다.
총액은 연결된 주식 보유종목과 업비트 원화·코인을 포함합니다. 주식계좌 예수금 및 다른 금융자산은 포함하지 않습니다.
미국주식은 Frankfurter의 날짜가 표시된 USD/KRW 환율로 환산합니다. 환율·계좌자료가 빠지면 총액은 n.a.로 표시하고 실패/이전 자료 사용을 안내합니다.
본인 계정으로 로그인한 주식·코인 페이지의 **자산기록 엑셀 다운로드**로도 같은 기록을 받을 수 있습니다.

주식 페이지에서 본인 계정으로 로그인 → **수량·가격 갱신** → 브라우저의 프로그램 실행 허용.
연결한 집 Windows PC에서 사용할 수 있습니다. 다른 PC·휴대폰에서는 집 PC 프로그램을 직접 실행한 뒤 화면을 다시 불러오세요.
브라우저는 계좌 동기화를 최대 90초 기다립니다. 엑셀 저장 결과는 PC 로그의 5단계에서 확인합니다.
예약 작업은 기존 IgnoreNew 설정으로 중복 실행을 막습니다. URI의 추가 인수는 실행하지 않습니다.

새 설치는 `install-toss-sync.cmd`, 직접 실행은 `sync-toss-now.cmd`를 사용하세요.

---

# 토스증권 집 PC 무료 동기화

토스증권 Open API는 허용 IP에서만 호출할 수 있고 Supabase Edge Function에는 고정 발신 IP가 없습니다. 이 도구는 허용 IP로 등록한 집 인터넷에서 보유종목을 읽고, 조회 결과만 Supabase에 업로드합니다.

- 주문·정정·취소 API는 호출하지 않습니다.
- Client ID와 Client Secret은 `%LOCALAPPDATA%\CoinRecomand`에 Windows 사용자 계정 전용 DPAPI 암호문으로 저장합니다.
- 대시보드에는 보유종목 조회 결과만 저장하며 토스 API 키는 전송하지 않습니다.
- 매일 오전 7시 10분에 실행합니다. PC가 꺼져 있으면 Windows가 다음 가능한 시점에 실행합니다.

## 설치

1. 이 폴더의 `install-toss-sync.cmd`를 더블클릭합니다.
2. 표시된 집 공인 IPv4를 토스증권 WTS의 **설정 → Open API → 허용 IP 관리**에 등록합니다.
3. 발급받은 Client ID와 Client Secret을 설치창에 입력합니다.
4. 설치창이 복사한 값을 GitHub Secret `TOSS_LOCAL_SYNC_KEY`로 저장합니다.
5. 설치창이 열어 준 GitHub Actions의 **Deploy Supabase backend**에서 **Run workflow**를 실행합니다.
6. 작업이 초록색으로 성공하면 설치창으로 돌아와 Enter를 누릅니다.
7. 첫 동기화 성공 메시지를 확인하고 대시보드에서 로그아웃·로그인한 뒤 **지금 동기화**를 누릅니다.

설치 후 즉시 다시 동기화하려면 `sync-toss-now.cmd`를 실행합니다. 로그는 `%LOCALAPPDATA%\CoinRecomand\toss-sync.log`에 남습니다.

## 집 인터넷 IP가 바뀐 경우

집 공인 IP가 변경됐다는 메시지가 표시되면 토스증권 허용 IP를 현재 IP로 변경하세요. API 키와 GitHub 동기화 키를 다시 발급할 필요는 없습니다.

## 삭제

Windows 작업 스케줄러에서 `CoinRecomand-TossSync` 작업을 삭제하고 `%LOCALAPPDATA%\CoinRecomand` 폴더를 지웁니다. GitHub Secret `TOSS_LOCAL_SYNC_KEY`도 삭제한 뒤 **Deploy Supabase backend**를 다시 실행하면 서버 직접조회 방식으로 돌아갑니다.
