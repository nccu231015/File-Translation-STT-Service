def _get_query_1_production_status(target_date: str) -> str:
    target_ymd = target_date.replace('-', '')
    return f"""
SELECT
"A"."SBMC" "設備名稱",
"A"."YMD" "年月日",
"A"."LPSL" "良品數量",
"A"."RUN" "運行時間",
"A"."DOWN" "DOWN時間",
"A"."IDEL" "IDEL時間",
"A"."SHUTDOWN" "SHUTDOWN時間",
"A"."ID" "ID",
"A"."EQUIPMENT_NAME" "設備名稱_1",
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
                "TOPIC" AS "SBMC",
                "YMD",
                0 AS "LPSL",
                0 AS "BLSL",
                CASE WHEN "W" IN ('A001', 'A006', 'A007', 'A008', 'A009') THEN SUM("RESULT") ELSE 0 END AS "DOWN",
                CASE WHEN "W" IN ('A002', 'A011', 'A012', 'A013', 'A014') THEN SUM("RESULT") ELSE 0 END AS "IDEL",
                CASE WHEN "W" IN ('A004', 'A010') THEN SUM("RESULT") ELSE 0 END AS "SHUTDOWN",
                CASE WHEN "W" IN ('A003') THEN SUM("RESULT") ELSE 0 END AS "RUN"
            FROM (
                SELECT 
                    "TOPIC",
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
                            "R" + 1 AS "R",
                            "TOPIC"
                        FROM (
                            SELECT 
                                "XX".*, 
                                0 AS "RESULT", 
                                0 AS "R" 
                            FROM "public"."CIM_MQTTCOLLECT" "XX" 
                            WHERE "SEQ" = 2
                                AND "DATEHOUR" LIKE '{target_ymd}' || '%'
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
                                        OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "RESULT",
                                    ROW_NUMBER() OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "R" 
                                FROM "public"."CIM_MQTTCOLLECT" "T"
                                WHERE "DATEHOUR" LIKE '{target_ymd}' || '%'
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
                            "R",
                            "TOPIC"
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
                                        OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "RESULT",
                                    ROW_NUMBER() OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "DATETIMES") AS "R" 
                                FROM "public"."CIM_MQTTCOLLECT" "T"
                                WHERE "DATEHOUR" LIKE '{target_ymd}' || '%'
                                    AND "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
                            ) "SUBQ2"
                        ) "A"
                    ) "B"
                    WHERE "B"."R" = "C"."R" AND "B"."TOPIC" = "C"."TOPIC"
                ) "JOINED" 
                GROUP BY "TOPIC", SUBSTRING("DATEHOURS", 1, 8), "STATE"
            ) "A"
            GROUP BY "TOPIC", "YMD", "W"
            
            UNION ALL
            
            SELECT * 
            FROM "public"."CIM_MQTT_OK_NG_QTY"
        ) "AL"
        GROUP BY "SBMC", "YMD"
    ) "GROUPED"
    LEFT JOIN "public"."EQUIPMENT_INFO_DICT" "TOPIC" 
        ON "TOPIC"."EQUIPMENT_CODE" = "SBMC" 
) "A"
WHERE SUBSTRING("YMD", 1, 4) || '-' || SUBSTRING("YMD", 5, 2) || '-' || SUBSTRING("YMD", 7, 2) = '{target_date}'
"""

def _get_query_2_failure_trend(start_date: str, end_date: str) -> str:
    start_ymd = start_date.replace('-', '')
    end_ymd = end_date.replace('-', '')
    return f"""
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
    "S"."YMD" >= '{start_ymd}' 
    AND "S"."YMD" <= '{end_ymd}'
ORDER BY 
    "YMD" ASC,
    "CS" DESC,
    "TOPIC" ASC
"""

def _get_query_3_downtime_stats(start_date: str, end_date: str) -> str:
    start_ymd = start_date.replace('-', '')
    end_ymd = end_date.replace('-', '')
    return f"""
SELECT DISTINCT
    "BZCN" as "標準產能",
    "CT"."EQUIPMENT_NAME" as "機台名稱",
    "VV"."MC" as "設備名稱",
    "VV"."R" as "RUN",
    "VV"."I" as "IDEL",
    "VV"."D" as "DOWN",
    "VV"."S" as "SHUTDOWN",
    "VV"."GZCS" as "故障次數",
    "VV"."YMD" as "年月日",
    "VV"."LPSL" as "良品數量",
    "VV"."BLSL" as "不良數量",
    "VV"."RUN" as "RUN數值",
    "VV"."IDEL" as "IDEL數值",
    "VV"."DOWN" as "DOWN數值",
    "VV"."SHUTDOWN" as "SHUTDOWN數值",
    "GD"."WORK_ORDER_NO" "工單號碼",
    "GD"."WORK_ORDER_NUM" "工單數量"
FROM (
    SELECT 
        "A"."SBMC" AS "MC",
        TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS') AS "RECORD_TIME",
        TO_CHAR(FLOOR("A"."RUN" / 60), 'FM00') || ':' || TO_CHAR(MOD("A"."RUN", 60), 'FM00') AS "R",
        TO_CHAR(FLOOR("A"."IDEL" / 60), 'FM00') || ':' || TO_CHAR(MOD("A"."IDEL", 60), 'FM00') AS "I",
        TO_CHAR(FLOOR("A"."DOWN" / 60), 'FM00') || ':' || TO_CHAR(MOD("A"."DOWN", 60), 'FM00') AS "D",
        TO_CHAR(FLOOR("A"."SHUTDOWN" / 60), 'FM00') || ':' || TO_CHAR(MOD("A"."SHUTDOWN", 60), 'FM00') AS "S",

        "BB"."GZCS",
        "AAA"."STATE",
        "A".*, 
        SUBSTRING("A"."YMD", 7, 2) || '號' AS "DD" 
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
                    "TOPIC" AS "SBMC",
                    "YMD",
                    0 AS "LPSL", 
                    0 AS "BLSL",
                    CASE WHEN "W" IN ('A001', 'A006', 'A007', 'A008', 'A009') THEN SUM("RESULT") ELSE 0 END AS "DOWN",
                    CASE WHEN "W" IN ('A002', 'A011', 'A012', 'A013', 'A014') THEN SUM("RESULT") ELSE 0 END AS "IDEL",
                    CASE WHEN "W" IN ('A004', 'A010') THEN SUM("RESULT") ELSE 0 END AS "SHUTDOWN",
                    CASE WHEN "W" IN ('A003') THEN SUM("RESULT") ELSE 0 END AS "RUN"
                FROM (
                    SELECT 
                        "TOPIC",
                        SUBSTRING("DATEHOURS", 1, 8) AS "YMD", 
                        "STATE", 
                        SUBSTRING("STATE", 5, 8) AS "W", 
                        SUM("RESULT") AS "RESULT" 
                    FROM (
                        WITH "BASE_DATA" AS (
                            SELECT
                                "T".*,
                                (SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                 SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                 CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER) - 
                                LAG(SUBSTRING("DATETIMES", 10, 2)::INTEGER * 3600 + 
                                    SUBSTRING("DATETIMES", 12, 2)::INTEGER * 60 + 
                                    CAST(SUBSTRING("DATETIMES", 14)AS NUMERIC)::INTEGER)
                                    OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "TOPIC", "DATETIMES") AS "RESULT",
                                ROW_NUMBER() OVER (PARTITION BY "TOPIC", SUBSTRING("DATETIMES", 1, 8) ORDER BY "TOPIC", "DATETIMES") AS "R"
                            FROM "public"."CIM_MQTTCOLLECT" "T"
                            WHERE "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
                        )
                        SELECT
                            "B"."TOPIC",
                            "B"."DATEHOUR" AS "DATEHOURS",
                            "B"."CODE",
                            "B"."DATETIMES",
                            "B"."RESULT",
                            "B"."R",
                            SUBSTRING("B"."CODE", 1, 4) || SUBSTRING(LAG("B"."CODE") OVER (PARTITION BY "B"."TOPIC", SUBSTRING("B"."DATEHOUR", 1, 8) ORDER BY "B"."TOPIC", SUBSTRING("B"."DATEHOUR", 1, 8)), 1, 4) AS "STATE"
                        FROM "BASE_DATA" "B"
                    ) "SUBQ"
                    GROUP BY "TOPIC", SUBSTRING("DATEHOURS", 1, 8), "STATE"
                ) "A" 
                GROUP BY "TOPIC", "YMD", "W"

                UNION ALL 

                SELECT * FROM "public"."CIM_MQTT_OK_NG_QTY"
            ) "AL" 
            GROUP BY "SBMC", "YMD"
        ) "SUBQ2"
    ) "A" 
    LEFT JOIN (
        SELECT * FROM (
            SELECT 
                "CODE",
                "TOPIC",
                SUBSTRING("DATEHOUR", 1, 4) || '-' || SUBSTRING("DATEHOUR", 5, 2) || '-' || SUBSTRING("DATEHOUR", 7, 2) AS "YMD",
                CASE 
                    WHEN "CODE" IN ('A001','A006','A007','A008','A009') THEN 'DOWN'
                    WHEN "CODE" IN ('A002','A011','A012','A013','A014') THEN 'IDEL'
                    WHEN "CODE" IN ('A004','A010') THEN 'SHUTDOWN'
                    WHEN "CODE" IN ('A003') THEN 'RUN' 
                    ELSE '' 
                END AS "STATE"
            FROM "public"."CIM_MQTTCOLLECT"
            WHERE "SEQ" = (
                SELECT MAX("SEQ") 
                FROM "public"."CIM_MQTTCOLLECT"
                WHERE "CODE" IN ('A001','A002','A003','A004','A005','A006','A007','A008','A009','A010','A011','A012','A013','A014','A015','A016','A017','A018')
            )
        ) "AA"
    ) "AAA" ON "A"."SBMC" = "AAA"."TOPIC" AND "A"."YMD" = "AAA"."YMD"
    LEFT JOIN (
        SELECT 
            "TOPIC",  
            COUNT(0) AS "GZCS",
            SUBSTRING("SJ", 1, 8) AS "YMD"
        FROM "public"."CIM_MQTTCOLLECT_AM_PM"
        LEFT JOIN "public"."CIM_MQTTCODEERR" 
            ON "public"."CIM_MQTTCOLLECT_AM_PM"."TOPIC" = "public"."CIM_MQTTCODEERR"."MACHINE"
            AND "public"."CIM_MQTTCOLLECT_AM_PM"."CODE" = "public"."CIM_MQTTCODEERR"."PLCCODE"
        WHERE "CODETYPE" = 'B' 
            AND "NOTE" IS NOT NULL
            AND "CATE" = 'DOWN'
            AND "CODE" IN (SELECT "PLCCODE" FROM "public"."CIM_MQTTCODEERR") 
        GROUP BY "TOPIC", SUBSTRING("SJ", 1, 8)
    ) "BB" ON "A"."SBMC" = "BB"."TOPIC" AND "A"."YMD" = "BB"."YMD"
) "VV"
LEFT JOIN "public"."EQUIPMENT_INFO_DICT" "CT" 
    ON "CT"."EQUIPMENT_CODE" = "VV"."MC"
LEFT JOIN "public"."CIM_WORK_GD_NUM_GLW" "GD" 
    ON REPLACE(TO_CHAR("GD"."PRO_TIME", 'YYYY-MM-DD'), '-', '') = "VV"."YMD"
    AND "GD"."NO" = (REGEXP_MATCH("CT"."EQUIPMENT_NAME", '[0-9]+'))[1]::TEXT
WHERE 
    "VV"."YMD" >= '{start_ymd}' 
    AND "VV"."YMD" <= '{end_ymd}'
ORDER BY 
    "YMD", 
    "MC" DESC
"""
