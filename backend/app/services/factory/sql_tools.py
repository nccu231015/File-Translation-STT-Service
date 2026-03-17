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
        try:
            conn = pymssql.connect(
                server=MSSQL_CONFIG['server'],
                user=MSSQL_CONFIG['user'],
                password=MSSQL_CONFIG['password'],
                database=MSSQL_CONFIG['database'],
                timeout=5
            )
            conn.close()
            results["mssql"] = "ok"
        except Exception:
            results["mssql"] = "failed"
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
        取得產線開工總覽。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"SELECT [jz], [WORK_ORDER_NO] FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        rows = self._execute_mssql_query(query)
        working_count = len(rows)
        work_orders = list(set([r['WORK_ORDER_NO'] for r in rows if r.get('WORK_ORDER_NO')]))
        models = list(set([r['jz'] for r in rows if r.get('jz')]))
        return {"status": "success", "working_lines_count": working_count, "active_work_orders": work_orders, "active_models": models}

    def get_detailed_production_report(self, target_date: str = None) -> Dict[str, Any]:
        """
        獲取詳細生產紀錄報表。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            SELECT jz AS Machine_Model, WORK_ORDER_NO AS Work_Order, WORK_ORDER_NUM AS Target_Qty, 
                   ACTUAL_PRO AS Actual_Qty, BAD_PRO_RATE AS Defect_Rate 
            FROM [dbo].[Daily_Status_Report] WHERE {date_cond} ORDER BY jz
        """
        report_res = self._execute_mssql_query(query)
        return {"status": "success", "report_data": report_res}

    def get_defect_pareto_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        不良品統計趨勢與 Pareto 分析（含排除條件）。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            WITH src AS (
                SELECT
                    a.jcgx AS [檢查工序], a.ljfl AS [零件分類], a.bllt AS [不良型態], a.blwz AS [不良位置],
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
                       [零件分類] + ' / ' + [不良型態] AS [分類_型態],
                       SUM([不良品數量]) OVER () AS [總計],
                       ROUND(1.0 * [不良品數量] / NULLIF(SUM([不良品數量]) OVER (), 0), 2) AS [個別佔比],
                       ROW_NUMBER() OVER (ORDER BY [不良品數量] DESC) AS [列序號],
                       CAST([不良品數量] AS DECIMAL(18,6)) / NULLIF(SUM([不良品數量]) OVER (), 0) AS ratio
                FROM src
            )
            SELECT [列序號], [檢查工序], [分類_型態],
                   CAST([列序號] AS varchar(3)) + ' ' + [不良位置] AS [位置_備註],
                   [不良品數量], [個別佔比], '不良品紀錄' jllb,
                   ROUND(SUM(ratio) OVER (ORDER BY [不良品數量] DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS [累積百分比]
            FROM calc ORDER BY [不良品數量] DESC
        """
        res = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "pareto_data": res}

    def get_downtime_cause_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        停機時間統計與原因分析（含排除條件）。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            WITH base AS (
                SELECT DISTINCT 
                    a.tjlb AS [停機類別], a.zrdw AS [責任單位], a.tjxz AS [停機細項],
                    SUM(a.tjsj) OVER() AS [總停機時間],
                    SUM(a.tjsj) OVER (PARTITION BY a.tjlb, a.zrdw, a.tjxz) AS [停機時間],
                    CAST(SUM(a.tjsj) OVER (PARTITION BY a.tjlb, a.zrdw, a.tjxz) AS float) / 
                    NULLIF(CAST(SUM(a.tjsj) OVER() AS float), 0) AS [個別占比]
                FROM [dbo].[tjsjjl_new_copy1] a
                WHERE tjsj > 0 AND gdhm = '{work_order}' AND {date_cond}
                AND NOT (
                    (a.tjlb='不良品分析(分)' AND zrdw='製造' AND tjxz='「備註」載明：分析多少pcs')
                    OR (a.tjlb='值日生' AND zrdw='製造' AND tjxz='「備註」載明：姓名&幾人')
                )
            ),
            answer AS (
                SELECT *, ROW_NUMBER() OVER(ORDER BY [停機時間] DESC) AS t_row FROM base 
            )
            SELECT *, SUM([個別占比]) OVER (ORDER BY t_row) AS [累積占比]
            FROM answer ORDER BY [停機時間] DESC
        """
        res = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "downtime_cause": res}

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
