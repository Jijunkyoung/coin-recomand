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

동기화 로그에 `집 공인 IP가 ...로 바뀌었습니다`가 표시되면 `install-toss-sync.cmd`를 다시 실행합니다. 새 IP를 토스증권에 등록하면 설정과 예약 작업이 갱신됩니다.

## 삭제

Windows 작업 스케줄러에서 `CoinRecomand-TossSync` 작업을 삭제하고 `%LOCALAPPDATA%\CoinRecomand` 폴더를 지웁니다. GitHub Secret `TOSS_LOCAL_SYNC_KEY`도 삭제한 뒤 **Deploy Supabase backend**를 다시 실행하면 서버 직접조회 방식으로 돌아갑니다.
