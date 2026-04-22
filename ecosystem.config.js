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
        SMTP_EMAIL: 'thinklynx@zohomail.com',
        SMTP_PASSWORD: 'YC57ChLd3Gx5'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    }
  ]
};
