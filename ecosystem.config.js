module.exports = {
  apps: [
    {
      name: 'kice-dashboard',
      script: '/home/ubuntu/.local/bin/gunicorn',
      args: '--workers 1 --threads 4 --bind 0.0.0.0:8181 dashboard:app',
      interpreter: 'none',
      env: {
        OFFLINE_MODE: '0',
        KICE_PORT: '5050',
        KICE_HOST: '0.0.0.0'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    }
  ]
};
