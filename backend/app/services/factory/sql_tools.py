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
    - decimal.Decimal -> float
    - datetime.date / datetime.datetime -> ISO string
    - bytes -> decoded string
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
        """
        [Health Check] Verify connectivity to MSSQL and PostgreSQL.
        Returns a dict with status of each DB.
        """
        results = {"mssql": "failed", "postgres": "failed"}
        
        # Test MSSQL
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
        except Exception as e:
            results["mssql"] = f"error: {e}"

        # Test PostgreSQL
        try:
            conn = psycopg2.connect(
                host=POSTGRES_CONFIG['host'],
                port=POSTGRES_CONFIG['port'],
                user=POSTGRES_CONFIG['user'],
                password=POSTGRES_CONFIG['password'],
                dbname=POSTGRES_CONFIG['database'],
                connect_timeout=5
            )
            conn.close()
            results["postgres"] = "ok"
        except Exception as e:
            results["postgres"] = f"error: {e}"

        return results

    def _execute_mssql_query(self, query: str) -> List[Dict[str, Any]]:
        """
        執行 MSSQL 查詢並返回字典列表。
        """
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
                print(f"[MSSQL Result] Fetched {len(result)} rows.", flush=True)
                conn.close()
                return [_sanitize(dict(row)) for row in result]
            except Exception as e:
                print(f"[SQL Attempt {attempt+1}] Query failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1) # Wait before retry
                    continue
                return [{"error": str(e)}]
        return []

    def get_production_overview(self, target_date: str = None) -> Dict[str, Any]:
        """
        取得產線開工總覽 (使用 tjsjjl_new_copy1 統計表)。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        # 查詢有開工的機種與工單清單 (gdhm 為工單號碼)
        query = f"SELECT DISTINCT jz, gdhm FROM [dbo].[tjsjjl_new_copy1] WHERE {date_cond} AND jz IS NOT NULL"
        rows = self._execute_mssql_query(query)
        
        working_lines_count = len(rows)
        work_orders = list(set([r['gdhm'] for r in rows if r.get('gdhm')]))
        models = list(set([r['jz'] for r in rows if r.get('jz')]))
        
        return {
            "status": "success",
            "date": target_date or "today",
            "working_lines_count": working_lines_count,
            "active_work_orders": work_orders,
            "active_models": models
        }

    def get_abnormal_details(self, target_date: str = None, top_n: int = 10) -> Dict[str, Any]:
        """
        查詢特定日期內，不良原因的具體分佈 (使用 blpjl_new_copy1 表)。
        可用於回答：具體是哪些異常比例高？
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        # 查詢各機種在前幾名的不良原因與數量
        query = f"""
            SELECT TOP {top_n} 
                jz AS Machine_Model, 
                blxm AS Abnormal_Item, 
                sum(blsl) as Abnormal_Count
            FROM [dbo].[blpjl_new_copy1]
            WHERE {date_cond} AND blsl > 0
            GROUP BY jz, blxm
            ORDER BY sum(blsl) DESC
        """
        
        details_res = self._execute_mssql_query(query)
        
        return {
            "status": "success",
            "date": target_date or "today",
            "abnormal_details": details_res
        }

    # ==========================================
    # A. 產線資訊工具 (ReportDB - MSSQL)
    # ==========================================

    def get_production_overview(self, target_date: str = None) -> Dict[str, Any]:
        """
        獲取指定日期的產線開工總覽：
        - 多少條產線有開工
        - 正在生產的工單號碼
        - 正在生產的機種
        若無提供日期則預設為今日 (GETDATE())。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        q_count = f"SELECT count(NO) kgcx FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        q_orders = f"SELECT distinct [WORK_ORDER_NO] FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
        q_models = f"SELECT distinct jz FROM [dbo].[Daily_Status_Report] WHERE {date_cond}"
    def get_kpi_ranking(self, kpi_type: str, target_date: str = None) -> Dict[str, Any]:
        """
        獲取產線設備的績效排行 (KPI Ranking)。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        if kpi_type == "top_achieving":
            table = "[dbo].[Daily_Status_Report]"
            order_by_col = "sum(ACTUAL_PRO)"
            order_dir = "DESC"
        elif kpi_type == "lagging":
            table = "[dbo].[Daily_Status_Report]"
            order_by_col = "sum(ACTUAL_PRO)"
            order_dir = "ASC"
        elif kpi_type == "abnormal":
            table = "[dbo].[Daily_Status_Report]"
            order_by_col = "sum(BAD_PRO_RATE)"
            order_dir = "DESC"
        elif kpi_type == "downtime":
            # 使用專用的停機時間統計視圖
            table = "[dbo].[tjsjjl_new_copy1]"
            # 假設視圖中停機時間欄位為 tjsc 或包含此數值，此處維持 sum(CAST(DOWN_TIME AS FLOAT)) 若欄位名不變
            order_by_col = "sum(tjsj)" # Changed to tjsj based on tjsjjl_new structure
            order_dir = "DESC"
        else:
            table = "[dbo].[Daily_Status_Report]"
            order_by_col = "sum(ACTUAL_PRO)"
            order_dir = "DESC"
            
        query = f"""
            SELECT TOP 10 
                jz AS Machine_Model, 
                sum(WORK_ORDER_NUM) as Target_Qty, 
                sum(ACTUAL_PRO) as Actual_Qty,
                sum(BAD_PRO_RATE) as Bad_Rate_Total,
                sum(CAST(DOWN_TIME AS FLOAT)) as Total_Downtime_Mins
            FROM {table}
            WHERE {date_cond} AND jz IS NOT NULL
            GROUP BY jz 
            ORDER BY {order_by_col} {order_dir}
        """
        
        ranking_res = self._execute_mssql_query(query)
        
        return {
            "status": "success",
            "kpi_type": kpi_type,
            "ranking_data": ranking_res
        }

    def get_workorder_quantity(self, target_date: str = None) -> Dict[str, Any]:
        """
        獲取指定日期的工單生產數量與實際生產數量：
        - 工單目標生產數量 (WORK_ORDER_NUM)
        - 現在實際生產數量 (ACTUAL_PRO)
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        q_target = f"SELECT [WORK_ORDER_NO], sum(WORK_ORDER_NUM) WORK_ORDER_NUM FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY [WORK_ORDER_NO]"
        q_actual = f"SELECT [WORK_ORDER_NO], sum(ACTUAL_PRO) ACTUAL_PRO FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY [WORK_ORDER_NO]"
        
        target_res = self._execute_mssql_query(q_target)
        actual_res = self._execute_mssql_query(q_actual)
        
        return {
            "status": "success",
            "target_quantities": target_res,
            "actual_quantities": actual_res
        }

    def get_kpi_ranking(self, kpi_type: str, target_date: str = None) -> Dict[str, Any]:
        """
        獲取產線設備 KPI 排名：
        kpi_type 必須為以下之一：
        - 'top_achieving' : 進度達標前10台
        - 'lagging' : 進度落後前10台
        - 'abnormal' : 異常數量(比例高)前10台
        - 'downtime' : 停機時間(異常)前10台
        - 'unachieved' : 達成率未達標(<0.5)設備列表
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        
        if kpi_type == 'top_achieving':
            query = f"SELECT top 10 jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE DESC"
        elif kpi_type == 'lagging':
            query = f"SELECT top 10 jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND ACHIEVING_RATE<1 GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE ASC"
        elif kpi_type == 'abnormal':
            query = f"SELECT top 10 jz, sum(BAD_PRO_RATE) blsl FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND BAD_PRO_RATE>0 GROUP BY jz, BAD_PRO_RATE ORDER BY BAD_PRO_RATE DESC"
        elif kpi_type == 'downtime':
            query = f"SELECT top 10 jz, LOST_TIME_PRO_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND LOST_TIME_PRO_RATE>0 GROUP BY jz, LOST_TIME_PRO_RATE ORDER BY LOST_TIME_PRO_RATE DESC"
        elif kpi_type == 'unachieved':
            query = f"SELECT jz, ACHIEVING_RATE FROM [dbo].[Daily_Status_Report] WHERE {date_cond} AND ACHIEVING_RATE<0.5 GROUP BY jz, ACHIEVING_RATE ORDER BY ACHIEVING_RATE ASC"
        else:
            return {"status": "error", "message": f"未知的 kpi_type: {kpi_type}"}
            
        result = self._execute_mssql_query(query)
        return {"status": "success", "kpi_type": kpi_type, "data": result}

    def get_line_defect_records(self, target_date: str = None) -> Dict[str, Any]:
        """
        獲取特定日期的產線不良品詳細紀錄 (從 blpjl_new 視圖)。
        """
        date_cond = f"a.PRO_TIME='{target_date}'" if target_date else "a.PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            SELECT a.* 
            FROM blpjl_new a
            WHERE a.blsl > 0 AND a.gdhm <> 'undefined'
            AND {date_cond}
            ORDER BY [NO], sjd ASC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "data": result}

    def get_line_downtime_records(self, target_date: str = None) -> Dict[str, Any]:
        """
        獲取特定日期的產線停機詳細紀錄 (從 tjsjjl_new 視圖)。
        """
        date_cond = f"a.PRO_TIME='{target_date}'" if target_date else "a.PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
            SELECT *
            FROM tjsjjl_new a
            WHERE tjsj > 0 AND (bz IS NOT NULL OR tjsj IS NOT NULL) AND gdhm <> 'undefined'
            AND {date_cond}
            ORDER BY [NO], sjd ASC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "data": result}

    def get_defect_pareto_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        針對特定工單與日期進行不良品統計與趨勢分析 (Pareto)。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
        WITH src AS (
            SELECT
                a.jcgx as [檢查工序], a.ljfl as [零件分類], a.bllt as [不良型態], a.blwz as [不良位置],
                SUM(a.blsl) AS [不良品數量]
            FROM blpjl_new a
            WHERE a.blsl > 0
            AND NOT( 
                jcgx ='設備判定 (CCD/成測)' and ljfl ='成品' 
                or ( a.jcgx='分析 (設備判定異常品)' AND a.ljfl ='重測/復判後OK數量') 
                or (jcgx ='設備判定 (CCD/成測)' and ljfl ='成品' and bllt is null)
                or ( ljfl in('重測/復判後OK數量','其他復判後OK數量'))
            )
            AND gdhm = '{work_order}'
            AND {date_cond}
            GROUP BY jcgx, ljfl, bllt, blwz
        ),
        calc AS (
            SELECT DISTINCT 
                *, 
                零件分類 + ' / ' + 不良型態 AS [分類_型態],
                SUM(不良品數量) OVER () AS [總計],
                ROUND(1.0 * 不良品數量 / NULLIF(SUM(不良品數量) OVER (), 0), 2) AS [個別佔比],
                ROW_NUMBER() OVER (ORDER BY 不良品數量 DESC) AS [列序號],
                CAST(不良品數量 AS DECIMAL(18,6)) / NULLIF(SUM(不良品數量) OVER (), 0) AS ratio
            FROM src
        )
        SELECT
            列序號, 檢查工序, 分類_型態,
            CAST(列序號 AS varchar(3)) + ' ' + 不良位置 AS [位置_備註],
            不良品數量, 個別佔比, '不良品紀錄' as jllb,
            ROUND(SUM(ratio) OVER (ORDER BY 不良品數量 DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2 ) AS [累積百分比]
        FROM calc
        ORDER BY 不良品數量 DESC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "data": result}

    def get_downtime_cause_analysis(self, work_order: str, target_date: str = None) -> Dict[str, Any]:
        """
        針對特定工單與日期進行停機時間統計與原因分析。
        """
        date_cond = f"PRO_TIME='{target_date}'" if target_date else "PRO_TIME=CONVERT(date, GETDATE())"
        query = f"""
        WITH base AS (
            SELECT DISTINCT 
                a.tjlb AS [停機類別], a.zrdw AS [責任單位], a.tjxz AS [停機細項],
                COUNT(*) OVER (PARTITION BY a.tjlb, a.zrdw, a.tjxz) AS [分組項次],
                SUM(a.tjsj) OVER() AS [總停機時間],
                SUM(a.tjsj) OVER (PARTITION BY a.tjlb, a.zrdw, a.tjxz) AS [停機時間],
                CAST(SUM(a.tjsj) OVER (PARTITION BY a.tjlb, a.zrdw, a.tjxz) AS float ) / 
                NULLIF(CAST(SUM(a.tjsj) OVER() AS FLOAT), 0) AS [個別占比]
            FROM tjsjjl_new a
            WHERE 1=1
            AND gdhm = '{work_order}'
            AND {date_cond}
            AND tjsj > 0
            AND NOT (a.tjlb='不良品分析(分)' AND zrdw='製造' AND tjxz='「備註」載明：分析多少pcs'
            OR (a.tjlb='值日生' AND zrdw='製造' AND tjxz='「備註」載明：姓名&幾人'))
        ),
        aswer AS (
            SELECT *, ROW_NUMBER() OVER(ORDER BY 停機時間 DESC) AS t_row
            FROM base 
        )
        SELECT *, SUM(個別占比) OVER (ORDER BY t_row) AS [累積占比]
        FROM aswer
        ORDER BY 停機時間 DESC
        """
        result = self._execute_mssql_query(query)
        return {"status": "success", "work_order": work_order, "data": result}


    def _execute_postgres_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        執行 PostgreSQL 查詢並返回字典列表。
        """
        try:
            conn = psycopg2.connect(
                host=POSTGRES_CONFIG['host'],
                port=POSTGRES_CONFIG['port'],
                user=POSTGRES_CONFIG['user'],
                password=POSTGRES_CONFIG['password'],
                dbname=POSTGRES_CONFIG['database']
            )
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if params:
                print(f"\n[Postgres Execute]\n{query}\nParams: {params}\n", flush=True)
                cursor.execute(query, params)
            else:
                print(f"\n[Postgres Execute]\n{query}\n", flush=True)
                cursor.execute(query)
            
            result = cursor.fetchall()
            print(f"[Postgres Result] Fetched {len(result)} rows.", flush=True)
            conn.close()
            # Convert RealDictRow to standard dict and sanitize types for JSON
            return [_sanitize(dict(row)) for row in result]
        except Exception as e:
            print(f"[Postgres Error] query failed: {e}")
            return [{"error": str(e)}]

    # ==========================================
    # B. 設備資訊工具 (PublicDB - PostgreSQL)
    # ==========================================

    def get_equipment_by_floor(self, floor: str) -> Dict[str, Any]:
        """
        1. 多少生產設備? (指定樓層)
        """
        query = f"""SELECT * FROM "EQUIPMENT_INFO_DICT" WHERE "EQUIP_INSTALL_POSITION"='{floor}'"""
        data = self._execute_postgres_query(query)
        return {"status": "success", "data": data}

    def get_active_equipment(self, target_date: str = None) -> Dict[str, Any]:
        """
        2. 有在生產的機台有哪些?
        預設查詢今日 (CURRENT_DATE)，或可指定 YYYYMMDD 日期。
        """
        date_cond = f"'{target_date}'" if target_date else "TO_CHAR(CURRENT_DATE, 'YYYYMMDD')"
        query = f"""
            SELECT distinct "TOPIC" 
            FROM "public"."CIM_MQTTCOLLECT" 
            WHERE "YMD"={date_cond} AND CAST("CODEVALUE" AS NUMERIC)>0
        """
        data = self._execute_postgres_query(query)
        return {"status": "success", "data": data}

    def get_equipment_daily_status(self, equipment_code: str, target_date_dash: str) -> Dict[str, Any]:
        """
        3. 正在生產的工單號碼/機種/稼動率/停機時間/良率?
        - equipment_code: 如 '94135B'
        - target_date_dash: 如 '2026-03-11'
        
        該邏輯封裝了複雜的 LAG 窗格函數計算時間差，LLM 呼叫不需自行撰寫。
        """
        target_date_no_dash = target_date_dash.replace('-', '') # e.g. 20260311
        
        # We replace the hardcoded '94135B', '2026-03-11' and '20260311' with parameters 
        query = f"""
        SELECT
        "A"."SBMC" "設備名稱",
        "A"."YMD" "年月日",
        "A"."LPSL" "良品數量",
        "A"."RUN" "運行時間",
        "A"."DOWN" "DOWN時間",
        "A"."IDEL" "IDEL時間",
        "A"."SHUTDOWN" "SHUTDOWN時間",
        "A"."ID" "ID",
        "A"."EQUIPMENT_NAME" "設備名稱",
        "A"."EQUIPMENT_CODE" "設備編碼",
        "A"."EQUIP_INSTALL_POSITION" "安裝地點樓層",
        "A"."EQUIP_IP" "設備IP",
        "A"."IOT_DEVICE_BRAND" "T/T",
        "A"."IOT_DEVICE_NAME" "目標產出",
        "A"."IOT_IP" "備註",
        "A"."EQUIP_PHOTO" "機台照片",
        "A"."BZCN" "標准產能",
        "A"."GDHM" "工單號碼",
        "A"."SL" "工單數量",
        "A"."MODEL" "對應模型編號",
        "A"."TOPIC" "設備顯示信息"
        , SUBSTRING("A"."YMD", 7, 2) || '號' AS "DD" 
        FROM (
            SELECT * 
            FROM (
                SELECT 
                    "SBMC", 
                    "YMD", 
                    SUM("LPSL") AS "LPSL",
                    ROUND(SUM("BLSL")) AS "BLSL",
                    ROUND(SUM("RUN") / 60) AS "RUN",
                    ROUND(SUM("DOWN") / 60) AS "DOWN",
                    ROUND(SUM("IDEL") / 60) AS "IDEL",
                    ROUND(SUM("SHUTDOWN") / 60) AS "SHUTDOWN"
                FROM (
                    SELECT  
                        '{equipment_code}' AS "SBMC",
                        "YMD",
                        0 AS "LPSL",
                        0 AS "BLSL",
                        CASE WHEN "W" IN ('A001', 'A006', 'A007', 'A008', 'A009') THEN SUM("RESULT") ELSE 0 END AS "DOWN",
                        CASE WHEN "W" IN ('A002', 'A011', 'A012', 'A013', 'A014') THEN SUM("RESULT") ELSE 0 END AS "IDEL",
                        CASE WHEN "W" IN ('A004', 'A010') THEN SUM("RESULT") ELSE 0 END AS "SHUTDOWN",
                        CASE WHEN "W" IN ('A003') THEN SUM("RESULT") ELSE 0 END AS "RUN"
                    FROM (
                        SELECT 
                            SUBSTRING("DATEHOURS", 1, 8) AS "YMD", 
                            "STATE", 
                            SUBSTRING("STATE", 5, 8) AS "W", 
                            SUM("RESULT") AS "RESULT" 
                        FROM (
                            SELECT 
                                "C"."CODE" AS "CODE",
                                "B".*, 
                                SUBSTRING("B"."CODE", 1, 4) || SUBSTRING("C"."CODE", 1, 4) AS "STATE",
                                "C"."RESULT" AS "RS",
                                "C"."DATEHOUR" AS "DATEHOURS" 
                            FROM (
                                SELECT 
                                    "DATEHOUR", 
                                    "CODE", 
                                    "DATETIMES", 
                                    "RESULT", 
                                    "R" + 1 AS "R" 
                                FROM (
                                    SELECT 
                                        "XX".*, 
                                        0 AS "RESULT", 
                                        0 AS "R" 
                                    FROM "public"."CIM_MQTTCOLLECT" "XX" 
                                    WHERE "SEQ" = 2
                                        AND "DATEHOUR" LIKE REPLACE('{target_date_dash}' || '%', '-', '')
                                        AND "TOPIC" = '{equipment_code}'
                                        AND "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
                                    
                                    UNION ALL
                                    
                                    SELECT * FROM (
                                        SELECT 
                                            "T".*,
                                            (SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                             SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                            CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER) - 
                                            LAG(SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                                SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                                CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER)
                                                OVER (PARTITION BY SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "RESULT",
                                            ROW_NUMBER() OVER (PARTITION BY SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "R" 
                                        FROM "public"."CIM_MQTTCOLLECT" "T"
                                        WHERE "DATEHOUR" LIKE REPLACE('{target_date_dash}' || '%', '-', '')
                                            AND "TOPIC" = '{equipment_code}'
                                            AND "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
                                    ) "SUBQ1"
                                ) "UNION_RESULT"
                            ) "C",
                            (
                                SELECT 
                                    "DATEHOUR", 
                                    "CODE", 
                                    "RESULT", 
                                    "DATETIMES", 
                                    "R" 
                                FROM (
                                    SELECT * 
                                    FROM (
                                        SELECT 
                                            "T".*,
                                            (SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                             SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                              CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER) - 
                                            LAG(SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                                SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                                 CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER)
                                                OVER (PARTITION BY SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "RESULT",
                                            ROW_NUMBER() OVER (PARTITION BY SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "R" 
                                        FROM "public"."CIM_MQTTCOLLECT" "T"
                                        WHERE "DATEHOUR" LIKE REPLACE('{target_date_dash}' || '%', '-', '')
                                            AND "TOPIC" = '{equipment_code}'
                                            AND "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
                                    ) "SUBQ2"
                                ) "A"
                            ) "B"
                            WHERE "B"."R" = "C"."R" 
                        ) "JOINED" 
                        GROUP BY SUBSTRING("DATEHOURS", 1, 8), "STATE"
                        ORDER BY SUBSTRING("DATEHOURS", 1, 8)
                    ) "A"
                    GROUP BY "YMD", "W"
                    
                    UNION ALL
                    
                    SELECT * 
                    FROM "public"."CIM_MQTT_OK_NG_QTY"
                    WHERE "SBMC" = '{equipment_code}'
                ) "AL"
                GROUP BY "SBMC", "YMD"
            ) "GROUPED"
            LEFT JOIN "public"."EQUIPMENT_INFO_DICT" "TOPIC" 
                ON "TOPIC"."EQUIPMENT_CODE" = "SBMC" 
            ORDER BY "YMD"
        ) "A"
        WHERE SUBSTRING("YMD", 1, 4) || '-' || SUBSTRING("YMD", 5, 2) || '-' || SUBSTRING("YMD", 7, 2) = '{target_date_dash}'
        """
        data = self._execute_postgres_query(query)
        return {"status": "success", "equipment_code": equipment_code, "target_date": target_date_dash, "data": data}

    def get_equipment_downtime_summary(self, start_date_num: str, end_date_num: str) -> Dict[str, Any]:
        """
        4. 故障趨勢，可從時間，設備名稱，設備，設備樓層，排序
        - start_date_num: 如 '20260301'
        - end_date_num: 如 '20260311'
        """
        query = f"""
        SELECT * FROM (
            SELECT 
                SUBSTRING("SJ", 1, 8) AS "YMD",
                "TOPIC",
                "CODE",
                "NOTE",
                COUNT(0) AS "CS",
                ROW_NUMBER() OVER (ORDER BY COUNT(0) DESC) AS "RN"
            FROM "public"."CIM_MQTTCOLLECT_AM_PM"
            LEFT JOIN "public"."CIM_MQTTCODEERR" 
                ON "public"."CIM_MQTTCOLLECT_AM_PM"."TOPIC" = "public"."CIM_MQTTCODEERR"."MACHINE"
                AND "public"."CIM_MQTTCOLLECT_AM_PM"."CODE" = "public"."CIM_MQTTCODEERR"."PLCCODE"
            WHERE "CODETYPE" = 'B' 
                AND "CODE" IN (
                    SELECT "PLCCODE"
                    FROM "public"."CIM_MQTTCODEERR"
                )
            GROUP BY "NOTE", "CODE", "TOPIC", SUBSTRING("SJ", 1, 8)
        ) "S"
        WHERE 
            "S"."YMD" >= '{start_date_num}' 
            AND "S"."YMD" <= '{end_date_num}'
        ORDER BY 
            "YMD" ASC,
            "CS" ASC,
            "TOPIC" ASC
        """
        data = self._execute_postgres_query(query)
        return {"status": "success", "data": data}
