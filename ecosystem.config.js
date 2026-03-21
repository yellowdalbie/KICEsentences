module.exports = {
  apps: [
    {
      name: 'kice-dashboard',
      script: 'dashboard.py',
      interpreter: 'python3',
      env: {
        OFFLINE_MODE: '0',
        KICE_PORT: '5050',
        KICE_HOST: '0.0.0.0'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    },
    {
      name: 'kice-landing',
      script: './landing/app.py',
      interpreter: 'python3',
      env: {
        PORT: '8181',
        ADMIN_KEY: 'kice-lynx-admin' // 필요시 변경하세요
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M'
    }
  ]
};
