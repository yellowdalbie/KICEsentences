const fs = require('fs');
const path = require('path');

// .env, .env.production 에서 자격증명 로드 (둘 다 git 미추적)
function loadEnv(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8')
      .split('\n')
      .filter(l => l.includes('=') && !l.startsWith('#'))
      .reduce((acc, l) => {
        const [k, ...v] = l.split('=');
        acc[k.trim()] = v.join('=').trim();
        return acc;
      }, {});
  } catch (e) {
    return {};
  }
}

// .env 를 먼저 읽고 .env.production 으로 덮어쓴다(뒤가 우선).
// 주의: pm2 restart --update-env 는 프로세스 환경변수를 이 env 블록으로 '교체'한다.
// 여기에 없는 키는 이전 기동에서 들고 있던 값까지 함께 사라지므로,
// 앱이 os.environ 으로 읽는 키는 빠짐없이 아래 env 에 나열해야 한다.
const secrets = Object.assign(
  loadEnv(path.join(__dirname, '.env')),
  loadEnv(path.join(__dirname, '.env.production'))
);

module.exports = {
  apps: [
    {
      name: 'think-lynx-dashboard',
      script: 'dashboard.py',
      interpreter: 'python3',
      env: {
        OFFLINE_MODE: '0',
        KICE_PORT: '8182',
        KICE_HOST: '127.0.0.1',
        // 고정값이 필수. 없으면 dashboard.py 가 os.urandom(24) 으로 매 기동마다
        // 새 키를 만들어 전 사용자 세션이 무효화된다.
        FLASK_SECRET_KEY: secrets.FLASK_SECRET_KEY || '',
        RESEND_API_KEY: secrets.RESEND_API_KEY || '',
        BASE_URL: secrets.BASE_URL || '',
        ADMIN_KEY: secrets.ADMIN_KEY || '',
        SMTP_EMAIL: secrets.SMTP_EMAIL || '',
        SMTP_PASSWORD: secrets.SMTP_PASSWORD || ''
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    }
  ]
};
