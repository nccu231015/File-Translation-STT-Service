import pymssql
import psycopg2
import psycopg2.extras
from typing import Dict, Any, List
from .db_config import MSSQL_CONFIG, POSTGRES_CONFIG
from decimal import Decimal
import datetime

from .sql_pg_queries import (
    _get_query_1_production_status,
    _get_query_2_failure_trend,
    _get_query_3_downtime_stats
)

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
        return []


    def get_workorder_quantity(self, target_date: str = None) -> Dict[str, Any]:
        """
        4. 工單的生產數量
        5. 現在的生產數量?
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        q_target = f"SELECT [WORK_ORDER_NO], sum(WORK_ORDER_NUM) WORK_ORDER_NUM FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY [WORK_ORDER_NO]"
        q_actual = f"SELECT [WORK_ORDER_NO], sum(ACTUAL_PRO) ACTUAL_PRO FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY [WORK_ORDER_NO]"
        
        target_res = self._execute_mssql_query(q_target)
        actual_res = self._execute_mssql_query(q_actual)
        
        # 在工具層合併兩組數據，避免傳給 LLM 的字元數過大
        actual_map = {r["WORK_ORDER_NO"]: r.get("ACTUAL_PRO", 0) for r in actual_res if "WORK_ORDER_NO" in r}
        
        rows = []
        for r in target_res:
            wo = r.get("WORK_ORDER_NO", "")
            target = r.get("WORK_ORDER_NUM", 0)
            actual = actual_map.get(wo, 0)
            rows.append(f"| {wo} | {target} | {actual} |")
        
        table = "| 工單號碼 | 目標數量 | 實際產量 |\n|---|---|---|\n" + "\n".join(rows)
        
        return {
            "status": "success",
            "summary": f"共 {len(rows)} 筆工單",
            "table": table
        }
    def get_kpi_ranking(self, kpi_type: str = 'top_achieving', target_date: str = None, lookback_days: int = 1, limit: int = 10) -> Dict[str, Any]:
        """
        獲取績效排行 (如: 達成率、不良率、停機)。
        支援動態限制數量 (limit) 與多日聚合。
        """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
            
        # 決定時間條件
        if lookback_days > 1:
            time_cond = f"PRO_TIME >= DATEADD(day, -{lookback_days-1}, '{target_date}') AND PRO_TIME <= '{target_date}'"
        else:
            time_cond = f"PRO_TIME = '{target_date}'"

        configs = {
            "top_achieving": {"col": "ACHIEVING_RATE", "order": "DESC", "label": "達成率", "agg": "AVG"},
            "lagging": {"col": "ACHIEVING_RATE", "order": "ASC", "label": "達成率(落後)", "agg": "AVG"},
            "abnormal": {"col": "BAD_PRO_RATE", "order": "DESC", "label": "不良數量", "agg": "SUM"},
            "downtime": {"col": "LOST_TIME_PRO_RATE", "order": "DESC", "label": "損失工時(總分)", "agg": "SUM"},
            "unachieved": {"col": "ACHIEVING_RATE", "order": "ASC", "label": "達成率", "agg": "AVG"},
        }
        
        c = configs.get(kpi_type, configs["top_achieving"])
        sql_col = c["col"]
        sql_order = c["order"]
        label = c["label"]
        agg_func = c["agg"]
        
        if kpi_type == "abnormal":
            query = f"""
                SELECT 
                TOP {limit}
                jz, sum(BAD_PRO_RATE) as blsl
                FROM [dbo].[Daily_Status_Report] 
                WHERE {time_cond} AND BAD_PRO_RATE > 0
                GROUP BY jz, BAD_PRO_RATE
                ORDER BY BAD_PRO_RATE DESC
            """
        else:
            query = f"""
                SELECT TOP {limit}
                    jz as [機種],
                    [NO] as [產線],
                    [WORK_ORDER_NO] as [工單],
                    {agg_func}({sql_col}) as [KPI數值]
                FROM [dbo].[Daily_Status_Report]
                WHERE {time_cond} AND [NO] IS NOT NULL
                GROUP BY jz, [NO], [WORK_ORDER_NO]
                ORDER BY [KPI數值] {sql_order}
            """
            
        result = self._execute_mssql_query(query)

        # 建立強制性的工具回報警告，防止較小的 LLM 出現資料幻覺
        warning_msg = (
            f"【系統強制警告】：1. 以下資料僅為排行前 {limit} 名的數據，絕不可宣稱全廠只有 {limit} 條產線。"
            " 2. 若此為『達成率』排行，工廠達標標準為 1.0 (100%)。"
        )
        
        return {
            "status": "success", 
            "kpi_target": label, 
            "lookback_days": lookback_days, 
            "limit": limit,
            "metadata_warning": warning_msg,
            "data": result
        }

    def get_line_defect_records(self, target_date: str = None) -> Dict[str, Any]:
        """
        產線/樓層-生產的數量、不良數 (包含工單)
        使用 blpjl_new_copy1
        """
        date_cond = f"a.PRO_TIME='{target_date}'" if target_date else "a.PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            SELECT a.* FROM [dbo].[blpjl_new_copy1] a 
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined' AND {date_cond}
            ORDER BY [NO], sjd ASC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "data": result}

    def get_line_downtime_records(self, target_date: str = None) -> Dict[str, Any]:
        """
        產線/樓層-生產的數量、停機時間 (包含工單)
        使用 tjsjjl_new_copy1
        """
        date_cond = f"a.PRO_TIME='{target_date}'" if target_date else "a.PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            SELECT * FROM [dbo].[tjsjjl_new_copy1] a
            WHERE tjsj > 0 AND (bz is not null or tjsj is not null) AND gdhm <> 'undefined'
            AND {date_cond}
            ORDER BY [NO], sjd ASC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "data": result}

    def get_defect_pareto_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        不良品統計、趨勢分析 (Pareto)
        使用 blpjl_new_copy1 與完整排除邏輯
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
        WITH src AS (
            SELECT
                a.jcgx [檢查工序],
                a.ljfl [零件分類],
                a.bllt [不良型態],
                a.blwz [不良位置],
                SUM(a.blsl) AS [不良品數量]
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0
            AND NOT( 
                jcgx ='設備判定 (CCD/成測)' and ljfl ='成品' 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (jcgx ='設備判定 (CCD/成測)' and ljfl ='成品' and bllt is null)
                or (ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            AND gdhm = '{work_order}'
            AND {date_cond}
            GROUP BY jcgx, ljfl, bllt, blwz
        ),
        calc AS (
            SELECT DISTINCT *, 
                零件分類+' / '+不良型態 AS [分類_型態],
                SUM(不良品數量) OVER () AS [總計],
                ROUND(1.0 * 不良品數量 / NULLIF(SUM(不良品數量) OVER (), 0), 2) AS [個別佔比],
                ROW_NUMBER() OVER (ORDER BY 不良品數量 DESC) AS [列序號],
                CAST(不良品數量 AS DECIMAL(18,6)) / NULLIF(SUM(不良品數量) OVER (), 0) AS ratio
            FROM src
        )
        SELECT
            列序號,
            檢查工序,
            分類_型態,
            CAST(列序號 AS varchar(3))+' '+ 不良位置 AS [位置_備註],
            不良品數量,
            個別佔比,
            '不良品紀錄' jllb,
            ROUND(
                SUM(ratio) OVER (ORDER BY 不良品數量 DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2 
            ) AS [累積百分比]
        FROM calc
        ORDER BY 不良品數量 DESC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "data": result}

    def get_defect_anomaly_report(self, target_date: str = None, lookback_days: int = 30, limit: int = 10) -> Dict[str, Any]:
        """
        跨日不良異常分析: 比對產線今日的不良數與過去 N 天的平均不良數。
        """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
            
        query = f"""
        WITH today AS (
            SELECT [NO] as line_no, SUM(BAD_PRO_RATE) as today_defects
            FROM [dbo].[Daily_Status_Report]
            WHERE PRO_TIME = '{target_date}' AND [NO] IS NOT NULL AND BAD_PRO_RATE > 0
            GROUP BY [NO]
        ),
        past AS (
            SELECT [NO] as line_no, SUM(BAD_PRO_RATE) as total_past_defects
            FROM [dbo].[Daily_Status_Report]
            WHERE CAST(PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE))
              AND CAST(PRO_TIME AS DATE) < CAST('{target_date}' AS DATE)
              AND [NO] IS NOT NULL AND BAD_PRO_RATE > 0
            GROUP BY [NO]
        ),
        past_avg AS (
            SELECT line_no, CAST(total_past_defects AS FLOAT) / {lookback_days} as avg_past_defects
            FROM past
        )
        SELECT TOP {limit}
            COALESCE(t.line_no, p.line_no) as [產線],
            ISNULL(t.today_defects, 0) as [今日不良總數],
            ROUND(ISNULL(p.avg_past_defects, 0), 2) as [過去平均不良數],
            CASE 
                WHEN ISNULL(p.avg_past_defects, 0) = 0 THEN NULL
                ELSE ROUND((ISNULL(t.today_defects, 0) - p.avg_past_defects) / p.avg_past_defects * 100, 2)
            END as [異常偏差百分比]
        FROM today t
        FULL OUTER JOIN past_avg p ON t.line_no = p.line_no
        ORDER BY [異常偏差百分比] DESC
        """
        result = self._execute_mssql_query(query)
        
        warning_msg = (
            f"【系統強制警告】：此資料已由高到低針對「異常偏差百分比」排序完畢，且僅顯示最極端的前 {limit} 筆產線！"
            "若使用者詢問『最高的前幾名』，絕對不可私自改用其他欄位重新排序。請確實按照 [異常偏差百分比] 數值高低回答！"
        )
        return {"status": "success", "target_date": target_date, "lookback_days": lookback_days, "limit": limit, "metadata_warning": warning_msg, "data": result}
        
    def get_defect_rate_anomaly_report(self, target_date: str = None, lookback_days: int = 7, limit: int = 10) -> Dict[str, Any]:
        """
        不良率異常分析: 讀取 Daily_Status_Report，比對產線今日不良率百分比（不良數量/總產量）與過去 N 天的平均不良率。
        """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
            
        query = f"""
        WITH lines AS (
            SELECT DISTINCT [NO] as line_no 
            FROM [dbo].[Daily_Status_Report] 
            WHERE CAST(PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE)) 
              AND CAST(PRO_TIME AS DATE) <= CAST('{target_date}' AS DATE)
              AND [NO] IS NOT NULL
        ),
        today_data AS (
            SELECT [NO] as line_no, SUM(BAD_PRO_RATE) as today_defects, SUM(ACTUAL_PRO) as today_pro
            FROM [dbo].[Daily_Status_Report]
            WHERE PRO_TIME = '{target_date}' AND [NO] IS NOT NULL
            GROUP BY [NO]
        ),
        past_data AS (
            SELECT [NO] as line_no, SUM(BAD_PRO_RATE) as past_total_defects, SUM(ACTUAL_PRO) as past_total_pro
            FROM [dbo].[Daily_Status_Report]
            WHERE CAST(PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE))
              AND CAST(PRO_TIME AS DATE) < CAST('{target_date}' AS DATE)
              AND [NO] IS NOT NULL
            GROUP BY [NO]
        )
        SELECT TOP {limit}
            l.line_no as [產線],
            ISNULL(t.today_defects, 0) as [今日不良總數],
            ISNULL(t.today_pro, 0) as [今日總產量],
            CASE WHEN ISNULL(t.today_pro, 0) = 0 THEN 0 ELSE ROUND(CAST(ISNULL(t.today_defects, 0) AS FLOAT) / t.today_pro * 100, 2) END as [今日不良率百分比],
            ISNULL(p.past_total_defects, 0) as [歷史不良總數],
            ISNULL(p.past_total_pro, 0) as [歷史總產量],
            CASE WHEN ISNULL(p.past_total_pro, 0) = 0 THEN 0 ELSE ROUND(CAST(ISNULL(p.past_total_defects, 0) AS FLOAT) / p.past_total_pro * 100, 2) END as [歷史平均不良率百分比],
            CASE 
                WHEN ISNULL(p.past_total_pro, 0) = 0 THEN NULL
                WHEN ISNULL(t.today_pro, 0) = 0 THEN NULL
                ELSE 
                    ROUND( 
                        (CAST(ISNULL(t.today_defects, 0) AS FLOAT) / t.today_pro * 100) - 
                        (CAST(ISNULL(p.past_total_defects, 0) AS FLOAT) / p.past_total_pro * 100), 2
                    )
            END as [不良率差值(百分點)]
        FROM lines l
        LEFT JOIN today_data t ON l.line_no = t.line_no
        LEFT JOIN past_data p ON l.line_no = p.line_no
        WHERE ISNULL(t.today_defects, 0) > 0 OR ISNULL(p.past_total_defects, 0) > 0
        ORDER BY [今日不良率百分比] DESC, [不良率差值(百分點)] DESC
        """
        result = self._execute_mssql_query(query)
        
        warning_msg = (
            f"【系統強制警告】：此資料已由高到低針對「今日不良率百分比」排序完畢，且僅顯示最極端的前 {limit} 筆產線！"
            "若使用者詢問『不良率最高的產線前幾名』，絕對不可私自改用「歷史平均不良率」重新排序。請確實按照 [今日不良率百分比] 數值高低回答！"
        )
        return {"status": "success", "target_date": target_date, "lookback_days": lookback_days, "limit": limit, "metadata_warning": warning_msg, "data": result}
        
    def get_downtime_trend_report(self, target_date: str = None, lookback_days: int = 7, limit: int = 10) -> Dict[str, Any]:
        """
        跨日「停機趨勢」分析: 回溯過去 N 天，按類別、單位統計總停機時間與占比。
        產出數據：停機類別、責任單位、總停機時間(分)、歷史占比。
        """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
            
        query = f"""
        WITH range_data AS (
            SELECT 
                a.tjlb as [停機類別], 
                a.zrdw as [責任單位], 
                SUM(a.tjsj) as [總停機時間(分)]
            FROM [dbo].[tjsjjl_new_copy1] a
            WHERE CAST(a.PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE)) 
              AND CAST(a.PRO_TIME AS DATE) <= CAST('{target_date}' AS DATE)
              AND a.tjsj > 0 AND a.gdhm <> 'undefined'
              AND NOT (
                (a.tjlb='不良品分析(分)' AND zrdw='製造' AND tjxz='「備註」載明：分析多少pcs')
                OR (a.tjlb='值日生' AND zrdw='製造' AND tjxz='「備註」載明：姓名&幾人')
              )
            GROUP BY a.tjlb, a.zrdw
        ),
        totals AS (
            SELECT SUM([總停機時間(分)]) as grand_total FROM range_data
        )
        SELECT TOP {limit}
            r.*,
            CASE WHEN t.grand_total = 0 THEN 0 ELSE ROUND(CAST(r.[總停機時間(分)] AS FLOAT) / t.grand_total * 100, 2) END as [累積占比百分比]
        FROM range_data r, totals t
        ORDER BY [總停機時間(分)] DESC
        """
        result = self._execute_mssql_query(query)
        
        warning_msg = (
            f"【系統強制警告】：此資料已由高到低針對「總停機時間」排序完畢，且僅顯示最極端的前 {limit} 筆類別！"
        )
        return {"status": "success", "target_date": target_date, "lookback_days": lookback_days, "limit": limit, "metadata_warning": warning_msg, "data": result}
        
    def get_active_equipment(self, target_date: str = None) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 當前稼動設備。 """
        if target_date:
            # YMD 欄位格式為 'YYYYMMDD'（8位數字），移除 ISO 格式中的連字符
            date_compact = target_date.replace("-", "")
            date_val = f"'{date_compact}'"
        else:
            date_val = "TO_CHAR(CURRENT_DATE, 'YYYYMMDD')"
        query = f"SELECT distinct \"TOPIC\" FROM \"public\".\"CIM_MQTTCOLLECT\" WHERE \"YMD\"={date_val} AND CAST(\"CODEVALUE\" AS NUMERIC)>0"
        return {"status": "success", "date_queried": date_val, "data": self._execute_postgres_query(query)}

    def get_equipment_location(self, keyword: str) -> Dict[str, Any]:
        """
        PostgreSQL 查詢: 根據設備名稱關鍵字模糊搜尋設備的安裝位置 (樓層)。
        例如：輸入 '成型機' 可找到所有成型機及其所在樓層。
        """
        safe_keyword = keyword.replace("'", "''")  # 防止 SQL Injection
        query = f"""
            SELECT "EQUIP_ID", "EQUIP_NAME", "EQUIP_INSTALL_POSITION", "EQUIP_TYPE"
            FROM "public"."EQUIPMENT_INFO_DICT"
            WHERE "EQUIP_NAME" ILIKE '%{safe_keyword}%'
               OR "EQUIP_TYPE" ILIKE '%{safe_keyword}%'
            ORDER BY "EQUIP_INSTALL_POSITION", "EQUIP_NAME"
        """
        result = self._execute_postgres_query(query)
        return {"status": "success", "keyword": keyword, "data": result}

    def get_equipment_by_floor(self, floor: str) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 根據安裝地點樓層獲取設備配置資料 """
        query = f"SELECT * FROM \"public\".\"EQUIPMENT_INFO_DICT\" WHERE \"EQUIP_INSTALL_POSITION\"='{floor}'"
        return {"status": "success", "floor": floor, "data": self._execute_postgres_query(query)}
        
    def get_equipment_production_status(self, target_date: str = None) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 依據日期抓取生產設備的運行狀況、總結良率等等 """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
        query = _get_query_1_production_status(target_date)
        return {"status": "success", "target_date": target_date, "data": self._execute_postgres_query(query)}

    def get_equipment_failure_trend(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 故障趨勢，依據時間範圍抓取各設備的故障次數與代碼 """
        query = _get_query_2_failure_trend(start_date, end_date)
        return {"status": "success", "start_date": start_date, "end_date": end_date, "data": self._execute_postgres_query(query)}

    def get_equipment_downtime_stats(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 停機時間深入統計 (RUN, IDEL, DOWN, SHUTDOWN, 故障次數, 產量) 等等 """
        query = _get_query_3_downtime_stats(start_date, end_date)
        return {"status": "success", "start_date": start_date, "end_date": end_date, "data": self._execute_postgres_query(query)}


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

        # Inject emoji into result rows (kept out of SQL to avoid cp950 encoding errors)
        STATUS_ICON = {'RUNNING': '🟢 開工', 'STOPPED': '🔴 停工'}
        for row in result:
            row['狀態燈'] = STATUS_ICON.get(row.get('稼動狀態', 'STOPPED'), '🔴 停工')

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

        # Inject emoji (kept out of SQL to avoid cp950 encoding errors)
        STATUS_ICON = {'RUNNING': '🟢 開工', 'STOPPED': '🔴 停工'}
        for row in lines_result:
            row['狀態燈'] = STATUS_ICON.get(row.get('稼動狀態', 'STOPPED'), '🔴 停工')

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

        # Inject emoji (kept out of SQL to avoid cp950 encoding errors)
        SEVERITY_ICON = {
            '嚴重落後': '🔴 嚴重落後 (<70%)',
            '輕微落後': '🟡 輕微落後 (<90%)',
            '接近達標': '🟡 接近達標 (<100%)',
        }
        for row in result:
            raw = row.pop('落後嚴重度_raw', '接近達標')
            row['落後嚴重度'] = SEVERITY_ICON.get(raw, raw)

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
        Q4: Rank production lines by defect rate (BAD_PRO_RATE / ACTUAL_PRO).
        lookback_days=1: today only.  lookback_days>1: rolling N-day window.
        Returns top-N lines sorted by defect rate descending.
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
                SUM(BAD_PRO_RATE)       AS [總不良數],
                CASE
                    WHEN SUM(ACTUAL_PRO) = 0 THEN 0
                    ELSE ROUND(
                            CAST(SUM(BAD_PRO_RATE) AS FLOAT) / SUM(ACTUAL_PRO) * 100, 2)
                END                     AS [不良率百分比],
                {display_date_val}      AS [資料日期]
            FROM [dbo].[Daily_Status_Report]
            WHERE {time_cond}
              AND [NO] IS NOT NULL
              AND BAD_PRO_RATE > 0
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
            'daily':     "CONVERT(VARCHAR(10), PRO_TIME, 120)",
            'weekly':    (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-W' + "
                "RIGHT('0' + CAST(DATEPART(WEEK, PRO_TIME) AS VARCHAR), 2)"
            ),
            'monthly':   "CONVERT(VARCHAR(7), PRO_TIME, 120)",
            'quarterly': (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-Q' + "
                "CAST(DATEPART(QUARTER, PRO_TIME) AS VARCHAR)"
            ),
            'yearly':    "CAST(YEAR(PRO_TIME) AS VARCHAR)",
        }
        time_expr = granularity_map.get(granularity, granularity_map['monthly'])

        # Use CTE so GROUP BY can reference the label expression safely
        query = f"""
            WITH base AS (
                SELECT
                    {time_expr}   AS period_label,
                    ACTUAL_PRO,
                    BAD_PRO_RATE
                FROM [dbo].[Daily_Status_Report]
                WHERE PRO_TIME BETWEEN '{start_date}' AND '{end_date}'
                  AND [NO] IS NOT NULL
                  {extra_where}
            )
            SELECT
                period_label          AS [時間標籤],
                SUM(ACTUAL_PRO)       AS [總產量],
                SUM(BAD_PRO_RATE)     AS [總不良數],
                ROUND(
                    CAST(SUM(BAD_PRO_RATE) AS FLOAT) / NULLIF(SUM(ACTUAL_PRO), 0) * 100,
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

        # Inject emoji into result rows (kept out of SQL to avoid cp950 encoding errors)
        STATUS_MAP = {
            'On track':       '🟢 N – On track',
            'Mildly behind':  '🟡 Y – Mildly behind',
            'Severely behind':'🔴 Y – Severely behind',
        }
        for row in result:
            raw = row.pop('進度狀態_raw', 'Severely behind')
            row['是否落後'] = STATUS_MAP.get(raw, raw)

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
        days_per_period = {'monthly': 30, 'quarterly': 90, 'yearly': 365}
        days            = days_per_period.get(granularity, 90) * periods
        start_date      = (
            datetime.date.fromisoformat(end_date) - datetime.timedelta(days=days)
        ).isoformat()

        granularity_map = {
            'monthly':   "CONVERT(VARCHAR(7), PRO_TIME, 120)",
            'quarterly': (
                "CAST(YEAR(PRO_TIME) AS VARCHAR) + '-Q' + "
                "CAST(DATEPART(QUARTER, PRO_TIME) AS VARCHAR)"
            ),
            'yearly':    "CAST(YEAR(PRO_TIME) AS VARCHAR)",
        }
        time_expr = granularity_map.get(granularity, granularity_map['quarterly'])

        # Step 1: time-series defect rate per model
        query_trend = f"""
            WITH base AS (
                SELECT
                    jz,
                    {time_expr} AS period_label,
                    ACTUAL_PRO,
                    BAD_PRO_RATE
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
                    SUM(BAD_PRO_RATE) AS [總不良數],
                    ROUND(
                        CAST(SUM(BAD_PRO_RATE) AS FLOAT) /
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
                        CAST(SUM(BAD_PRO_RATE) AS FLOAT) /
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
        granularity_zh = {'monthly': '\u6708\u5c0d\u6708', 'quarterly': '\u5b63\u5c0d\u5b63', 'yearly': '\u5e74\u5c0d\u5e74'}
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
            # Bar: quantity (left Y-axis)
            datasets.append({
                "type":            "bar",
                "label":           f"{lbl} \u7522\u91cf",
                "data":            [qty_map.get(model, {}).get(p, 0) for p in period_set],
                "yAxisID":         "y_quantity",
                "backgroundColor": color.replace(",1)", ",0.30)"),
                "borderColor":     color,
            })
            # Line: defect rate (right Y-axis)
            datasets.append({
                "type":        "line",
                "label":       f"{lbl} \u4e0d\u826f\u7387",
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

    def _execute_postgres_query(self, query: str) -> List[Dict[str, Any]]:
        try:
            conn = psycopg2.connect(host=POSTGRES_CONFIG['host'], port=POSTGRES_CONFIG['port'],
                                    user=POSTGRES_CONFIG['user'], password=POSTGRES_CONFIG['password'], dbname=POSTGRES_CONFIG['database'])
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query)
            result = cursor.fetchall()
            conn.close()
            return [_sanitize(dict(row)) for row in result]
        except Exception:
            return []
