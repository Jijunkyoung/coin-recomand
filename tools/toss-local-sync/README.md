# 토스 집 PC 동기화와 브라우저 갱신 버튼

이미 설치한 경우 API 키나 GitHub Secret을 다시 입력하지 마세요.
압축을 모두 풀고 `enable-browser-sync.cmd`를 한 번 실행하세요.
기존 키·계좌·오전 7시 10분 예약을 유지하면서 버튼 연결을 등록합니다.

주식 페이지에서 본인 계정으로 로그인 → **수량·가격 갱신** → 브라우저의 프로그램 실행 허용.
연결한 집 Windows PC에서 사용할 수 있습니다. 다른 PC·휴대폰에서는 집 PC 프로그램을 직접 실행한 뒤 화면을 다시 불러오세요.
브라우저는 완료를 최대 90초 기다립니다. 실패 시 이전 자료를 보존하고 상태를 표시합니다.
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
