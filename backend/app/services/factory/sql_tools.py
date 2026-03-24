import pymssql
import psycopg2
import psycopg2.extras
from typing import Dict, Any, List
from .db_config import MSSQL_CONFIG, POSTGRES_CONFIG
from decimal import Decimal
import datetime

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
                    login_timeout=10
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

    def get_kpi_ranking(self, kpi_type: str, target_date: str = None) -> Dict[str, Any]:
        """
        6. 進度達標前10台
        7. 進度落後前10台
        8. 異常數量?
        9. 停機時間?
        10. 達成率?
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        if kpi_type == 'top_achieving':
            # 進度達標前10台
            query = f"SELECT top 10 jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE DESC"
        elif kpi_type == 'lagging':
            # 進度落後前10台
            query = f"SELECT top 10 jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE ASC"
        elif kpi_type == 'abnormal':
            # 異常數量比例排行
            query = f"SELECT top 10 jz, sum(BAD_PRO_RATE) as BLSL FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND BAD_PRO_RATE > 0 GROUP BY jz ORDER BY BLSL DESC"
        elif kpi_type == 'downtime':
            # 停機時間比例排行
            query = f"SELECT top 10 jz, sum(LOST_TIME_PRO_RATE) as LOST_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND LOST_TIME_PRO_RATE > 0 GROUP BY jz ORDER BY LOST_RATE DESC"
        elif kpi_type == 'unachieved':
            # 達成率不足 0.5 的台數 (作為補充)
            query = f"SELECT jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND ACHIEVING_RATE < 0.5 GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE ASC"
        else:
            return {"status": "error", "message": "Unknown kpi_type"}
            
        result = self._execute_mssql_query(query)
        return {"status": "success", "kpi_type": kpi_type, "data": result}

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
                a.jcgx [檢查工序], a.ljfl [零件分類], a.bllt [不良型態], a.blwz [不良位置],
                SUM(a.blsl) AS [不良品數量]
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0
            AND NOT( 
                (jcgx ='設備判定 (CCD/成測)' and ljfl ='成品') 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (jcgx ='設備判定 (CCD/成測)' and ljfl ='成品' and bllt is null)
                or (ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            AND gdhm = '{work_order}' AND {date_cond}
            GROUP BY jcgx, ljfl, bllt, blwz
        ),
        calc AS (
            SELECT DISTINCT *, 
                零件分類 + ' / ' + 不良型態 AS [分類_型態],
                SUM(不良品數量) OVER () AS [總計],
                ROUND(1.0 * 不良品數量 / NULLIF(SUM(不良品數量) OVER (), 0), 2) AS [個別佔比],
                ROW_NUMBER() OVER (ORDER BY 不良品數量 DESC) AS [列序號],
                CAST(不良品數量 AS DECIMAL(18,6)) / NULLIF(SUM(不良品數量) OVER (), 0) AS ratio
            FROM src
        )
        SELECT 列序號, 檢查工序, 分類_型態,
            CAST(列序號 AS varchar(3)) + ' ' + 不良位置 AS [位置_備註],
            不良品數量, 個別佔比, '不良品紀錄' jllb,
            ROUND(SUM(ratio) OVER (ORDER BY 不良品數量 DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS [累積百分比]
        FROM calc ORDER BY 不良品數量 DESC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "data": result}

    def get_downtime_cause_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        停機時間統計與原因分析 (對齊專家範例)
        使用 tjsjjl_new_copy1
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
        WITH base AS (
            SELECT DISTINCT 
                a.tjlb as [停機類別], a.zrdw as [責任單位], a.tjxz as [停機細項],
                count(*) OVER (PARTITION by a.tjlb, a.zrdw, a.tjxz) as [分組項次],
                SUM(a.tjsj) OVER() as [總停機時間],
                SUM(a.tjsj) OVER (PARTITION by a.tjlb, a.zrdw, a.tjxz) as [停機時間],
                CAST(SUM(a.tjsj) OVER (PARTITION by a.tjlb, a.zrdw, a.tjxz) AS float) / 
                NULLIF(CAST(SUM(a.tjsj) OVER() AS float), 0) as [個別占比]
            FROM [dbo].[tjsjjl_new_copy1] a
            WHERE 1=1 AND gdhm='{work_order}' AND {date_cond} AND tjsj > 0
            AND NOT (
                (a.tjlb='不良品分析(分)' AND zrdw='製造' AND tjxz='「備註」載明：分析多少pcs')
                OR (a.tjlb='值日生' AND zrdw='製造' AND tjxz='「備註」載明：姓名&幾人')
            )
        ),
        answer AS (
            SELECT *, ROW_NUMBER() OVER(ORDER BY [停機時間] DESC) as t_row FROM base 
        )
        SELECT *, SUM(個別占比) OVER (ORDER BY t_row) as [累積占比]
        FROM answer ORDER BY 停機時間 DESC
        """
        res = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "data": res}

    def get_defect_anomaly_report(self, target_date: str = None, lookback_days: int = 30) -> Dict[str, Any]:
        """
        跨日不良異常分析: 比對產線今日的不良數與過去 N 天的平均不良數。
        """
        import datetime
        if not target_date:
            target_date = datetime.date.today().isoformat()
            
        query = f"""
        WITH today AS (
            SELECT [NO] as line_no, SUM(blsl) as today_defects
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined' AND a.PRO_TIME = '{target_date}'
            AND NOT( 
                (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品') 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品' and a.bllt is null)
                or (a.ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            GROUP BY [NO]
        ),
        past AS (
            SELECT [NO] as line_no, SUM(blsl) as total_past_defects
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined' 
              AND CAST(a.PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE))
              AND CAST(a.PRO_TIME AS DATE) < CAST('{target_date}' AS DATE)
            AND NOT( 
                (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品') 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品' and a.bllt is null)
                or (a.ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            GROUP BY [NO]
        ),
        past_avg AS (
            SELECT line_no, CAST(total_past_defects AS FLOAT) / {lookback_days} as avg_past_defects
            FROM past
        )
        SELECT 
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
        return {"status": "success", "target_date": target_date, "lookback_days": lookback_days, "data": result}
        
    def get_defect_rate_anomaly_report(self, target_date: str = None, lookback_days: int = 7) -> Dict[str, Any]:
        """
        不良率異常分析: 跨表聯集 Daily_Status_Report(產出) 與 blpjl_new_copy1(不良)，計算跨日真實不良率。
        解決只看「數量」而忽視「產量基數」造成的偏差。
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
        today_defects AS (
            SELECT [NO] as line_no, SUM(blsl) as total_defects
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined' AND a.PRO_TIME = '{target_date}'
            AND NOT( 
                (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品') 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品' and a.bllt is null)
                or (a.ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            GROUP BY [NO]
        ),
        today_production AS (
            SELECT [NO] as line_no, SUM(ACTUAL_PRO) as total_pro
            FROM [dbo].[Daily_Status_Report]
            WHERE PRO_TIME = '{target_date}'
            GROUP BY [NO]
        ),
        past_defects AS (
            SELECT [NO] as line_no, SUM(blsl) as past_total_defects
            FROM [dbo].[blpjl_new_copy1] a
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined' 
              AND CAST(a.PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE))
              AND CAST(a.PRO_TIME AS DATE) < CAST('{target_date}' AS DATE)
            AND NOT( 
                (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品') 
                or (a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (a.jcgx ='設備判定 (CCD/成測)' and a.ljfl ='成品' and a.bllt is null)
                or (a.ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            GROUP BY [NO]
        ),
        past_production AS (
            SELECT [NO] as line_no, SUM(ACTUAL_PRO) as past_total_pro
            FROM [dbo].[Daily_Status_Report]
            WHERE CAST(PRO_TIME AS DATE) >= DATEADD(day, -{lookback_days}, CAST('{target_date}' AS DATE))
              AND CAST(PRO_TIME AS DATE) < CAST('{target_date}' AS DATE)
            GROUP BY [NO]
        )
        SELECT 
            l.line_no as [產線],
            ISNULL(td.total_defects, 0) as [今日不良總數],
            ISNULL(tp.total_pro, 0) as [今日總產量],
            CASE WHEN ISNULL(tp.total_pro, 0) = 0 THEN 0 ELSE ROUND(CAST(ISNULL(td.total_defects, 0) AS FLOAT) / tp.total_pro * 100, 2) END as [今日不良率],
            ISNULL(pd.past_total_defects, 0) as [歷史不良總數],
            ISNULL(pp.past_total_pro, 0) as [歷史總產量],
            CASE WHEN ISNULL(pp.past_total_pro, 0) = 0 THEN 0 ELSE ROUND(CAST(ISNULL(pd.past_total_defects, 0) AS FLOAT) / pp.past_total_pro * 100, 2) END as [歷史平均不良率],
            CASE 
                WHEN ISNULL(pp.past_total_pro, 0) = 0 THEN NULL
                WHEN ISNULL(tp.total_pro, 0) = 0 THEN NULL
                ELSE 
                    ROUND( 
                        (CAST(ISNULL(td.total_defects, 0) AS FLOAT) / tp.total_pro * 100) - 
                        (CAST(ISNULL(pd.past_total_defects, 0) AS FLOAT) / pp.past_total_pro * 100), 2
                    )
            END as [不良率差值(百分點)]
        FROM lines l
        LEFT JOIN today_defects td ON l.line_no = td.line_no
        LEFT JOIN today_production tp ON l.line_no = tp.line_no
        LEFT JOIN past_defects pd ON l.line_no = pd.line_no
        LEFT JOIN past_production pp ON l.line_no = pp.line_no
        WHERE ISNULL(td.total_defects, 0) > 0 OR ISNULL(pd.past_total_defects, 0) > 0
        ORDER BY [今日不良率] DESC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "target_date": target_date, "lookback_days": lookback_days, "data": result}
        
    def get_active_equipment(self, target_date: str = None) -> Dict[str, Any]:
        """ PostgreSQL 查詢: 當前稼動設備。 """
        date_val = f"'{target_date}'" if target_date else "TO_CHAR(CURRENT_DATE, 'YYYYMMDD')"
        query = f"SELECT distinct \"TOPIC\" FROM \"public\".\"CIM_MQTTCOLLECT\" WHERE \"YMD\"={date_val} AND CAST(\"CODEVALUE\" AS NUMERIC)>0"
        return {"status": "success", "data": self._execute_postgres_query(query)}

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
