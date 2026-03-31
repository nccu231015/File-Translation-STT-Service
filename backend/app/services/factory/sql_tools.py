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

    def get_production_overview(self, target_date: str = None) -> Dict[str, Any]:
        """
        1. 今日多少條產線有開工?
        2. 正在生產的工單號碼
        3. 正在生產的機種?
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        q_count = f"SELECT count(NO) kgcx FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        q_orders = f"SELECT distinct [WORK_ORDER_NO] FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        q_models = f"SELECT distinct jz FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        
        count_res = self._execute_mssql_query(q_count)
        orders_res = self._execute_mssql_query(q_orders)
        models_res = self._execute_mssql_query(q_models)
        
        return {
            "status": "success",
            "working_lines_count": count_res[0].get("kgcx", 0) if count_res and "error" not in count_res[0] else 0,
            "active_work_orders": [r.get("WORK_ORDER_NO") for r in orders_res if r.get("WORK_ORDER_NO")],
            "active_models": [r.get("jz") for r in models_res if r.get("jz")]
        }

    def get_production_line_count(self, floor: str = None) -> Dict[str, Any]:
        """
        查詢各樓層共有多少條產線。
        Scx_base 表欄位: scx_no=產線號, scx_value=詳細產線, lc=樓層
        - floor 為 None：回傳全廠依樓層分佈統計
        - floor 有値（如 '1'）：只回傳該樓層的產線數
        """
        if floor:
            safe_floor = str(floor).replace("'", "''")
            query = f"""
                SELECT [lc] AS [樓層], count([scx_value]) AS [產線數量]
                FROM [dbo].[Scx_base]
                WHERE [lc] = '{safe_floor}'
                GROUP BY [lc]
            """
            result = self._execute_mssql_query(query)
            count = result[0].get("產線數量", 0) if result and "error" not in result[0] else 0
            return {
                "status": "success",
                "queried_floor": floor,
                "line_count": count,
                "data": result
            }

        total_query = "SELECT count([scx_value]) AS [總產線數] FROM [dbo].[Scx_base]"
        total_result = self._execute_mssql_query(total_query)
        total = total_result[0].get("總產線數", 0) if total_result and "error" not in total_result[0] else 0

        floor_query = """
            SELECT [lc] AS [樓層], count([scx_value]) AS [產線數量]
            FROM [dbo].[Scx_base]
            GROUP BY [lc]
            ORDER BY [lc]
        """
        breakdown = self._execute_mssql_query(floor_query)
        return {
            "status": "success",
            "total_lines": total,
            "breakdown_by_floor": breakdown
        }

    def get_production_line_location(self, line_no: str) -> Dict[str, Any]:
        """
        查詢特定產線號碼屬於哪個樓層。
        Scx_base: scx_no=產線號, scx_value=詳細產線名稱, lc=樓層
        """
        safe_no = str(line_no).replace("'", "''")  # 防止 SQL injection
        query = f"""
            SELECT [scx_no] AS [產線號], [scx_value] AS [詳細產線], [lc] AS [樓層], [remark] AS [備註]
            FROM [dbo].[Scx_base]
            WHERE CAST([scx_no] AS VARCHAR) LIKE '%{safe_no}%'
               OR [scx_value] LIKE '%{safe_no}%'
            ORDER BY [lc], [scx_no]
        """
        result = self._execute_mssql_query(query)
        return {
            "status": "success",
            "query_keyword": line_no,
            "data": result
        }

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
