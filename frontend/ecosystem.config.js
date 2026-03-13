module.exports = {
    apps: [
        {
            name: "stt-translation-frontend",
            script: "npm",
            args: "start",
            cwd: "./",
            instances: 1,
            autorestart: true,
            watch: false,
            max_memory_restart: "1G",
            env: {
                NODE_ENV: "production",
                PORT: 3000,
                // API URL pointing to backend via Nginx HTTPS proxy
                NEXT_PUBLIC_API_URL: "https://172.16.2.68:8000"
            }
        }
    ]
};
