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
                // 供 next.config.ts 的 rewrite 使用（server-side proxy 到後端）
                BACKEND_URL: "http://127.0.0.1:8000",
                // 供前端元件使用（瀏覽器可見）
                NEXT_PUBLIC_API_URL: "http://172.16.2.68:3000"
            }
        }
    ]
};
