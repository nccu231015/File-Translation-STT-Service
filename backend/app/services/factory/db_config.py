import os

# MSSQL (產線資訊) Connection Config
MSSQL_CONFIG = {
    "server": os.getenv("MSSQL_HOST", "172.16.102.8"),
    "user": "reportdbr",
    "password": "For1014Select",
    "database": "reportdb",
    "as_dict": True
}

# PostgreSQL (設備資訊) Connection Config
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "172.16.2.24"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "user": "read_user",
    "password": "Read260316",
    "database": "postgres"
}

