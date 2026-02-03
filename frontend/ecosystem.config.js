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
                // Host-side API URL (Docker container mapped to host port 8000)
                NEXT_PUBLIC_API_URL: "http://localhost:8000"
            }
        }
    ]
};
