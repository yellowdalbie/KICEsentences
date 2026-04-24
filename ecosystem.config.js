const fs = require('fs');
const path = require('path');

// .env.production 파일에서 SMTP 자격증명 로드 (git 미추적)
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

const secrets = loadEnv(path.join(__dirname, '.env.production'));

module.exports = {
  apps: [
    {
      name: 'think-lynx-dashboard',
      script: 'dashboard.py',
      interpreter: 'python3',
      env: {
        OFFLINE_MODE: '0',
        KICE_PORT: '8181',
        KICE_HOST: '0.0.0.0',
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
