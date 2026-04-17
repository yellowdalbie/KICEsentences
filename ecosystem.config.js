module.exports = {
  apps: [
    {
      name: 'kice-dashboard',
      script: '-m',
      args: 'gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8181 dashboard:app',
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
    }
  ]
};
