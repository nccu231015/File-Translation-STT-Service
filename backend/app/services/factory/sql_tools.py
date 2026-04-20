import pymssql
import psycopg2
import psycopg2.extras
from typing import Dict, Any, List
from .db_config import MSSQL_CONFIG, POSTGRES_CONFIG
from decimal import Decimal
import datetime

import re

def _sanitize(row: dict) -> dict:
    """
    Convert non-JSON-serializable types to safe Python equivalents.
    """
    clean = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            clean[k] = float(v)
        elif isinstance(v, (datetime.date, datetime.datetime)):
            clean[k] = v.isoformat()
        elif isinstance(v, bytes):
            # 先嘗試 UTF-8，失敗則用 CP950 (繁體中文 Big5)
            try:
                clean[k] = v.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    clean[k] = v.decode('cp950')
                except Exception:
                    clean[k] = v.decode('utf-8', errors='replace')
        else:
            clean[k] = v
    return clean

class FactorySqlTools:
    """
    負責與產線 (MSSQL) 和設備 (PostgreSQL) 互動的 SQL 工具庫。
    """

    def test_connections(self) -> dict:
        results = {"mssql": "failed", "postgres": "failed"}
        
        # Test MSSQL
        try:
            conn_ms = pymssql.connect(
                server=MSSQL_CONFIG['server'],
                user=MSSQL_CONFIG['user'],
                password=MSSQL_CONFIG['password'],
                database=MSSQL_CONFIG['database'],
                timeout=5
            )
            conn_ms.close()
            results["mssql"] = "ok"
        except Exception as e:
            print(f"[HealthCheck] MSSQL Test Failed: {e}")
            results["mssql"] = "failed"
            
        # Test PostgreSQL
        try:
            conn_pg = psycopg2.connect(
                host=POSTGRES_CONFIG['host'],
                port=POSTGRES_CONFIG['port'],
                user=POSTGRES_CONFIG['user'],
                password=POSTGRES_CONFIG['password'],
                database=POSTGRES_CONFIG['database'],
                connect_timeout=5
            )
            conn_pg.close()
            results["postgres"] = "ok"
        except Exception as e:
            print(f"[HealthCheck] Postgres Test Failed: {e}")
            results["postgres"] = "failed"
            
        return results

    def _execute_mssql_query(self, query: str) -> List[Dict[str, Any]]:
        import time
        max_retries = 2
        for attempt in range(max_retries):
            try:
                conn = pymssql.connect(
                    server=MSSQL_CONFIG['server'],
                    user=MSSQL_CONFIG['user'],
                    password=MSSQL_CONFIG['password'],
                    database=MSSQL_CONFIG['database'],
                    as_dict=True,
                    login_timeout=10,
                    timeout=90,       # query execution timeout (seconds); prevents View queries from hanging
                    charset='cp950'  # 繁體中文 Big5 編碼，防止中文亂碼
                )
                cursor = conn.cursor()
                print(f"\n[MSSQL Execute]\n{query}\n", flush=True)
                cursor.execute(query)
                result = cursor.fetchall()
                conn.close()
                return [_sanitize(dict(row)) for row in result]
            except Exception as e:
                print(f"[SQL Attempt {attempt+1}] Query failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return [{"error": str(e)}]

    def _build_line_filter(self, line_no: str, no_col: str = "[NO]") -> str:
        """
        Build a SQL WHERE condition for line_no that handles both numeric IDs
        (e.g. '302') and human-readable names (e.g. 'SMT B', '三樓A線').
        - Numeric  -> direct equality:  CAST([NO] AS VARCHAR(50)) = '302'
        - Name     -> lookup via Scx_base.scx_value LIKE '%SMT B%'
        """
        safe = str(line_no).replace("'", "''")
        if safe.strip().isdigit():
            # Pure numeric ID – direct match
            return f"CAST({no_col} AS VARCHAR(50)) = '{safe}'"
        else:
            # Name-based – resolve scx_no from Scx_base first
            return (
                f"CAST({no_col} AS VARCHAR(50)) IN ("
                f"SELECT CAST(scx_no AS VARCHAR(50)) FROM [dbo].[Scx_base] "
                f"WHERE scx_value LIKE '%{safe}%'"
                f")"
            )


        
    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-A: Real-time equipment operation status (all floors or specific floor)
    # Req 1: table by floor × device-type, with good/bad qty + date
    # ══════════════════════════════════════════════════════════════════════════════
    def get_equipment_operation_status(
        self,
        floor: str = None,
        target_date: str = None
    ) -> Dict[str, Any]:
        """
        EQ-A: Equipment production summary grouped by floor.
        Returns RUN/DOWN/IDEL/SHUTDOWN minutes, 稼動率, and 良品數/不良數/良率 per device.
        Code classification: RUN=A003, DOWN=A001/A006-A009, IDEL=A002/A011-A014, SHUTDOWN=A004/A010.
        """
        if not target_date:
            target_date = datetime.date.today().isoformat()
        target_ymd  = target_date.replace('-', '')
        safe_floor = floor.replace("'", "''") if floor else ''
        floor_filter = f"AND e.\"EQUIP_INSTALL_POSITION\" ILIKE '%{safe_floor[0]}%'" if floor and len(safe_floor)>0 else ""

        query = f"""
            WITH eq_info AS (
                -- Deduplicate EQUIPMENT_INFO_DICT: one row per EQUIPMENT_CODE (latest GDHM)
                SELECT DISTINCT ON ("EQUIPMENT_CODE")
                    "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC",
                    "EQUIP_INSTALL_POSITION", "GDHM"
                FROM "public"."EQUIPMENT_INFO_DICT"
                -- Prefer rows with floor and topic populated, then latest GDHM
                ORDER BY "EQUIPMENT_CODE",
                    CASE WHEN "EQUIP_INSTALL_POSITION" IS NOT NULL AND "EQUIP_INSTALL_POSITION" != '' THEN 0 ELSE 1 END,
                    CASE WHEN "TOPIC" IS NOT NULL AND "TOPIC" != '' THEN 0 ELSE 1 END,
                    "GDHM" DESC NULLS LAST
            ),
            deltas AS (
                -- Compute duration per state interval using LAG within (TOPIC, date)
                -- Source: CIM_MQTTCOLLECT_AM_PM; DATETIMES format = YYYYMMDDTHHMMSS.xxxxx
                SELECT
                    "TOPIC" AS "SBMC",
                    LAG("CODE") OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS prev_code,
                    (SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                     + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                     + SUBSTRING("DATETIMES", 14, 2)::INT)
                    - LAG(
                        SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                        + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                        + SUBSTRING("DATETIMES", 14, 2)::INT
                    ) OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS duration_sec
                FROM "public"."CIM_MQTTCOLLECT_AM_PM"
                WHERE SUBSTRING("DATETIMES", 1, 8) = '{target_ymd}'
                  AND LENGTH("DATETIMES") >= 14
            ),
            times AS (
                -- Classify each interval into RUN/DOWN/IDEL/SHUTDOWN using confirmed code mapping
                SELECT "SBMC",
                    ROUND(SUM(CASE WHEN prev_code = 'A003' AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "RUN",
                    ROUND(SUM(CASE WHEN prev_code IN ('A001','A006','A007','A008','A009') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "DOWN",
                    ROUND(SUM(CASE WHEN prev_code IN ('A002','A011','A012','A013','A014') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "IDEL",
                    ROUND(SUM(CASE WHEN prev_code IN ('A004','A010') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "SHUTDOWN"
                FROM deltas
                WHERE prev_code IS NOT NULL
                GROUP BY "SBMC"
            ),
            daily_qty AS (
                SELECT "SBMC", SUM("LPSL") AS "LPSL", SUM("BLSL") AS "BLSL"
                FROM "public"."CIM_MQTT_OK_NG_QTY"
                WHERE "YMD" = '{target_ymd}'
                GROUP BY "SBMC"
            )
            SELECT
                COALESCE(e."EQUIP_INSTALL_POSITION", 'N/A')  AS "樓層",
                COALESCE(e."EQUIPMENT_CODE", e."TOPIC")       AS "設備代碼",
                e."EQUIPMENT_NAME"                            AS "設備名稱",
                COALESCE(t."RUN", 0)                          AS "RUN(分)",
                COALESCE(t."DOWN", 0)                         AS "DOWN(分)",
                COALESCE(t."IDEL", 0)                         AS "IDEL(分)",
                COALESCE(t."SHUTDOWN", 0)                     AS "SHUTDOWN(分)",
                CASE WHEN (COALESCE(t."RUN", 0) + COALESCE(t."DOWN", 0)) > 0
                     THEN ROUND((COALESCE(t."RUN", 0)::FLOAT / (COALESCE(t."RUN", 0) + COALESCE(t."DOWN", 0)) * 100)::NUMERIC, 2)
                     ELSE NULL END                            AS "稼動率(%)",
                COALESCE(q."LPSL", 0)                         AS "良品數量",
                COALESCE(q."BLSL", 0)                         AS "不良數量",
                CASE WHEN (COALESCE(q."LPSL", 0) + COALESCE(q."BLSL", 0)) > 0
                     THEN ROUND((COALESCE(q."LPSL", 0)::FLOAT / (COALESCE(q."LPSL", 0) + COALESCE(q."BLSL", 0)) * 100)::NUMERIC, 2)
                     ELSE NULL END                            AS "良率(%)"
            FROM eq_info e
            LEFT JOIN times t ON (t."SBMC" = e."TOPIC" OR t."SBMC" = e."EQUIPMENT_CODE")
            LEFT JOIN daily_qty q ON (q."SBMC" = e."TOPIC" OR q."SBMC" = e."EQUIPMENT_CODE")
            WHERE 1=1
            {floor_filter}
            ORDER BY "樓層", "設備名稱", "設備代碼"
        """
        rows = self._execute_postgres_query(query)

        import re as _re
        def _derive_type(name: str) -> str:
            """
            Derive machine type from equipment name by stripping trailing
            alphanumeric identifiers (e.g. 'WELD2A' → 'WELD', '成型機-03' → '成型機').
            Falls back to first 4 chars if pattern can not be extracted.
            """
            if not name:
                return '-'
            m = _re.match(r'^([^\d\-_A-Z]+)', name, _re.UNICODE)
            if m and len(m.group(1)) >= 2:
                return m.group(1).strip()
            return name[:4].strip() if len(name) >= 4 else name

        clean_rows = []
        for r in rows:
            util    = r.get('稼動率(%)')
            eq_name = r.get('設備名稱') or ''
            clean_rows.append({
                '樓層':       r.get('樓層', 'N/A'),
                '機型':       _derive_type(eq_name),
                '設備(代碼)': f"{eq_name} ({r.get('設備代碼', '')})",
                'RUN(分)':    int(r.get('RUN(分)', 0) or 0),
                'DOWN(分)':   int(r.get('DOWN(分)', 0) or 0),
                '稼動率(%)':  round(float(util), 2) if util is not None else '-',
            })

        return {
            "status":     "success",
            "query_date": target_date,
            "floor":      floor or "全廠",
            "data":       clean_rows
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-B: Underperforming equipment (yield rate < threshold)
    # Req 2: table with red highlight flag for yield < 80%
    # ══════════════════════════════════════════════════════════════════════════════
    def get_underperforming_equipment(
        self,
        target_date: str = None,
        threshold: float = 80.0
    ) -> Dict[str, Any]:
        """
        EQ-B: Find equipment with yield rate (良率) below threshold (default 80%).
        良率 = LPSL / (LPSL + BLSL) * 100.
        Returns: all equipment, flagging below-threshold with below_threshold=True.
        """
        if not target_date:
            target_date = datetime.date.today().isoformat()
        target_ymd = target_date.replace('-', '')

        query = f"""
            SELECT
                COALESCE(e."EQUIP_INSTALL_POSITION", 'N/A') AS "樓層",
                q."SBMC"                                     AS "設備代碼",
                COALESCE(e."EQUIPMENT_NAME", q."SBMC")       AS "設備名稱",
                COALESCE(SUM(q."LPSL"), 0)                   AS "良品數量",
                COALESCE(SUM(q."BLSL"), 0)                   AS "不良數量",
                CASE
                    WHEN COALESCE(SUM(q."LPSL"), 0) + COALESCE(SUM(q."BLSL"), 0) > 0
                    THEN ROUND((
                        COALESCE(SUM(q."LPSL"), 0)::FLOAT /
                        (COALESCE(SUM(q."LPSL"), 0) + COALESCE(SUM(q."BLSL"), 0)) * 100
                    )::NUMERIC, 2)
                    ELSE NULL
                END AS "良率(%)",
                '{target_date}' AS "資料日期"
            FROM "public"."CIM_MQTT_OK_NG_QTY" q
            LEFT JOIN "public"."EQUIPMENT_INFO_DICT" e ON (e."TOPIC" = q."SBMC" OR e."EQUIPMENT_CODE" = q."SBMC")
            WHERE q."YMD" = '{target_ymd}'
            GROUP BY e."EQUIP_INSTALL_POSITION", q."SBMC", e."EQUIPMENT_NAME"
            ORDER BY "樓層", "設備代碼"
        """
        rows = self._execute_postgres_query(query)
        below_count = 0
        clean_rows = []
        for row in rows:
            rate = row.get('良率(%)')
            if rate is not None and float(rate) < threshold:
                clean_rows.append({
                    '樓層': row.get('樓層', '未知'),
                    '設備(代碼)': f"{row.get('設備名稱')} ({row.get('設備代碼')})",
                    '產出(良/不良)': f"{row.get('良品數量', 0)} / {row.get('不良數量', 0)}",
                    '良率(%)': rate,
                    '狀態燈': '🔴 未達標'
                })
                below_count += 1
                
        return {
            "status":          "success",
            "query_date":      target_date,
            "threshold":       threshold,
            "total_failed":    below_count,
            "data":            clean_rows
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-C: Floor equipment status with latest raw signal code and daily yield
    # Returns latest CODE per device (no hardcoded classification) + 良率 from DB
    # ══════════════════════════════════════════════════════════════════════════════
    def get_floor_equipment_status(
        self,
        floor: str,
        target_date: str = None
    ) -> Dict[str, Any]:
        """
        EQ-C: Per-floor equipment status with RUN/DOWN/IDEL/SHUTDOWN minutes, 稼動率, and 良率.
          - State classification: RUN=A003, DOWN=A001/A006-A009, IDEL=A002/A011-A014, SHUTDOWN=A004/A010
          - Daily state time from CIM_MQTTCOLLECT LAG computation
          - 良率 from CIM_MQTT_OK_NG_QTY LPSL/BLSL
        """
        if not target_date:
            target_date = datetime.date.today().isoformat()
        target_ymd  = target_date.replace('-', '')
        safe_floor  = floor.replace("'", "''") if floor else ''
        query_daily = f"""
            WITH eq_info AS (
                -- Deduplicate EQUIPMENT_INFO_DICT: one row per EQUIPMENT_CODE (latest GDHM)
                SELECT DISTINCT ON ("EQUIPMENT_CODE")
                    "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC",
                    "EQUIP_INSTALL_POSITION", "GDHM"
                FROM "public"."EQUIPMENT_INFO_DICT"
                -- Prefer rows with floor and topic populated, then latest GDHM
                ORDER BY "EQUIPMENT_CODE",
                    CASE WHEN "EQUIP_INSTALL_POSITION" IS NOT NULL AND "EQUIP_INSTALL_POSITION" != '' THEN 0 ELSE 1 END,
                    CASE WHEN "TOPIC" IS NOT NULL AND "TOPIC" != '' THEN 0 ELSE 1 END,
                    "GDHM" DESC NULLS LAST
            ),
            deltas AS (
                -- LAG-based duration within each (TOPIC, date) to avoid cross-day bleeding
                -- Source: CIM_MQTTCOLLECT_AM_PM; DATETIMES format = YYYYMMDDTHHMMSS.xxxxx
                SELECT
                    "TOPIC" AS "SBMC",
                    LAG("CODE") OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS prev_code,
                    (SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                     + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                     + SUBSTRING("DATETIMES", 14, 2)::INT)
                    - LAG(
                        SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                        + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                        + SUBSTRING("DATETIMES", 14, 2)::INT
                    ) OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS duration_sec
                FROM "public"."CIM_MQTTCOLLECT_AM_PM"
                WHERE SUBSTRING("DATETIMES", 1, 8) = '{target_ymd}'
                  AND LENGTH("DATETIMES") >= 14
            ),
            times AS (
                -- Aggregate minutes per state category using confirmed code mapping
                SELECT "SBMC",
                    ROUND(SUM(CASE WHEN prev_code = 'A003' AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "RUN",
                    ROUND(SUM(CASE WHEN prev_code IN ('A001','A006','A007','A008','A009') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "DOWN",
                    ROUND(SUM(CASE WHEN prev_code IN ('A002','A011','A012','A013','A014') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "IDEL",
                    ROUND(SUM(CASE WHEN prev_code IN ('A004','A010') AND duration_sec > 0 THEN duration_sec ELSE 0 END) / 60.0) AS "SHUTDOWN"
                FROM deltas
                WHERE prev_code IS NOT NULL
                GROUP BY "SBMC"
            ),
            daily_qty AS (
                SELECT "SBMC", SUM("LPSL") AS "LPSL", SUM("BLSL") AS "BLSL"
                FROM "public"."CIM_MQTT_OK_NG_QTY"
                WHERE "YMD" = '{target_ymd}'
                GROUP BY "SBMC"
            )
            SELECT
                COALESCE(e."EQUIPMENT_CODE", e."TOPIC") AS "設備代碼",
                e."EQUIPMENT_NAME"                      AS "設備名稱",
                COALESCE(t."RUN", 0)                    AS "RUN(分)",
                COALESCE(t."DOWN", 0)                   AS "DOWN(分)",
                COALESCE(t."IDEL", 0)                   AS "IDEL(分)",
                COALESCE(t."SHUTDOWN", 0)               AS "SHUTDOWN(分)",
                CASE WHEN (COALESCE(t."RUN", 0) + COALESCE(t."DOWN", 0)) > 0
                     THEN ROUND((COALESCE(t."RUN", 0)::FLOAT / (COALESCE(t."RUN", 0) + COALESCE(t."DOWN", 0)) * 100)::NUMERIC, 2)
                     ELSE NULL END                      AS "稼動率(%)",
                COALESCE(q."LPSL", 0)                   AS "良品數量",
                COALESCE(q."BLSL", 0)                   AS "不良數量",
                '{target_date}'                         AS "資料日期"
            FROM eq_info e
            LEFT JOIN times t ON (t."SBMC" = e."TOPIC" OR t."SBMC" = e."EQUIPMENT_CODE")
            LEFT JOIN daily_qty q ON (q."SBMC" = e."TOPIC" OR q."SBMC" = e."EQUIPMENT_CODE")
            WHERE e."EQUIP_INSTALL_POSITION" ILIKE '%{safe_floor[0] if safe_floor else ''}%'
            ORDER BY "設備名稱", "設備代碼"
        """

        from datetime import datetime as dt, timedelta

        # Current state: classify latest CODE per device using confirmed code mapping
        # Source: CIM_MQTTCOLLECT_AM_PM; DATETIMES format = YYYYMMDDTHHMMSS.xxxxx
        seven_days_ago_ymd = (dt.strptime(target_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y%m%d")
        query_state = f"""
            SELECT
                COALESCE(e."EQUIPMENT_CODE", sub."TOPIC") AS "設備代碼",
                CASE
                    WHEN sub."CODE" = 'A003' THEN 'RUN'
                    WHEN sub."CODE" IN ('A001','A006','A007','A008','A009') THEN 'DOWN'
                    WHEN sub."CODE" IN ('A002','A011','A012','A013','A014') THEN 'IDEL'
                    WHEN sub."CODE" IN ('A004','A010') THEN 'SHUTDOWN'
                    ELSE sub."CODE"
                END AS "稼動狀態",
                sub."CODE" AS "最新狀態碼"
            FROM (
                SELECT "TOPIC", "CODE",
                       ROW_NUMBER() OVER (
                           PARTITION BY "TOPIC"
                           ORDER BY "DATETIMES" DESC
                       ) AS rn
                FROM "public"."CIM_MQTTCOLLECT_AM_PM"
                WHERE SUBSTRING("DATETIMES", 1, 8) >= '{seven_days_ago_ymd}'
                  AND LENGTH("DATETIMES") >= 14
                  AND "CODE" IN ('A001','A002','A003','A004','A006','A007','A008','A009','A010','A011','A012','A013','A014')
            ) sub
            LEFT JOIN "public"."EQUIPMENT_INFO_DICT" e ON e."TOPIC" = sub."TOPIC"
            WHERE sub.rn = 1
        """

        daily_rows = self._execute_postgres_query(query_daily)
        state_rows = self._execute_postgres_query(query_state)
        # Map device code to (稼動狀態, 最新狀態碼)
        state_map  = {r['設備代碼']: (r.get('稼動狀態', '-'), r.get('最新狀態碼', '-')) for r in state_rows}

        STATE_ICON = {'RUN': '🟢', 'DOWN': '🔴', 'IDEL': '🟡', 'SHUTDOWN': '⚫'}

        running_count = 0
        stopped_count = 0
        clean_rows = []
        for row in daily_rows:
            code       = row.get('設備代碼', '')
            state_pair = state_map.get(code, ('-', '-'))
            state      = state_pair[0]
            raw_code   = state_pair[1]
            icon       = STATE_ICON.get(state, '⚪')
            good       = int(row.get('良品數量', 0) or 0)
            bad        = int(row.get('不良數量', 0) or 0)
            util_raw   = row.get('稼動率(%)')
            util       = round(float(util_raw), 2) if util_raw is not None else '-'
            yld        = round(good / (good + bad) * 100, 2) if (good + bad) > 0 else '-'
            if state == 'RUN':
                running_count += 1
            elif state == 'DOWN':
                stopped_count += 1
            clean_rows.append({
                '設備(代碼)':  f"{row.get('設備名稱')} ({code})",
                '稼動狀態':    f"{icon} {state}",
                '最新狀態碼':  raw_code,
                'RUN(分)':     int(row.get('RUN(分)', 0) or 0),
                'DOWN(分)':    int(row.get('DOWN(分)', 0) or 0),
                '稼動率(%)':   util,
                '生產數':      good,
                '不良數':      bad,
                '良率(%)':    yld,
            })

        floor_utilization = round(running_count / len(daily_rows) * 100, 1) if daily_rows else 0
        return {
            "status":                "success",
            "floor":                 floor,
            "query_date":            target_date,
            "total_equipment":       len(daily_rows),
            "running_count":         running_count,
            "stopped_count":         stopped_count,
            "floor_utilization_pct": floor_utilization,
            "data":                  clean_rows,
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-D: Equipment model production trend (cross-DB PG → MSSQL)
    # Data flow:
    #   EQUIPMENT_INFO_DICT (PG)
    #     ├─ TOPIC / EQUIPMENT_CODE → CIM_MQTT_OK_NG_QTY.SBMC  (daily LPSL/BLSL)
    #     └─ GDHM (work order)      → MSSQL Daily_Status_Report.WORK_ORDER_NO → jz (model name)
    # ══════════════════════════════════════════════════════════════════════════════
    def get_equipment_model_production_trend(
        self,
        start_date: str,
        end_date: str,
        equipment_code: str = None,
        equipment_name: str = None,
        granularity: str = 'monthly',
        include_chart: bool = False
    ) -> Dict[str, Any]:
        """
        EQ-D: Per-equipment production trend with model name resolution.
        - Q4 (include_chart=False): table of models produced + summary qty/yield
        - Q5 (include_chart=True):  time-series bar(qty)+line(defect rate) chart_config
        granularity: daily | weekly | monthly | quarterly | half_yearly | yearly
        """
        import re as _re

        # ── Step 1: Resolve TOPIC and GDHM from EQUIPMENT_INFO_DICT ─────────────
        safe_kw = (equipment_name or equipment_code or "").replace("'", "''")
        info_q = f"""
            SELECT "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC", "GDHM"
            FROM "public"."EQUIPMENT_INFO_DICT"
            WHERE "EQUIPMENT_NAME" ILIKE '%{safe_kw}%'
               OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%'
        """
        info_rows = self._execute_postgres_query(info_q)
        if not info_rows:
            return {"status": "error", "message": f"找不到設備：{safe_kw}"}

        # Prefer exact match (EQUIPMENT_CODE == kw or EQUIPMENT_NAME == kw) over partial ILIKE hits
        exact = [r for r in info_rows
                 if (r.get("EQUIPMENT_CODE") or "").upper() == safe_kw.upper()
                 or (r.get("EQUIPMENT_NAME") or "").upper() == safe_kw.upper()]
        primary_row = exact[0] if exact else info_rows[0]

        eq_name  = primary_row.get("EQUIPMENT_NAME") or safe_kw
        eq_code  = primary_row.get("EQUIPMENT_CODE") or safe_kw
        topic    = primary_row.get("TOPIC") or eq_code

        # Collect ALL unique GDHMs only from rows that share the same EQUIPMENT_CODE
        same_device_rows = [r for r in info_rows if r.get("EQUIPMENT_CODE") == eq_code]
        unique_gdhms = list({r.get("GDHM") for r in same_device_rows if r.get("GDHM")})

        # ── Step 2: Resolve model names via MSSQL Daily_Status_Report ────────────
        # GDHM (EQUIPMENT_INFO_DICT) → WORK_ORDER_NO → jz (machine model name)
        # If GDHM is NULL in EQUIPMENT_INFO_DICT, model lookup cannot proceed.
        model_names: List[str] = []
        gdhm_available = bool(unique_gdhms)
        if unique_gdhms:
            gdhm_in = ",".join(f"'{g}'" for g in unique_gdhms)
            ms_q = f"""
                SELECT DISTINCT jz AS [機種名稱]
                FROM [dbo].[Daily_Status_Report]
                WHERE [WORK_ORDER_NO] IN ({gdhm_in})
                  AND jz IS NOT NULL AND jz <> ''
            """
            ms_rows = self._execute_mssql_query(ms_q)
            model_names = [r.get("機種名稱") for r in ms_rows if r.get("機種名稱")]

        # ── Step 3: Fetch daily LPSL / BLSL from CIM_MQTT_OK_NG_QTY ─────────────
        # SBMC may store TOPIC, EQUIPMENT_CODE, or other device identifiers.
        # Use multi-strategy filter to avoid format mismatches:
        #   1. SBMC matches TOPIC values in EQUIPMENT_INFO_DICT
        #   2. SBMC matches EQUIPMENT_CODE values in EQUIPMENT_INFO_DICT
        #   3. SBMC ILIKE '%keyword%' as safety fallback
        start_ymd = start_date.replace('-', '')
        end_ymd   = end_date.replace('-', '')
        safe_kw_qty = safe_kw.replace("'", "''")

        qty_q = f"""
            SELECT
                "YMD"                        AS "日期碼",
                SUM(COALESCE("LPSL", 0))     AS "良品數量",
                SUM(COALESCE("BLSL", 0))     AS "不良數量"
            FROM "public"."CIM_MQTT_OK_NG_QTY"
            WHERE "YMD" BETWEEN '{start_ymd}' AND '{end_ymd}'
              AND (
                "SBMC" IN (
                    SELECT "TOPIC" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw_qty}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw_qty}%')
                      AND "TOPIC" IS NOT NULL
                )
                OR "SBMC" IN (
                    SELECT "EQUIPMENT_CODE" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw_qty}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw_qty}%')
                      AND "EQUIPMENT_CODE" IS NOT NULL
                )
                OR "SBMC" ILIKE '%{safe_kw_qty}%'
              )
            GROUP BY "YMD"
            ORDER BY "YMD"
        """
        qty_rows = self._execute_postgres_query(qty_q)

        # ── Step 4: Convert YMD (YYYYMMDD) to period label by granularity ────────
        def ymd_to_period(ymd: str, gran: str) -> str:
            """Convert YYYYMMDD string to a period label for the given granularity."""
            try:
                y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])
                dt = datetime.date(y, m, d)
                if gran == 'daily':
                    return dt.isoformat()
                elif gran == 'weekly':
                    return f"{y}-W{dt.isocalendar()[1]:02d}"
                elif gran == 'monthly':
                    return f"{y}-{m:02d}"
                elif gran == 'quarterly':
                    return f"{y}-Q{(m - 1) // 3 + 1}"
                elif gran == 'half_yearly':
                    return f"{y}-{'1H' if m <= 6 else '2H'}"
                elif gran == 'yearly':
                    return str(y)
            except Exception:
                pass
            return ymd  # fallback

        # Aggregate by period
        period_good: Dict[str, float] = {}
        period_bad:  Dict[str, float] = {}
        for row in qty_rows:
            ymd  = str(row.get("日期碼") or "")
            good = float(row.get("良品數量") or 0)
            bad  = float(row.get("不良數量") or 0)
            p    = ymd_to_period(ymd, granularity)
            period_good[p] = period_good.get(p, 0) + good
            period_bad[p]  = period_bad.get(p,  0) + bad

        periods = sorted(period_good.keys())

        # Build trend table
        trend_data = []
        for p in periods:
            good = period_good[p]
            bad  = period_bad[p]
            total = good + bad
            defect_rate = round(bad / total * 100, 4) if total > 0 else 0
            yield_rate  = round(good / total * 100, 2) if total > 0 else 0
            trend_data.append({
                "時間標籤":    p,
                "良品數量":    int(good),
                "不良數量":    int(bad),
                "總產量":      int(total),
                "不良率(%)":  defect_rate,
                "良率(%)":    yield_rate,
            })

        # ── Step 5: Build chart_config (bar_line_combo) if requested ─────────────
        chart_config = None
        if include_chart and periods:
            qty_data  = [int(period_good[p] + period_bad[p]) for p in periods]
            rate_data = [
                round(period_bad[p] / (period_good[p] + period_bad[p]) * 100, 4)
                if (period_good[p] + period_bad[p]) > 0 else 0
                for p in periods
            ]
            chart_config = {
                "chart_type": "bar_line_combo",
                "title":      f"{eq_name} 產量與不良率趨勢（{granularity}）",
                "labels":     periods,
                "datasets": [
                    {
                        "type":            "bar",
                        "label":           "總產量",
                        "data":            qty_data,
                        "yAxisID":         "y_quantity",
                        "backgroundColor": "rgba(99, 102, 241, 0.55)",
                        "borderColor":     "rgba(99, 102, 241, 1)",
                    },
                    {
                        "type":        "line",
                        "label":       "不良率 (%)",
                        "data":        rate_data,
                        "yAxisID":     "y_defect_rate",
                        "borderColor": "rgba(239, 68, 68, 1)",
                        "fill":        False,
                        "tension":     0.3,
                    },
                ],
                "yAxes": {
                    "y_quantity":    {"label": "總產量 (件)", "position": "left"},
                    "y_defect_rate": {"label": "不良率 (%)", "position": "right"},
                },
            }

        # Total summary
        total_good_all = sum(period_good.values())
        total_bad_all  = sum(period_bad.values())
        total_all      = total_good_all + total_bad_all

        return {
            "status":         "success",
            "equipment_name": eq_name,
            "equipment_code": eq_code,
            "topic":          topic,
            "period":         f"{start_date} ~ {end_date}",
            "granularity":    granularity,
            "model_names":    model_names,   # jz from Daily_Status_Report via GDHM
            "gdhm_available": gdhm_available, # False = GDHM is NULL in EQUIPMENT_INFO_DICT, model lookup skipped
            "debug_gdhms":    unique_gdhms,   # work order numbers found (empty = GDHM not set)
            "summary": {
                "總產量":    int(total_all),
                "良品數量":  int(total_good_all),
                "不良數量":  int(total_bad_all),
                "良率(%)":  round(total_good_all / total_all * 100, 2) if total_all > 0 else 0,
                "不良率(%)": round(total_bad_all  / total_all * 100, 4) if total_all > 0 else 0,
            },
            "trend_data":     trend_data,    # time-series rows for table display
            "chart_config":   chart_config,  # None when include_chart=False
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-E: Downtime anomaly ranking (Top-N machines by total DOWN time in a period)
    # Supports Pareto chart: bar = downtime hours desc, line = cumulative %
    # DOWN codes: A001, A006, A007, A008, A009 (actual names stored in CIM_MQTTCODEERR.NOTE)
    # ══════════════════════════════════════════════════════════════════════════════
    def get_downtime_anomaly_ranking(
        self,
        start_date: str,
        end_date: str,
        top_n: int = 10,
        floor: str = None,
        include_chart: bool = False,
        include_cause: bool = True
    ) -> Dict[str, Any]:
        """
        EQ-E: Rank equipment by total downtime hours in [start_date, end_date].
        Returns Top-N list. include_cause=True adds 主要停機原因 via B-code co-occurrence.
        """
        start_ymd = start_date.replace('-', '')
        end_ymd   = end_date.replace('-', '')
        safe_floor = (floor or '').replace("'", "''")
        floor_join = f'AND e."EQUIP_INSTALL_POSITION" ILIKE \'%{safe_floor}%\'' if safe_floor else ''

        query = f"""
            WITH eq_info AS (
                SELECT DISTINCT ON ("EQUIPMENT_CODE")
                    "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC",
                    "EQUIP_INSTALL_POSITION"
                FROM "public"."EQUIPMENT_INFO_DICT"
                -- Prefer rows with floor and topic populated, then latest GDHM
                ORDER BY "EQUIPMENT_CODE",
                    CASE WHEN "EQUIP_INSTALL_POSITION" IS NOT NULL AND "EQUIP_INSTALL_POSITION" != '' THEN 0 ELSE 1 END,
                    CASE WHEN "TOPIC" IS NOT NULL AND "TOPIC" != '' THEN 0 ELSE 1 END,
                    "GDHM" DESC NULLS LAST
            ),
            -- LAG within each (TOPIC, date) to avoid cross-day bleeding
            -- Source: CIM_MQTTCOLLECT_AM_PM; DATETIMES format = YYYYMMDDTHHMMSS.xxxxx
            deltas AS (
                SELECT
                    "TOPIC" AS "SBMC",
                    SUBSTRING("DATETIMES", 1, 8) AS "YMD",
                    LAG("CODE") OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS prev_code,
                    (SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                     + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                     + SUBSTRING("DATETIMES", 14, 2)::INT)
                    - LAG(
                        SUBSTRING("DATETIMES", 10, 2)::INT * 3600
                        + SUBSTRING("DATETIMES", 12, 2)::INT * 60
                        + SUBSTRING("DATETIMES", 14, 2)::INT
                    ) OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS duration_sec
                FROM "public"."CIM_MQTTCOLLECT_AM_PM"
                WHERE SUBSTRING("DATETIMES", 1, 8) BETWEEN '{start_ymd}' AND '{end_ymd}'
                  AND LENGTH("DATETIMES") >= 14
            ),
            -- Sum DOWN-only intervals: A001/A006-A009
            down_totals AS (
                SELECT
                    "SBMC",
                    ROUND(SUM(CASE WHEN duration_sec > 0 THEN duration_sec ELSE 0 END) / 3600.0, 2) AS total_hours
                FROM deltas
                WHERE prev_code IN ('A001','A006','A007','A008','A009')
                GROUP BY "SBMC"
            )
            SELECT
                COALESCE(e."EQUIP_INSTALL_POSITION", 'N/A') AS "樓層",
                COALESCE(e."EQUIPMENT_NAME", d."SBMC")       AS "設備名稱",
                d."SBMC"                                      AS "設備代碼",
                d.total_hours                                 AS "停機時數(h)"
            FROM down_totals d
            LEFT JOIN eq_info e ON (e."TOPIC" = d."SBMC" OR e."EQUIPMENT_CODE" = d."SBMC")
            WHERE d.total_hours > 0
            {floor_join}
            ORDER BY d.total_hours DESC
            LIMIT {int(top_n)}
        """
        rows = self._execute_postgres_query(query)
        if not rows:
            return {
                "status": "success",
                "period": f"{start_date} ~ {end_date}",
                "message": "查詢期間內無停機紀錄",
                "data": [],
                "chart_config": None,
            }

        # Secondary query: fetch 主要停機原因 only when requested
        # Strategy 1 (same-second): B-codes co-occur within same second as DOWN A-codes
        # Strategy 2 (same-minute fallback): widen window to same minute for devices with no same-second match
        # B-code PLCCODE maps to CIM_MQTTCODEERR.NOTE for fault description
        topic_list = [r.get("設備代碼") for r in rows if r.get("設備代碼")]
        cause_map: Dict[str, str] = {}
        if include_cause and topic_list:
            topics_in = ",".join(f"'{t}'" for t in topic_list)

            # --- Pass 1: same-second co-occurrence (SUBSTRING 1→15) ---
            cause_query = f"""
                SELECT * FROM (
                    SELECT
                        b."TOPIC",
                        err."NOTE",
                        COUNT(*) AS "CS",
                        ROW_NUMBER() OVER (
                            PARTITION BY b."TOPIC"
                            ORDER BY COUNT(*) DESC
                        ) AS "RN"
                    FROM "public"."CIM_MQTTCOLLECT_AM_PM" b
                    JOIN "public"."CIM_MQTTCODEERR" err
                        ON b."CODE" = err."PLCCODE"
                    WHERE b."CODE" LIKE 'B%'
                      AND SUBSTRING(b."DATETIMES", 1, 8) BETWEEN '{start_ymd}' AND '{end_ymd}'
                      AND b."TOPIC" IN ({topics_in})
                      AND EXISTS (
                          SELECT 1 FROM "public"."CIM_MQTTCOLLECT_AM_PM" a
                          WHERE a."TOPIC" = b."TOPIC"
                            AND a."CODE" IN ('A001','A006','A007','A008','A009')
                            AND SUBSTRING(a."DATETIMES", 1, 15) = SUBSTRING(b."DATETIMES", 1, 15)
                      )
                    GROUP BY b."TOPIC", err."NOTE"
                ) "S"
                WHERE "S"."RN" = 1
            """
            cause_rows = self._execute_postgres_query(cause_query)
            cause_map = {r["TOPIC"]: r.get("NOTE") or "" for r in cause_rows if r.get("TOPIC")}

            # --- Pass 2: same-minute fallback for devices with no same-second result ---
            missing_topics = [t for t in topic_list if not cause_map.get(t)]
            if missing_topics:
                missing_in = ",".join(f"'{t}'" for t in missing_topics)
                fallback_query = f"""
                    SELECT * FROM (
                        SELECT
                            b."TOPIC",
                            err."NOTE",
                            COUNT(*) AS "CS",
                            ROW_NUMBER() OVER (
                                PARTITION BY b."TOPIC"
                                ORDER BY COUNT(*) DESC
                            ) AS "RN"
                        FROM "public"."CIM_MQTTCOLLECT_AM_PM" b
                        JOIN "public"."CIM_MQTTCODEERR" err
                            ON b."CODE" = err."PLCCODE"
                        WHERE b."CODE" LIKE 'B%'
                          AND SUBSTRING(b."DATETIMES", 1, 8) BETWEEN '{start_ymd}' AND '{end_ymd}'
                          AND b."TOPIC" IN ({missing_in})
                          AND EXISTS (
                              SELECT 1 FROM "public"."CIM_MQTTCOLLECT_AM_PM" a
                              WHERE a."TOPIC" = b."TOPIC"
                                AND a."CODE" IN ('A001','A006','A007','A008','A009')
                                AND SUBSTRING(a."DATETIMES", 1, 13) = SUBSTRING(b."DATETIMES", 1, 13)
                          )
                        GROUP BY b."TOPIC", err."NOTE"
                    ) "S"
                    WHERE "S"."RN" = 1
                """
                fallback_rows = self._execute_postgres_query(fallback_query)
                for r in fallback_rows:
                    t = r.get("TOPIC")
                    if t and not cause_map.get(t):
                        cause_map[t] = r.get("NOTE") or ""

        # Build clean output rows
        clean_rows = []
        for r in rows:
            hrs   = float(r.get("停機時數(h)") or 0)
            topic = r.get("設備代碼", "")
            row = {
                "排名":        len(clean_rows) + 1,
                "樓層":        r.get("樓層", "N/A"),
                "設備(代碼)":  f"{r.get('設備名稱')} ({topic})",
                "停機時數(h)": hrs,
            }
            if include_cause:
                row["主要停機原因"] = cause_map.get(topic) or "無對應故障代碼記錄"
            clean_rows.append(row)

        # Pareto chart: bars = total hours desc, line = cumulative %
        chart_config = None
        if include_chart and clean_rows:
            labels     = [r["設備(代碼)"] for r in clean_rows]
            bar_data   = [r["停機時數(h)"] for r in clean_rows]
            total_all  = sum(bar_data)
            cumulative = []
            running    = 0
            for v in bar_data:
                running += v
                cumulative.append(round(running / total_all * 100, 1) if total_all > 0 else 0)
            chart_config = {
                "chart_type": "bar_line_combo",
                "title":      f"停機時數 Pareto —主要停機原因（Top {top_n}）{start_date} ~ {end_date}",
                "labels":     labels,
                "datasets": [
                    {
                        "type":            "bar",
                        "label":           "停機時數 (h)",
                        "data":            bar_data,
                        "yAxisID":         "y_hours",
                        "backgroundColor": "rgba(239, 68, 68, 0.6)",
                        "borderColor":     "rgba(239, 68, 68, 1)",
                    },
                    {
                        "type":        "line",
                        "label":       "累積百分比 (%)",
                        "data":        cumulative,
                        "yAxisID":     "y_pct",
                        "borderColor": "rgba(234, 179, 8, 1)",
                        "fill":        False,
                        "tension":     0.2,
                    },
                ],
                "yAxes": {
                    "y_hours": {"label": "總時數 (h)", "position": "left"},
                    "y_pct":   {"label": "累積百分比 (%)", "position": "right", "max": 100},
                },
            }

        return {
            "status":       "success",
            "period":       f"{start_date} ~ {end_date}",
            "floor":        floor or "全廠",
            "top_n":        top_n,
            "data":         clean_rows,
            "chart_config": chart_config,
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-F: Equipment fault pattern comparison across two time periods
    # Compares DOWN code distribution: period A vs period B
    # e.g. this quarter vs last quarter, 1H vs 2H
    # ══════════════════════════════════════════════════════════════════════════════
    def get_fault_pattern_comparison(
        self,
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
        period_a_label: str = "期間A",
        period_b_label: str = "期間B",
        equipment_code: str = None,
        equipment_name: str = None,
        floor: str = None,
        top_n: int = 15,
        include_chart: bool = True
    ) -> Dict[str, Any]:
        """
        EQ-F: Compare fault reason distribution between two time periods.
        Strategy: B-codes co-occurring within same second as A001/A006-A009 DOWN events,
        joined with CIM_MQTTCODEERR for fault description (NOTE).
        Returns top-N fault reasons ranked by combined occurrence count,
        with grouped bar chart (period A vs period B) and comparison table.
        """
        # Build optional topic filter based on equipment or floor scope
        topic_filter = ""
        eq_label = floor or "全廠"
        if equipment_code or equipment_name:
            safe_kw = (equipment_name or equipment_code or "").replace("'", "''")
            # Fetch display name from EQUIPMENT_INFO_DICT (prefer row with non-NULL TOPIC)
            info_q = f"""
                SELECT "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC"
                FROM "public"."EQUIPMENT_INFO_DICT"
                WHERE "EQUIPMENT_NAME" ILIKE '%{safe_kw}%'
                   OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%'
                ORDER BY CASE WHEN "TOPIC" IS NOT NULL THEN 0 ELSE 1 END
                LIMIT 1
            """
            info_rows = self._execute_postgres_query(info_q)
            if info_rows:
                eq_label = info_rows[0].get("EQUIPMENT_NAME") or info_rows[0].get("EQUIPMENT_CODE") or safe_kw
            else:
                eq_label = safe_kw
            # Multi-strategy filter: EQUIPMENT_INFO_DICT TOPIC values + EQUIPMENT_CODE as TOPIC
            # + direct ILIKE on AM_PM.TOPIC to handle format mismatches (e.g. 'DATA/4F/64008A/' vs 'Sonic_401')
            topic_filter = f"""AND (
                b."TOPIC" IN (
                    SELECT "TOPIC" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%')
                      AND "TOPIC" IS NOT NULL
                )
                OR b."TOPIC" IN (
                    SELECT "EQUIPMENT_CODE" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%')
                      AND "EQUIPMENT_CODE" IS NOT NULL
                )
                OR b."TOPIC" ILIKE '%{safe_kw}%'
            )"""
        elif floor:
            safe_floor = floor.replace("'", "''")
            topic_filter = f"""
                AND b."TOPIC" IN (
                    SELECT DISTINCT "TOPIC" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE "EQUIP_INSTALL_POSITION" ILIKE '%{safe_floor}%'
                )
            """

        def _query_fault_counts(ymd_start: str, ymd_end: str) -> Dict[str, int]:
            """Query B-code fault occurrences co-occurring within same second as DOWN events.
            Returns dict of {NOTE: count} for the given date range."""
            q = f"""
                SELECT
                    err."NOTE",
                    COUNT(*) AS cnt
                FROM "public"."CIM_MQTTCOLLECT_AM_PM" b
                JOIN "public"."CIM_MQTTCODEERR" err
                    ON b."CODE" = err."PLCCODE"
                WHERE b."CODE" LIKE 'B%'
                  AND SUBSTRING(b."DATETIMES", 1, 8) BETWEEN '{ymd_start}' AND '{ymd_end}'
                  AND LENGTH(b."DATETIMES") >= 14
                  {topic_filter}
                  AND EXISTS (
                      SELECT 1 FROM "public"."CIM_MQTTCOLLECT_AM_PM" a
                      WHERE a."TOPIC" = b."TOPIC"
                        AND a."CODE" IN ('A001','A006','A007','A008','A009')
                        AND SUBSTRING(a."DATETIMES", 1, 15) = SUBSTRING(b."DATETIMES", 1, 15)
                  )
                GROUP BY err."NOTE"
                ORDER BY cnt DESC
            """
            rows = self._execute_postgres_query(q)
            return {r["NOTE"]: int(r["cnt"]) for r in rows if r.get("NOTE")}

        a_ymd_s = period_a_start.replace('-', '')
        a_ymd_e = period_a_end.replace('-', '')
        b_ymd_s = period_b_start.replace('-', '')
        b_ymd_e = period_b_end.replace('-', '')

        counts_a = _query_fault_counts(a_ymd_s, a_ymd_e)
        counts_b = _query_fault_counts(b_ymd_s, b_ymd_e)

        # Merge all fault reasons from both periods, rank by combined count
        all_notes = sorted(
            set(counts_a) | set(counts_b),
            key=lambda n: (counts_a.get(n, 0) + counts_b.get(n, 0)),
            reverse=True
        )[:top_n]

        # Build comparison table
        comparison = []
        for note in all_notes:
            ca = counts_a.get(note, 0)
            cb = counts_b.get(note, 0)
            delta = ca - cb
            comparison.append({
                "故障原因":                note,
                f"{period_a_label}(次)":  ca,
                f"{period_b_label}(次)":  cb,
                "變化(次)":               delta,
                "趨勢":                   "⬆ 惡化" if delta > 0 else ("⬇ 改善" if delta < 0 else "─ 持平"),
            })

        # Build grouped bar chart: X = fault reason, two bars per reason (A vs B)
        chart_config = None
        if include_chart and all_notes:
            chart_config = {
                "chart_type": "bar_line_combo",
                "title":      f"故障原因分佈比對：{period_a_label} vs {period_b_label}（{eq_label}）",
                "labels":     all_notes,
                "datasets": [
                    {
                        "type":            "bar",
                        "label":           f"{period_a_label}(次)",
                        "data":            [counts_a.get(n, 0) for n in all_notes],
                        "yAxisID":         "y_count",
                        "backgroundColor": "rgba(239, 68, 68, 0.65)",
                        "borderColor":     "rgba(239, 68, 68, 1)",
                    },
                    {
                        "type":            "bar",
                        "label":           f"{period_b_label}(次)",
                        "data":            [counts_b.get(n, 0) for n in all_notes],
                        "yAxisID":         "y_count",
                        "backgroundColor": "rgba(99, 102, 241, 0.55)",
                        "borderColor":     "rgba(99, 102, 241, 1)",
                    },
                ],
                "yAxes": {
                    "y_count": {"label": "發生次數", "position": "left"},
                },
            }

        return {
            "status":         "success",
            "scope":          eq_label,
            "period_a":       f"{period_a_start} ~ {period_a_end}",
            "period_b":       f"{period_b_start} ~ {period_b_end}",
            "period_a_label": period_a_label,
            "period_b_label": period_b_label,
            "comparison":     comparison,
            "chart_config":   chart_config,
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # EQ-G: Fault reason heat map (equipment × fault_note → occurrence_count)
    # X-axis = top-N equipment by total fault occurrences
    # Y-axis = top-M fault reasons (NOTE from CIM_MQTTCODEERR)
    # Cell value = occurrence count within the period
    # ══════════════════════════════════════════════════════════════════════════════
    def get_fault_heatmap(
        self,
        start_date: str,
        end_date: str,
        floor: str = None,
        equipment_code: str = None,
        equipment_name: str = None,
        top_n_equipment: int = 8,
        top_m_notes: int = 10,
    ) -> Dict[str, Any]:
        """
        EQ-G: Build a heat map of fault reasons (NOTE) × equipment for a period.
        Can scope to a single device (equipment_code/equipment_name), a floor, or the whole factory.
        Returns chart_type='heatmap' compatible with ChartConfig.
        """
        start_ymd = start_date.replace('-', '')
        end_ymd   = end_date.replace('-', '')

        # Build scope filter: single equipment > floor > factory-wide
        scope_filter = ""
        scope_label  = floor or "全廠"
        if equipment_code or equipment_name:
            safe_kw = (equipment_name or equipment_code or "").replace("'", "''")
            # Fetch display name from EQUIPMENT_INFO_DICT (prefer row with non-NULL TOPIC)
            info_q = f"""
                SELECT "EQUIPMENT_CODE", "EQUIPMENT_NAME", "TOPIC"
                FROM "public"."EQUIPMENT_INFO_DICT"
                WHERE "EQUIPMENT_NAME" ILIKE '%{safe_kw}%'
                   OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%'
                ORDER BY CASE WHEN "TOPIC" IS NOT NULL THEN 0 ELSE 1 END
                LIMIT 1
            """
            info_rows = self._execute_postgres_query(info_q)
            if info_rows:
                scope_label = info_rows[0].get("EQUIPMENT_NAME") or info_rows[0].get("EQUIPMENT_CODE") or safe_kw
            else:
                scope_label = safe_kw
            # Multi-strategy filter: EQUIPMENT_INFO_DICT TOPIC values + EQUIPMENT_CODE as TOPIC
            # + direct ILIKE on AM_PM.TOPIC to handle format mismatches (e.g. 'DATA/4F/64008A/' vs 'Sonic_401')
            scope_filter = f"""AND (
                b."TOPIC" IN (
                    SELECT "TOPIC" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%')
                      AND "TOPIC" IS NOT NULL
                )
                OR b."TOPIC" IN (
                    SELECT "EQUIPMENT_CODE" FROM "public"."EQUIPMENT_INFO_DICT"
                    WHERE ("EQUIPMENT_NAME" ILIKE '%{safe_kw}%' OR "EQUIPMENT_CODE" ILIKE '%{safe_kw}%')
                      AND "EQUIPMENT_CODE" IS NOT NULL
                )
                OR b."TOPIC" ILIKE '%{safe_kw}%'
            )"""
            # When scoped to single equipment, expand top_m so nothing is truncated
            top_n_equipment = 1
            top_m_notes = 30
        elif floor:
            safe_floor = floor.replace("'", "''")
            scope_filter = f'AND ei."EQUIP_INSTALL_POSITION" ILIKE \'%{safe_floor}%\''

        # Join B-codes (fault reason) with co-occurring DOWN events (A001/A006-A009)
        # B-codes appear within the same second as DOWN A-codes (co-occurrence pattern confirmed)
        # No CATE filter needed - B-code CATE is mostly IDEL/IDEL1, not DOWN
        # IMPORTANT: LEFT JOIN EQUIPMENT_INFO_DICT must use deduplicated subquery (DISTINCT ON TOPIC)
        # to avoid COUNT inflation when one TOPIC has multiple rows (different GDHM versions etc.)
        query = f"""
            SELECT
                COALESCE(ei."EQUIPMENT_NAME", b."TOPIC") AS "設備名稱",
                err."NOTE"                                AS "故障原因",
                COUNT(*)                                  AS "發生次數"
            FROM "public"."CIM_MQTTCOLLECT_AM_PM" b
            JOIN "public"."CIM_MQTTCODEERR" err
                ON b."CODE" = err."PLCCODE"
            LEFT JOIN (
                SELECT DISTINCT ON ("TOPIC")
                    "TOPIC", "EQUIPMENT_NAME", "EQUIPMENT_CODE"
                FROM "public"."EQUIPMENT_INFO_DICT"
                WHERE "TOPIC" IS NOT NULL
                ORDER BY "TOPIC",
                    CASE WHEN "EQUIPMENT_NAME" IS NOT NULL THEN 0 ELSE 1 END
            ) ei ON ei."TOPIC" = b."TOPIC"
            WHERE b."CODE" LIKE 'B%'
              AND err."NOTE" IS NOT NULL
              AND SUBSTRING(b."DATETIMES", 1, 8) BETWEEN '{start_ymd}' AND '{end_ymd}'
              AND EXISTS (
                  SELECT 1 FROM "public"."CIM_MQTTCOLLECT_AM_PM" a
                  WHERE a."TOPIC" = b."TOPIC"
                    AND a."CODE" IN ('A001','A006','A007','A008','A009')
                    AND SUBSTRING(a."DATETIMES", 1, 15) = SUBSTRING(b."DATETIMES", 1, 15)
              )
              {scope_filter}
            GROUP BY
                COALESCE(ei."EQUIPMENT_NAME", b."TOPIC"),
                err."NOTE"
            ORDER BY "發生次數" DESC
        """
        rows = self._execute_postgres_query(query)
        if not rows or (len(rows) == 1 and rows[0].get("error")):
            return {
                "status":  "success",
                "period":  f"{start_date} ~ {end_date}",
                "message": "查詢期間內無符合條件的故障記錄，熱點圖無資料",
                "chart_config": None,
            }

        # ── Tally totals to pick top-N equipment and top-M notes ──────────────
        eq_totals: Dict[str, int] = {}
        note_totals: Dict[str, int] = {}
        matrix_raw: Dict[str, Dict[str, int]] = {}   # note → {equip → count}
        note_cate: Dict[str, str] = {}

        for r in rows:
            equip = r.get("設備名稱") or ""
            note  = r.get("故障原因") or ""
            cnt   = int(r.get("發生次數") or 0)
            if not equip or not note:
                continue
            eq_totals[equip]   = eq_totals.get(equip, 0) + cnt
            note_totals[note]  = note_totals.get(note, 0) + cnt
            if note not in matrix_raw:
                matrix_raw[note] = {}
            matrix_raw[note][equip] = matrix_raw[note].get(equip, 0) + cnt

        # Select top-N equipment and top-M notes
        top_equips = [
            eq for eq, _ in sorted(eq_totals.items(), key=lambda x: -x[1])[:top_n_equipment]
        ]
        top_notes = [
            n for n, _ in sorted(note_totals.items(), key=lambda x: -x[1])[:top_m_notes]
        ]

        if not top_equips or not top_notes:
            return {
                "status":  "success",
                "period":  f"{start_date} ~ {end_date}",
                "message": "該期間內無符合停機代碼的故障記錄，熱點圖無資料",
                "chart_config": None,
            }

        # ── Build datasets (one per note / row) ───────────────────────────────
        max_val = 0
        datasets = []
        for note in top_notes:
            data = [matrix_raw.get(note, {}).get(eq, 0) for eq in top_equips]
            mv = max(data)
            if mv > max_val:
                max_val = mv
            datasets.append({
                "type":  "heatmap",
                "label": note,
                "data":  data,
                "cate":  note_cate.get(note, "未分類"),
            })

        chart_config = {
            "chart_type": "heatmap",
            "title":      f"故障原因熱點圖（{scope_label}） {start_date} ~ {end_date}",
            "labels":     top_equips,           # X-axis: equipment
            "datasets":   datasets,             # Y-axis: one row per fault note
            "max_value":  max_val,
        }

        # Build a flat summary table for LLM text analysis (fault reason + count per equipment)
        summary_table = []
        for note in top_notes:
            row_entry = {"故障原因": note}
            for eq in top_equips:
                row_entry[eq] = matrix_raw.get(note, {}).get(eq, 0)
            row_entry["合計次數"] = note_totals.get(note, 0)
            summary_table.append(row_entry)

        return {
            "status":          "success",
            "period":          f"{start_date} ~ {end_date}",
            "scope":           scope_label,
            "top_n_equipment": top_n_equipment,
            "top_m_notes":     top_m_notes,
            "equipment_list":  top_equips,
            "note_list":       top_notes,
            "summary_table":   summary_table,   # flat table for LLM analysis: [{故障原因, equip_name, 合計次數}]
            "chart_config":    chart_config,
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q1: Real-time operation status for each floor / line
    # Utilization = running lines / total lines  (RUN / [RUN + DOWN])
    # "Running" = line exists in Daily_Status_Report for today
    # "Stopped" = line in Scx_base but NOT in Daily_Status_Report today
    # ──────────────────────────────────────────────────────────────────────────────
    def get_line_operation_status(self, floor: str = None, target_date: str = None) -> Dict[str, Any]:
        """
        Q1: Real-time utilization status per floor / line with GREEN / RED indicators.
        Joins Scx_base (full line master) with Daily_Status_Report (today's running lines).
        Returns per-line status and per-floor summary statistics.
        """
        # Build date filter and a safe display string for the 資料日期 column
        date_cond    = f"'{target_date}'" if target_date else "CONVERT(date, GETDATE())"
        display_date = f"'{target_date}'" if target_date else "CONVERT(VARCHAR(10), GETDATE(), 120)"
        floor_filter = f"AND s.lc = '{str(floor).replace(chr(39), chr(39)*2)}'" if floor else ""

        query = f"""
            WITH running AS (
                -- Lines that have reported production today
                SELECT CAST([NO] AS VARCHAR(50)) AS line_key,
                       SUM(ACTUAL_PRO)            AS actual_pro_sum,
                       MAX(jz)                    AS current_model
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME = {date_cond} AND [NO] IS NOT NULL
                GROUP BY [NO]
            )
            SELECT
                s.lc                                                    AS [樓層],
                s.scx_no                                                AS [產線號],
                s.scx_value                                             AS [產線名稱],
                CASE WHEN r.line_key IS NOT NULL THEN 'RUNNING' ELSE 'STOPPED' END AS [稼動狀態],
                CASE WHEN r.line_key IS NOT NULL THEN '開工'    ELSE '停工'    END AS [狀態燈],
                ISNULL(r.actual_pro_sum, 0)                             AS [今日產量],
                ISNULL(r.current_model, '')                             AS [生產機種],
                {display_date}                                          AS [資料日期]
            FROM [dbo].[Scx_base] s
            LEFT JOIN running r ON CAST(s.scx_no AS VARCHAR(50)) = r.line_key
            WHERE 1=1 {floor_filter}
            ORDER BY s.lc, s.scx_no
        """
        result = self._execute_mssql_query(query)

        # Use ASCII-only labels to prevent LLM garbling in Markdown tables
        # LLM will add 🟢/🔴 based on System Prompt instructions
        STATUS_LABEL = {'RUNNING': 'RUN', 'STOPPED': 'STOP'}
        for row in result:
            row['狀態燈'] = STATUS_LABEL.get(row.get('稼動狀態', 'STOPPED'), 'STOP')

        # Calculate per-floor summary
        floor_map: Dict[str, Dict[str, int]] = {}
        for row in result:
            lc = str(row.get('樓層', 'N/A'))
            floor_map.setdefault(lc, {'total': 0, 'running': 0})
            floor_map[lc]['total'] += 1
            if row.get('稼動狀態') == 'RUNNING':
                floor_map[lc]['running'] += 1

        floor_summary = [
            {
                '樓層': lc,
                '產線總數': v['total'],
                '開工中': v['running'],
                '停工中': v['total'] - v['running'],
                '稼動率(%)': round(v['running'] / v['total'] * 100, 1) if v['total'] > 0 else 0
            }
            for lc, v in sorted(floor_map.items())
        ]

        total = sum(v['total'] for v in floor_map.values())
        running_total = sum(v['running'] for v in floor_map.values())

        return {
            "status": "success",
            "queried_floor": floor or "全廠",
            "query_date": target_date or datetime.date.today().isoformat(),
            "overall_summary": {
                "total_lines": total,
                "running_lines": running_total,
                "stopped_lines": total - running_total,
                "utilization_rate_pct": round(running_total / total * 100, 1) if total > 0 else 0
            },
            "floor_summary": floor_summary,
            "line_detail": result if floor else [] # Only send line-by-line detail if a specific floor is selected.
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q2: Active lines and current models on a specific floor
    # ──────────────────────────────────────────────────────────────────────────────
    def get_floor_active_lines(self, floor: str, target_date: str = None) -> Dict[str, Any]:
        """
        Q2: For a specific floor, return:
          (a) Line status table (running/stopped) with current model and work order.
          (b) Model table showing which models are being produced and on which lines.
        """
        date_cond    = f"'{target_date}'" if target_date else "CONVERT(date, GETDATE())"
        display_date = f"'{target_date}'" if target_date else "CONVERT(VARCHAR(10), GETDATE(), 120)"
        safe_floor   = str(floor).replace("'", "''")

        # Table A: per-line status on this floor
        query_lines = f"""
            WITH running AS (
                SELECT CAST([NO] AS VARCHAR(50)) AS line_key,
                       MAX(jz)                   AS jz,
                       MAX(WORK_ORDER_NO)         AS wo,
                       SUM(ACTUAL_PRO)            AS actual_sum
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME = {date_cond} AND [NO] IS NOT NULL
                GROUP BY [NO]
            )
            SELECT
                s.scx_no                                               AS [產線號],
                s.scx_value                                            AS [產線名稱],
                CASE WHEN r.line_key IS NOT NULL THEN '開工' ELSE '停工' END AS [狀態燈],
                CASE WHEN r.line_key IS NOT NULL THEN 'RUNNING' ELSE 'STOPPED' END AS [稼動狀態],
                ISNULL(r.jz, '')           AS [生產機種],
                ISNULL(r.wo, '')           AS [工單號碼],
                ISNULL(r.actual_sum, 0)    AS [今日實際產量],
                {display_date}             AS [資料日期]
            FROM [dbo].[Scx_base] s
            LEFT JOIN running r ON CAST(s.scx_no AS VARCHAR(50)) = r.line_key
            WHERE s.lc = '{safe_floor}'
            ORDER BY s.scx_no
        """

        # Table B: model × line mapping (only active lines)
        query_models = f"""
            SELECT
                d.jz                          AS [機種],
                CAST(d.[NO] AS VARCHAR(50))   AS [產線號],
                d.WORK_ORDER_NO               AS [工單號碼],
                SUM(d.ACTUAL_PRO)             AS [今日實際產量],
                {display_date}                AS [資料日期]
            FROM [dbo].[Daily_Status_Report] d
            INNER JOIN [dbo].[Scx_base] s
                ON CAST(s.scx_no AS VARCHAR(50)) = CAST(d.[NO] AS VARCHAR(50))
            WHERE d.PRO_TIME = {date_cond}
              AND s.lc = '{safe_floor}'
              AND d.[NO] IS NOT NULL
            GROUP BY d.jz, d.[NO], d.WORK_ORDER_NO
            ORDER BY d.jz, d.[NO]
        """

        lines_result  = self._execute_mssql_query(query_lines)
        models_result = self._execute_mssql_query(query_models)

        # Use ASCII-only labels to prevent LLM garbling in Markdown tables
        # LLM will add 🟢/🔴 based on System Prompt instructions
        STATUS_LABEL = {'RUNNING': 'RUN', 'STOPPED': 'STOP'}
        for row in lines_result:
            row['狀態燈'] = STATUS_LABEL.get(row.get('稼動狀態', 'STOPPED'), 'STOP')

        running = sum(1 for r in lines_result if r.get('稼動狀態') == 'RUNNING')
        total   = len(lines_result)

        return {
            "status": "success",
            "floor": floor,
            "query_date": target_date or datetime.date.today().isoformat(),
            "running_count": running,
            "total_lines": total,
            "utilization_rate_pct": round(running / total * 100, 1) if total > 0 else 0,
            "line_status_table": lines_result,     # Table with green/red per line
            "active_model_table": models_result    # Table: line → model mapping
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q3: Work orders lagging behind schedule (ACHIEVING_RATE < threshold)
    # Based on: SELECT jz, ACHIEVING_RATE FROM Daily_Status_Report GROUP BY ...
    # ──────────────────────────────────────────────────────────────────────────────
    def get_lagging_workorders(
        self, target_date: str = None, threshold: float = 1.0, limit: int = 50
    ) -> Dict[str, Any]:
        """
        Q3: Identify work orders falling behind schedule on each production line.
        Filters for ACHIEVING_RATE < threshold (default 1.0 = 100% target).
        Returns: work order, production line, model, achieving rate, severity.
        Sorted worst-first (ascending ACHIEVING_RATE).
        """
        date_cond    = f"'{target_date}'" if target_date else "CONVERT(date, GETDATE())"
        display_date = f"'{target_date}'" if target_date else "CONVERT(VARCHAR(10), GETDATE(), 120)"

        query = f"""
            SELECT TOP {limit}
                [NO]                          AS [產線],
                jz                            AS [機種],
                WORK_ORDER_NO                 AS [工單號碼],
                SUM(WORK_ORDER_NUM)           AS [工單目標數],
                SUM(ACTUAL_PRO)               AS [今日實際產量],
                ROUND(AVG(ACHIEVING_RATE), 4) AS [達成率],
                CASE
                    WHEN AVG(ACHIEVING_RATE) < 0.7  THEN '嚴重落後'
                    WHEN AVG(ACHIEVING_RATE) < 0.9  THEN '輕微落後'
                    ELSE                                  '接近達標'
                END                           AS [落後嚴重度_raw],
                {display_date}                AS [資料日期]
            FROM [dbo].[Daily_Status_Report]
            WHERE PRO_TIME = {date_cond}
              AND [NO] IS NOT NULL
              AND ACHIEVING_RATE < {threshold}
            GROUP BY [NO], jz, WORK_ORDER_NO
            ORDER BY AVG(ACHIEVING_RATE) ASC
        """
        result = self._execute_mssql_query(query)

        # Use short ASCII-safe severity labels to prevent LLM garbling in Markdown tables
        SEVERITY_MAP = {
            '嚴重落後': 'CRITICAL',
            '輕微落後': 'MILD',
            '接近達標': 'NEAR',
        }
        for row in result:
            raw = row.pop('落後嚴重度_raw', '嚴重落後')
            row['落後嚴重度'] = SEVERITY_MAP.get(raw, 'CRITICAL')

        return {
            "status": "success",
            "query_date": target_date or datetime.date.today().isoformat(),
            "threshold_achieving_rate": threshold,
            "lagging_count": len(result),
            "metadata_warning": (
                f"All listed work orders have ACHIEVING_RATE < {threshold} (below 100% target). "
                "Sorted worst-first. Critical < 70%, Mild < 90%."
            ),
            "data": result
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q4: Production lines with high defect rates today / recent N days
    # ──────────────────────────────────────────────────────────────────────────────
    def get_high_defect_lines(
        self, target_date: str = None, lookback_days: int = 1, limit: int = 15
    ) -> Dict[str, Any]:
        """
        Q4: Rank production lines by defect rate (NG_NUM / ACTUAL_PRO).
        lookback_days=1: today only.  lookback_days>1: rolling N-day window.
        Returns top-N lines sorted by defect rate descending.
        Only includes lines with ACTUAL_PRO > 0 (has production records).
        """
        if not target_date:
            target_date = datetime.date.today().isoformat()

        if lookback_days > 1:
            display_date_val = f"CONVERT(VARCHAR, DATEADD(day, -{lookback_days - 1}, '{target_date}'), 120) + ' ~ ' + '{target_date}'"
            time_cond = (
                f"PRO_TIME >= DATEADD(day, -{lookback_days - 1}, '{target_date}') "
                f"AND PRO_TIME <= '{target_date}'"
            )
        else:
            display_date_val = f"'{target_date}'"
            time_cond = f"PRO_TIME = '{target_date}'"

        query = f"""
            SELECT TOP {limit}
                [NO]                    AS [產線],
                jz                      AS [機種],
                SUM(ACTUAL_PRO)         AS [總產量],
                SUM(NG_NUM)             AS [總不良數],
                CASE
                    WHEN SUM(ACTUAL_PRO) = 0 THEN 0
                    ELSE ROUND(
                            CAST(SUM(NG_NUM) AS FLOAT) / NULLIF(SUM(ACTUAL_PRO), 0) * 100, 4)
                END                     AS [不良率百分比],
                {display_date_val}      AS [資料日期]
            FROM [dbo].[Daily_Status_Report]
            WHERE {time_cond}
              AND [NO] IS NOT NULL
              AND ACTUAL_PRO > 0
            GROUP BY [NO], jz
            ORDER BY [不良率百分比] DESC
        """
        result = self._execute_mssql_query(query)

        # Build range string for JSON return metadata
        range_label = target_date
        if lookback_days > 1:
            try:
                start_dt = datetime.datetime.strptime(target_date, '%Y-%m-%d') - datetime.timedelta(days=lookback_days-1)
                range_label = f"{start_dt.date().isoformat()} ~ {target_date}"
            except:
                pass

        return {
            "status": "success",
            "query_range": range_label,
            "lookback_days": lookback_days,
            "limit": limit,
            "metadata_warning": (
                f"Lines sorted by defect rate (highest first). Top {limit} shown. "
                "High defect rate lines may require immediate process review."
            ),
            "data": result
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q5: Production quantity + defect rate time-series with chart config
    # Supports: daily / weekly / monthly / quarterly / yearly granularity
    # ──────────────────────────────────────────────────────────────────────────────
    def get_production_trend_data(
        self,
        start_date: str,
        end_date: str,
        line_no: str = None,
        model: str = None,
        granularity: str = 'monthly'
    ) -> Dict[str, Any]:
        """
        Q5: Time-series trend of production quantity and defect rate.
        Returns:
          - 'data':         raw rows for table display
          - 'chart_config': Recharts / Chart.js compatible JSON
                            (Bar = quantity, Line = defect rate, dual Y-axis)
        granularity options: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'
        """
        # Build optional column filters
        extra_filters = []
        if line_no:
            extra_filters.append(f"CAST([NO] AS VARCHAR(50)) = '{str(line_no).replace(chr(39), chr(39)*2)}'")
        if model:
            extra_filters.append(f"jz = '{str(model).replace(chr(39), chr(39)*2)}'")
        extra_where = ("AND " + " AND ".join(extra_filters)) if extra_filters else ""

        # Map granularity to SQL time-label expression
        granularity_map = {
            'daily':       "CONVERT(VARCHAR(10), PRO_TIME, 120)",
            'weekly':      (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-W' + "
                "RIGHT('0' + CAST(DATEPART(WEEK, PRO_TIME) AS VARCHAR), 2)"
            ),
            'monthly':     "CONVERT(VARCHAR(7), PRO_TIME, 120)",
            'quarterly':   (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-Q' + "
                "CAST(DATEPART(QUARTER, PRO_TIME) AS VARCHAR)"
            ),
            'half_yearly': (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-' + "
                "CASE WHEN MONTH(PRO_TIME) <= 6 THEN '1H' ELSE '2H' END"
            ),
            'yearly':      "CAST(YEAR(PRO_TIME) AS VARCHAR)",
        }
        time_expr = granularity_map.get(granularity, granularity_map['monthly'])

        # Use CTE so GROUP BY can reference the label expression safely
        query = f"""
            WITH base AS (
                SELECT
                    {time_expr}   AS period_label,
                    ACTUAL_PRO,
                    NG_NUM
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME BETWEEN '{start_date}' AND '{end_date}'
                  AND [NO] IS NOT NULL
                  {extra_where}
            )
            SELECT
                period_label          AS [時間標籤],
                SUM(ACTUAL_PRO)       AS [總產量],
                SUM(NG_NUM)           AS [總不良數],
                ROUND(
                    CAST(SUM(NG_NUM) AS FLOAT) / NULLIF(SUM(ACTUAL_PRO), 0) * 100,
                    4
                )                     AS [不良率百分比]
            FROM base
            GROUP BY period_label
            ORDER BY period_label
        """
        result = self._execute_mssql_query(query)

        # Build chart-ready config (Recharts dual-axis: Bar + Line)
        labels    = [r.get('時間標籤', '')     for r in result]
        bar_data  = [r.get('總產量', 0)        for r in result]
        line_data = [r.get('不良率百分比', 0)  for r in result]

        chart_config = {
            "chart_type": "bar_line_combo",
            "title": f"Production Trend ({granularity})"
                     + (f" | Line {line_no}" if line_no else "")
                     + (f" | Model {model}"   if model   else ""),
            "labels": labels,
            "datasets": [
                {
                    "type":            "bar",
                    "label":           "總產量 (units)",
                    "data":            bar_data,
                    "yAxisID":         "y_quantity",
                    "backgroundColor": "rgba(54, 162, 235, 0.6)",
                    "borderColor":     "rgba(54, 162, 235, 1)",
                },
                {
                    "type":        "line",
                    "label":       "不良率 (%)",
                    "data":        line_data,
                    "yAxisID":     "y_defect_rate",
                    "borderColor": "rgba(255, 99, 132, 1)",
                    "fill":        False,
                    "tension":     0.3,
                }
            ],
            "yAxes": {
                "y_quantity":    {"label": "產量 (units)", "position": "left"},
                "y_defect_rate": {"label": "不良率 (%)",   "position": "right"}
            }
        }

        return {
            "status":      "success",
            "start_date":  start_date,
            "end_date":    end_date,
            "granularity": granularity,
            "line_no":     line_no,
            "model":       model,
            "data":        result,          # table rows for LLM text response
            "chart_config": chart_config    # JSON for frontend chart rendering
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q6: Check if a specific work order is behind schedule (Y / N)
    # ──────────────────────────────────────────────────────────────────────────────
    def get_workorder_progress_check(
        self, work_order_no: str, target_date: str = None
    ) -> Dict[str, Any]:
        """
        Q6: Check a single work order's progress.
        Returns Y/N behind-schedule flag with severity and production recommendations.
        """
        date_filter = f"AND PRO_TIME = '{target_date}'" if target_date else ""
        safe_wo     = str(work_order_no).replace("'", "''")

        query = f"""
            SELECT
                [NO]                          AS [產線],
                jz                            AS [機種],
                WORK_ORDER_NO                 AS [工單號碼],
                SUM(WORK_ORDER_NUM)           AS [工單目標數],
                SUM(ACTUAL_PRO)               AS [累積實際產量],
                ROUND(AVG(ACHIEVING_RATE), 4) AS [平均達成率],
                MAX(PRO_TIME)                 AS [最新更新日期],
                CASE
                    WHEN AVG(ACHIEVING_RATE) >= 1.0 THEN 'On track'
                    WHEN AVG(ACHIEVING_RATE) >= 0.8 THEN 'Mildly behind'
                    ELSE                                 'Severely behind'
                END                           AS [進度狀態_raw]
            FROM [dbo].[Daily_Status_Report]
            WHERE WORK_ORDER_NO = '{safe_wo}'
              AND [NO] IS NOT NULL
              {date_filter}
            GROUP BY [NO], jz, WORK_ORDER_NO
        """
        result = self._execute_mssql_query(query)

        # Use ASCII-only labels to prevent LLM garbling in Markdown tables
        # LLM will add 🟢/🟡/🔴 based on System Prompt instructions
        STATUS_MAP = {
            'On track':       'ON_TRACK',
            'Mildly behind':  'MILD_BEHIND',
            'Severely behind':'SEVERE_BEHIND',
        }
        for row in result:
            raw = row.pop('進度狀態_raw', 'Severely behind')
            row['是否落後'] = STATUS_MAP.get(raw, 'SEVERE_BEHIND')

        # Derive overall verdict and recommendation
        is_behind = "UNKNOWN"
        recommendation = "No data found for this work order. Please verify the work order number."

        if result and "error" not in result[0]:
            avg_rate = float(result[0].get('平均達成率') or 0)
            if avg_rate >= 1.0:
                is_behind = "N"
                recommendation = (
                    "Work order is on track (achieving rate ≥ 100%). "
                    "No corrective action required."
                )
            elif avg_rate >= 0.8:
                is_behind = "Y (Mild)"
                recommendation = (
                    f"Achieving rate is {round(avg_rate * 100, 1)}% — slightly below target. "
                    "Recommended actions: (1) Review shift productivity, "
                    "(2) Consider limited overtime to recover output gap."
                )
            else:
                is_behind = "Y (Severe)"
                recommendation = (
                    f"Achieving rate is only {round(avg_rate * 100, 1)}% — significantly below target. "
                    "Immediate actions recommended: "
                    "(1) Identify root cause (material shortage / equipment fault / manpower gap), "
                    "(2) Reallocate personnel or raw materials, "
                    "(3) Evaluate splitting the order to parallel production lines, "
                    "(4) Escalate to production manager for expedite decision."
                )

        return {
            "status":              "success",
            "work_order_no":       work_order_no,
            "is_behind_schedule":  is_behind,
            "recommendation":      recommendation,
            "data":                result
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q7: Models with largest defect rate fluctuation across periods
    # Supports: monthly / quarterly / yearly
    # ──────────────────────────────────────────────────────────────────────────────
    def get_defect_rate_fluctuation_data(
        self,
        end_date: str = None,
        granularity: str = 'quarterly',
        periods: int = 4,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Q7: Rank models by defect rate fluctuation (MAX − MIN across time periods).
        Returns:
          - 'fluctuation_ranking': sorted by volatility descending (table)
          - 'trend_data':          raw time-series rows per model
          - 'chart_config':        multi-line chart JSON (one line per model)
        """
        if not end_date:
            end_date = datetime.date.today().isoformat()

        # Determine look-back window and time label SQL
        days_per_period = {
            'daily':       1,
            'weekly':      7,
            'monthly':     30,
            'quarterly':   90,
            'half_yearly': 182,
            'yearly':      365,
        }
        days       = days_per_period.get(granularity, 90) * periods
        start_date = (
            datetime.date.fromisoformat(end_date) - datetime.timedelta(days=days)
        ).isoformat()

        granularity_map = {
            'daily':       "CONVERT(VARCHAR(10), PRO_TIME, 120)",
            'weekly':      (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-W' + "
                "RIGHT('0' + CAST(DATEPART(WEEK, PRO_TIME) AS VARCHAR), 2)"
            ),
            'monthly':     "CONVERT(VARCHAR(7), PRO_TIME, 120)",
            'quarterly':   (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-Q' + "
                "CAST(DATEPART(QUARTER, PRO_TIME) AS VARCHAR)"
            ),
            'half_yearly': (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-' + "
                "CASE WHEN MONTH(PRO_TIME) <= 6 THEN '1H' ELSE '2H' END"
            ),
            'yearly':      "CAST(YEAR(PRO_TIME) AS VARCHAR)",
        }
        time_expr = granularity_map.get(granularity, granularity_map['quarterly'])

        # Step 1: time-series defect rate per model
        query_trend = f"""
            WITH base AS (
                SELECT
                    jz,
                    {time_expr} AS period_label,
                    ACTUAL_PRO,
                    NG_NUM
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME BETWEEN '{start_date}' AND '{end_date}'
                  AND [NO] IS NOT NULL
                  AND jz IS NOT NULL
            ),
            agg AS (
                SELECT
                    jz             AS [機種],
                    period_label   AS [時間標籤],
                    SUM(ACTUAL_PRO)  AS [總產量],
                    SUM(NG_NUM)      AS [總不良數],
                    ROUND(
                        CAST(SUM(NG_NUM) AS FLOAT) /
                        NULLIF(SUM(ACTUAL_PRO), 0) * 100, 4
                    ) AS [不良率百分比]
                FROM base
                GROUP BY jz, period_label
            )
            SELECT * FROM agg ORDER BY [機種], [時間標籤]
        """

        # Step 2: fluctuation ranking (MAX − MIN per model)
        query_fluctuation = f"""
            WITH base AS (
                SELECT
                    jz,
                    {time_expr} AS period_label,
                    ROUND(
                        CAST(SUM(NG_NUM) AS FLOAT) /
                        NULLIF(SUM(ACTUAL_PRO), 0) * 100, 4
                    ) AS defect_rate_pct
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME BETWEEN '{start_date}' AND '{end_date}'
                  AND [NO] IS NOT NULL
                  AND jz IS NOT NULL
                GROUP BY jz, {time_expr}
            )
            SELECT TOP {limit}
                jz                                              AS [機種],
                MIN(defect_rate_pct)                            AS [最低不良率(%)],
                MAX(defect_rate_pct)                            AS [最高不良率(%)],
                ROUND(MAX(defect_rate_pct) - MIN(defect_rate_pct), 4) AS [波動幅度(百分點)],
                COUNT(DISTINCT period_label)                    AS [統計期數]
            FROM base
            GROUP BY jz
            ORDER BY [波動幅度(百分點)] DESC
        """

        trend_result       = self._execute_mssql_query(query_trend)
        fluctuation_result = self._execute_mssql_query(query_fluctuation)

        # Step A: build per-model time-series lookup from trend data
        model_map: Dict[str, Dict[str, float]] = {}
        period_set: List[str] = []
        for row in trend_result:
            m = str(row.get('機種', ''))
            p = str(row.get('時間標籤', ''))
            rate = float(row.get('不良率百分比') or 0)
            model_map.setdefault(m, {})[p] = rate
            if p not in period_set:
                period_set.append(p)
        period_set.sort()

        # Step B: build fluctuation ranking map from SQL result
        fluctuation_map: Dict[str, float] = {}
        for row in fluctuation_result:
            m = str(row.get('機種', ''))
            fluctuation_map[m] = float(row.get('波動幅度(百分點)') or 0)

        # Step C: sort by fluctuation desc, take top N for chart
        top_models = sorted(
            [m for m in model_map.keys() if m in fluctuation_map],
            key=lambda m: fluctuation_map.get(m, 0),
            reverse=True
        )[:limit]

        # Truncate long model names for legend readability (max 14 chars)
        def short_label(name: str) -> str:
            return name if len(name) <= 14 else name[:13] + '\u2026'

        palette = [
            'rgba(255,99,132,1)',   'rgba(54,162,235,1)',
            'rgba(255,206,86,1)',   'rgba(75,192,192,1)',
            'rgba(153,102,255,1)',  'rgba(255,159,64,1)',
            'rgba(199,199,199,1)',  'rgba(83,102,255,1)',
            'rgba(255,130,100,1)', 'rgba(0,200,150,1)',
        ]
        granularity_zh = {
            'daily':       '每日',
            'weekly':      '每週',
            'monthly':     '月對月',
            'quarterly':   '季對季',
            'half_yearly': '半年對半年(1H/2H)',
            'yearly':      '年對年',
        }
        title_zh = f"\u5404\u6a5f\u7a2e\u4e0d\u826f\u7387\u6ce2\u52d5\u5c0d\u6bd4\uff08{granularity_zh.get(granularity, granularity)}\uff09"

        # Step D: build per-model quantity map
        qty_map: Dict[str, Dict[str, float]] = {}
        for row in trend_result:
            m   = str(row.get('\u6a5f\u7a2e', ''))
            p   = str(row.get('\u6642\u9593\u6a19\u7c64', ''))
            qty = float(row.get('\u7e3d\u7522\u91cf') or 0)
            qty_map.setdefault(m, {})[p] = qty

        # Step E: build paired bar (qty) + line (defect rate) datasets per model
        # Same colour shared between bar and line of the same model for visual clarity
        datasets: List[Dict] = []
        for i, model in enumerate(top_models):
            color = palette[i % len(palette)]
            lbl   = short_label(model)
            
            # Bar: quantity (left Y-axis) - HIDE from legend to prevent redundancy
            datasets.append({
                "type":            "bar",
                "label":           f"{lbl} \u7522\u91cf",
                "data":            [qty_map.get(model, {}).get(p, 0) for p in period_set],
                "yAxisID":         "y_quantity",
                "backgroundColor": color.replace(",1)", ",0.30)"),
                "borderColor":     color,
                "hideInLegend":    True    # New: hide from bottom legend list
            })
            
            # Line: defect rate (right Y-axis) - ONLY this shows in legend
            datasets.append({
                "type":        "line",
                "label":       lbl,        # Simpler label
                "data":        [model_map[model].get(p) for p in period_set],
                "yAxisID":     "y_defect_rate",
                "borderColor": color,
                "fill":        False,
                "tension":     0.3,
            })

        chart_config = {
            "chart_type": "bar_line_combo",
            "title":      title_zh,
            "labels":     period_set,
            "datasets":   datasets,
            "yAxes": {
                "y_quantity":    {"label": "\u5404\u6a5f\u7a2e\u7522\u91cf (units)", "position": "left"},
                "y_defect_rate": {"label": "\u4e0d\u826f\u7387 (%)",         "position": "right"},
            }
        }

        return {
            "status":               "success",
            "start_date":           start_date,
            "end_date":             end_date,
            "granularity":          granularity,
            "fluctuation_ranking":  fluctuation_result,   # table: model → volatility
            "trend_data":           trend_result,          # raw time-series
            "chart_config":         chart_config           # JSON for frontend chart
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Q8: Defect quantity trend (dual-line chart) + top defect cause ranking
    # Source A: Daily_Status_Report → NG_NUM + REJECT_RATE time-series
    # Source B: blpjl_new (live view) → bllt defect type ranking + date concentration
    # ──────────────────────────────────────────────────────────────────────────────
    def get_defect_cause_analysis(
        self,
        start_date: str = None,
        end_date: str = None,
        line_no: str = None,
        model: str = None,
        granularity: str = 'daily',
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Q8: Defect quantity trend + top-N defect cause ranking with date concentration.
        At least one of line_no or model must be provided.
        Returns:
          - 'trend_data':    time-series rows for table display
          - 'chart_config':  dual Y-axis line chart JSON (left=NG_NUM, right=REJECT_RATE%)
          - 'cause_ranking': top-N defect causes with date concentration flag
        """
        # Default date range: last 30 days
        if not end_date:
            end_date = datetime.date.today().isoformat()
        if not start_date:
            start_date = (
                datetime.date.fromisoformat(end_date) - datetime.timedelta(days=30)
            ).isoformat()

        # Build WHERE filters (at least one of line_no / model expected)
        # NOTE: blpjl_new only has [NO], PRO_TIME, bllt, blsl — no jz column.
        # So model/work-order filters must be resolved to [NO] values via Daily_Status_Report first.
        import re as _re

        def _line_or_wo_filter(val: str) -> str:
            """
            Return a WHERE fragment for Daily_Status_Report that handles:
            - Pure digits          -> [NO] = '302'
            - Work order (has '-') -> WORK_ORDER_NO = '9RT94135-1T'
            - Line name            -> [NO] IN (SELECT scx_no FROM Scx_base WHERE ...)
            """
            safe = str(val).replace("'", "''")
            if safe.strip().isdigit():
                return f"CAST([NO] AS VARCHAR(50)) = '{safe}'"
            if '-' in safe:
                # Likely a work order number — match WORK_ORDER_NO directly
                return f"WORK_ORDER_NO = '{safe}'"
            # Line name — look up via Scx_base
            return (
                f"CAST([NO] AS VARCHAR(50)) IN ("
                f"SELECT CAST(scx_no AS VARCHAR(50)) FROM [dbo].[Scx_base] "
                f"WHERE scx_value LIKE '%{safe}%')"
            )

        filters: List[str] = [f"PRO_TIME BETWEEN '{start_date}' AND '{end_date}'"]
        if line_no:
            filters.append(_line_or_wo_filter(line_no))
        if model:
            safe_model = str(model).replace("'", "''")
            filters.append(f"jz = '{safe_model}'")

        where_dsr = " AND ".join(filters)

        # ── Resolve actual [NO] values for blpjl_new filter ──────────────────
        # blpjl_new has no jz/WORK_ORDER_NO column, so we resolve [NO] from DSR first.
        no_resolve_q = f"""
            SELECT DISTINCT CAST([NO] AS VARCHAR(50)) AS [LINE_NO]
            FROM [dbo].[Daily_Status_Report]
            WHERE {where_dsr} AND [NO] IS NOT NULL
        """
        no_rows = self._execute_mssql_query(no_resolve_q)
        if no_rows and not (len(no_rows) == 1 and no_rows[0].get("error")):
            no_values = [str(r["LINE_NO"]) for r in no_rows if r.get("LINE_NO")]
            if no_values:
                no_in = ", ".join(f"'{v}'" for v in no_values)
                where_bl = f"PRO_TIME BETWEEN '{start_date}' AND '{end_date}' AND CAST([NO] AS VARCHAR(50)) IN ({no_in})"
            else:
                where_bl = f"PRO_TIME BETWEEN '{start_date}' AND '{end_date}' AND 1=0"
        else:
            # Fallback: apply line filter only (model/work-order can't be applied to blpjl_new)
            bl_parts: List[str] = [f"PRO_TIME BETWEEN '{start_date}' AND '{end_date}'"]
            if line_no and '-' not in str(line_no):
                bl_parts.append(self._build_line_filter(line_no))
            where_bl = " AND ".join(bl_parts)

        # Granularity time label for trend grouping
        granularity_map = {
            'daily':   "CONVERT(VARCHAR(10), PRO_TIME, 120)",
            'weekly':  (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-W' + "
                "RIGHT('0' + CAST(DATEPART(WEEK, PRO_TIME) AS VARCHAR), 2)"
            ),
            'monthly': "CONVERT(VARCHAR(7), PRO_TIME, 120)",
        }
        time_expr = granularity_map.get(granularity, granularity_map['daily'])

        # ── Query A: Defect quantity & rate trend ──────────────────────────────
        query_trend = f"""
            WITH base AS (
                SELECT
                    {time_expr}   AS period_label,
                    NG_NUM,
                    ACTUAL_PRO,
                    REJECT_RATE
                FROM [dbo].[Daily_Status_Report]
                WHERE {where_dsr}
                  AND [NO] IS NOT NULL
            )
            SELECT
                period_label                                AS [時間標籤],
                SUM(NG_NUM)                                 AS [不良數量],
                ROUND(
                    CAST(SUM(NG_NUM) AS FLOAT) /
                    NULLIF(SUM(ACTUAL_PRO), 0) * 100, 4
                )                                           AS [不良率(%)],
                ROUND(AVG(REJECT_RATE) * 100, 4)            AS [REJECT_RATE平均(%)]
            FROM base
            GROUP BY period_label
            ORDER BY period_label
        """

        # ── Query B: Top-N defect causes from blpjl_new (live view) ─────────────
        query_cause = f"""
            SELECT TOP {top_n}
                bllt                            AS [不良型態],
                SUM(blsl)                       AS [不良數量],
                COUNT(DISTINCT PRO_TIME)        AS [發生天數]
            FROM [dbo].[blpjl_new] WITH (NOLOCK)
            WHERE {where_bl}
              AND bllt IS NOT NULL
              AND bllt <> ''
            GROUP BY bllt
            ORDER BY [不良數量] DESC
        """

        trend_result = self._execute_mssql_query(query_trend)
        cause_result = self._execute_mssql_query(query_cause)

        # ── Date concentration analysis (Python-side) ──────────────────────────
        try:
            total_days = (
                datetime.date.fromisoformat(end_date) -
                datetime.date.fromisoformat(start_date)
            ).days + 1
        except Exception:
            total_days = 30

        for row in cause_result:
            appeared = int(row.get('發生天數') or 0)
            conc_pct = round(appeared / total_days * 100, 1) if total_days > 0 else 0
            row['集中度(%)'] = conc_pct
            row['集中性標示'] = (
                '⚠️ 集中發生'  if conc_pct < 30
                else '📊 分散發生' if conc_pct < 70
                else '🔴 持續發生'
            )

        # ── Chart config: dual Y-axis line chart ──────────────────────────────
        labels     = [r.get('時間標籤', '')   for r in trend_result]
        ng_data    = [r.get('不良數量', 0)    for r in trend_result]
        rate_data  = [r.get('不良率(%)', 0)  for r in trend_result]

        scope_label = ""
        if line_no and model:
            scope_label = f"產線 {line_no} × {model}"
        elif line_no:
            scope_label = f"產線 {line_no}"
        elif model:
            scope_label = f"機種 {model}"

        chart_config = {
            "chart_type": "bar_line_combo",
            "title":      f"不良數量與不良率趨勢 ({granularity}) | {scope_label}",
            "labels":     labels,
            "datasets": [
                {
                    "type":            "bar",
                    "label":           "不良數量",
                    "data":            ng_data,
                    "yAxisID":         "y_ng_count",
                    "backgroundColor": "rgba(255, 99, 132, 0.65)",
                    "borderColor":     "rgba(255, 99, 132, 1)",
                },
                {
                    "type":        "line",
                    "label":       "不良率 (%)",
                    "data":        rate_data,
                    "yAxisID":     "y_defect_rate",
                    "borderColor": "rgba(54, 162, 235, 1)",
                    "fill":        False,
                    "tension":     0.3,
                }
            ],
            "yAxes": {
                "y_ng_count":    {"label": "不良數量 (件)", "position": "left"},
                "y_defect_rate": {"label": "不良率 (%)",   "position": "right"},
            }
        }

        return {
            "status":        "success",
            "start_date":    start_date,
            "end_date":      end_date,
            "granularity":   granularity,
            "line_no":       line_no,
            "model":         model,
            "top_n":         top_n,
            "trend_data":    trend_result,    # for LLM text table
            "cause_ranking": cause_result,    # top-N defect types with concentration
            "chart_config":  chart_config     # dual-line JSON for frontend
        }

    def _execute_postgres_query(self, query: str) -> List[Dict[str, Any]]:
        try:
            conn = psycopg2.connect(host=POSTGRES_CONFIG['host'], port=POSTGRES_CONFIG['port'],
                                    user=POSTGRES_CONFIG['user'], password=POSTGRES_CONFIG['password'], dbname=POSTGRES_CONFIG['database'])
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            print(f"\n[PG Execute]\n{query}\n", flush=True)
            cursor.execute(query)
            result = cursor.fetchall()
            conn.close()
            print(f"[PG Result] {len(result)} rows", flush=True)
            return [_sanitize(dict(row)) for row in result]
        except Exception as e:
            print(f"[PG ERROR] {e}\nQuery was:\n{query}", flush=True)
            return [{"error": str(e)}]
