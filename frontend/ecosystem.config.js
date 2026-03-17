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
                // 指定後端實體位址（由 Next.js server-side 呼叫）
                BACKEND_URL: "http://172.16.2.68:8000"
            }
        }
    ]
};
