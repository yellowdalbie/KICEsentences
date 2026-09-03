// PM2 실행 설정.
//
// 비밀값(FLASK_SECRET_KEY, RESEND_API_KEY, BASE_URL, ADMIN_KEY 등)은 여기서
// 다루지 않는다. dashboard.py 가 기동 시 .env 를 직접 읽으므로 출처를 한 곳으로
// 둔다. 여기서 함께 넘기면 .env 가 없을 때 빈 문자열이 전달되고, 그러면
// os.environ.get(키, 기본값) 이 기본값을 쓰지 않아 secret_key 가 빈 값이 되어
// 세션을 쓰는 모든 라우트가 500 이 된다.
//
// 주의: pm2 restart --update-env 는 프로세스 환경변수를 아래 env 블록으로
// '교체'한다. 그러므로 이 블록에는 실행 방식을 정하는 값만 둔다.

module.exports = {
  apps: [
    {
      name: 'think-lynx-dashboard',
      script: 'dashboard.py',
      interpreter: 'python3',
      env: {
        OFFLINE_MODE: '0',
        KICE_PORT: '8182',
        KICE_HOST: '127.0.0.1'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    }
  ]
};
