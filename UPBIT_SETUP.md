# 업비트 자동 잔고조회 연결 순서

업비트 인증 API는 호출지의 고정 공개 IP 등록이 필수입니다. Supabase Edge Function 자체는 고정 송신 IP가 없으므로, 고정 IPv4를 가진 소형 HTTPS 프록시를 한 번 준비해야 합니다.

1. 고정 IPv4 프록시 준비
   - AWS Lightsail/EC2, Oracle Cloud VM 등 고정 IPv4가 유지되는 서버를 사용합니다.
   - 프록시는 `/v1/accounts`와 `/v1/ticker` 요청만 `https://api.upbit.com`으로 전달하도록 제한합니다.
   - 임의 사용을 막기 위해 충분히 긴 `UPBIT_PROXY_TOKEN`을 설정합니다.
2. 업비트 PC 웹에서 API Key 발급
   - `마이페이지 → Open API 관리`로 이동합니다.
   - 권한은 **자산조회만** 선택합니다.
   - 주문조회·주문하기·입금조회·출금조회·출금하기 권한은 선택하지 않습니다.
   - 허용 IP에는 1번 프록시의 고정 IPv4만 등록합니다.
   - 발급 직후 Access Key와 한 번만 표시되는 Secret Key를 안전하게 보관합니다.
3. Supabase 비밀값 입력
   - Supabase 프로젝트 `pgtxtnggjqaysjhtdepz`의 Edge Functions Secrets에서 아래 네 값을 입력합니다.
   - `UPBIT_ACCESS_KEY`: 업비트 Access Key
   - `UPBIT_SECRET_KEY`: 업비트 Secret Key
   - `UPBIT_PROXY_URL`: 예: `https://upbit-proxy.example.com`
   - `UPBIT_PROXY_TOKEN`: 프록시에 설정한 긴 인증 토큰
4. 대시보드 확인
   - Coin Signal Desk에 기존 소유자 이메일 계정으로 로그인합니다.
   - 코인 화면의 `내 업비트 보유현황`은 평가금액 내림차순으로 자동 표시됩니다.
   - `내 설정 → 업비트 계좌 자동 동기화 → 지금 동기화`로 즉시 다시 조회할 수 있습니다.

API Key와 프록시 토큰은 채팅, GitHub 코드, 브라우저 저장소에 입력하지 않습니다.
