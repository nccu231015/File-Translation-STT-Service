from typing import Dict, Any, List
from .sql_tools import FactorySqlTools
import datetime

class EquipmentSqlAgent:
    """
    負責處理「設備檢索」上下文的工具調用，將自然語言轉為 7 種設備分析功能：
      EQ-A: 各樓層設備即時稼動狀態
      EQ-B: 良率未達標設備（紅色標記）
      EQ-C: 指定樓層設備稼動燈號與稼動率
      EQ-D: 特定設備生産機種不良率趨勢（Bar+Line）
      EQ-E: 停機時數異常排行 Top-N（Pareto）
      EQ-F: 設備故障原因分布比較（兩期間對比）
      EQ-G: 故障原因熱點圖（設備 × 故障原因 Heat Map）
    """

    def __init__(self, llm_service):
        self.llm   = llm_service
        self.tools = FactorySqlTools()

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            # ── EQ-A ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_operation_status",
                    "description": (
                        "[設備] 查詢各樓層設備的即時稼動狀態。"
                        "按樓層與設備類型分組，呈現良品數、不良數、良率、資料日期。"
                        "可選擇指定樓層（如 '3F'）或查全廠。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {
                                "type": "string",
                                "description": "樓層，例如 '1F'、'3F'、'4F'。不傳則查全廠。"
                            },
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            }
                        }
                    }
                }
            },
            # ── EQ-B ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_underperforming_equipment",
                    "description": (
                        "[設備] 找出良率未達標的設備（預設門檻：80%）。"
                        "良率 = 良品數 / (良品數 + 不良數) × 100。"
                        "回傳達標狀態燈號（🔴未達標），含資料日期。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            },
                            "threshold": {
                                "type": "number",
                                "description": "良率門檻（百分比），預設 80.0。"
                            }
                        }
                    }
                }
            },
            # ── EQ-C ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_floor_equipment_status",
                    "description": (
                        "[設備] 查詢指定樓層的設備總數與稼動狀態。"
                        "按設備類型分組，顯示即時狀態燈號（🟢稼動中/🔴停機/🟡閒置/⚫關機）"
                        "與稼動率 = RUN / (RUN + DOWN)。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {
                                "type": "string",
                                "description": "必填。樓層，例如 '1F'、'3F'、'4F'。"
                            },
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            }
                        },
                        "required": ["floor"]
                    }
                }
            },
            # ── EQ-D ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_model_production_trend",
                    "description": (
                        "[設備] 查詢特定設備在時間區間內生產了哪些機種，以及各機種的"
                        "產量與不良率趨勢。可用設備代碼（如 '94135B'）或設備名稱關鍵字"
                        "（如 '成型機A'）指定設備。"
                        "可選回傳 bar_line_combo 圖表（透過 include_chart 參數控制）。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "查詢開始日期，格式 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "查詢結束日期，格式 YYYY-MM-DD。"
                            },
                            "equipment_code": {
                                "type": "string",
                                "description": "設備代碼（SBMC/TOPIC），例如 '94135B'。與 equipment_name 擇一。"
                            },
                            "equipment_name": {
                                "type": "string",
                                "description": "設備名稱關鍵字，例如 '成型機A'。系統會模糊比對。與 equipment_code 擇一。"
                            },
                            "granularity": {
                                "type": "string",
                                "description": (
                                    "時間粒度：'daily'（每日）、'weekly'（每週）、"
                                    "'monthly'（月對月）、'quarterly'（季對季）、'yearly'（年對年）。"
                                    "預設 'monthly'。"
                                )
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否需要畫圖/產生圖表配置？單純詢問「生產了哪些機種」設為 false。除非使用者明確詢問「不良比例、走勢」或要求「畫圖/產生圖表」，才設為 true。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            # ── EQ-E ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_downtime_anomaly_ranking",
                    "description": (
                        "[EQ-E] 查詢指定期間內停機時數前 N 名的設備（Pareto），"
                        "帶有各停機原因明細（計畫停機/設備故障/換模換料/品質異常/待料停工）。"
                        "支援迴視期間：30天/一季/半年等。"
                        "可颓視實際停機著黄點，带楼層位置資訊。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "查詢開始日期 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "查詢結束日期 YYYY-MM-DD。"
                            },
                            "top_n": {
                                "type": "integer",
                                "description": "回傳前 N 名，預設 10。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "指定樓層（如 '3F'），省略則查全廠。"
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否產生 Pareto 圖表配置，預設 false。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            # ── EQ-F ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_fault_pattern_comparison",
                    "description": (
                        "[EQ-F] 比較兩個期間的設備停機原因分佈，適用於："
                        "【此季對上季】【上半年對下半年】等對比分析。"
                        "可鎖定到特定設備、樓層或全廠。"
                        "回傳各原因停機時數對比表 + 趨勢標記。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period_a_start": {
                                "type": "string",
                                "description": "期間A 開始日 YYYY-MM-DD。"
                            },
                            "period_a_end": {
                                "type": "string",
                                "description": "期間A 結束日 YYYY-MM-DD。"
                            },
                            "period_b_start": {
                                "type": "string",
                                "description": "期間B 開始日 YYYY-MM-DD。"
                            },
                            "period_b_end": {
                                "type": "string",
                                "description": "期間B 結束日 YYYY-MM-DD。"
                            },
                            "period_a_label": {
                                "type": "string",
                                "description": "期間A 顯示名稱，如 '本季'、'2026 Q1'、'上半年'。"
                            },
                            "period_b_label": {
                                "type": "string",
                                "description": "期間B 顯示名稱，如 '上季'、'2025 Q4'、'下半年'。"
                            },
                            "equipment_code": {
                                "type": "string",
                                "description": "鎖定特定設備代碼，省略則分析全廠/指定樓層。"
                            },
                            "equipment_name": {
                                "type": "string",
                                "description": "鎖定特定設備名稱關鍵字。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "鎖定樓層（如 '3F'），省略則全廠。"
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否產生分組柱狀圖表配置，預設 false。"
                            }
                        },
                        "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"]
                    }
                }
            },
            # ── EQ-G ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_fault_heatmap",
                    "description": (
                        "[EQ-G] 產生設備故障原因熱點圖（Heat Map），"
                        "X 軸 = 設備名稱，Y 軸 = 具體故障原因（NOTE），"
                        "儲格色階 = 發生次數（白→深紅）。"
                        "適用於：「哪台設備跟哪種故障最相關」「故障熱點圖」。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "開始日期 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "結束日期 YYYY-MM-DD。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "樓層篩選（如 '3F'），省略則全廠。"
                            },
                            "top_n_equipment": {
                                "type": "integer",
                                "description": "X 軸顯示的設備數，預設 8。"
                            },
                            "top_m_notes": {
                                "type": "integer",
                                "description": "Y 軸顯示的故障原因數，預設 10。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
        ]

    async def execute_task(self, question: str) -> Dict[str, Any]:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """支援上下文記憶的聊天接口，回傳與 SqlAgent 格式一致的 dict。"""
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"

        system_prompt = f"""你是一個專業的製造業數據分析專家，負責處理「全一電子」的**設備專用數據**。
你的任務是根據使用者的問題，調用資料庫工具來獲取即時設備數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

【數據源說明】
此模式為【設備檢索】模式，資料來自設備 MQTT 信號（PostgreSQL）及生產記錄（MSSQL）。

【工具調用規範】
1. 詢問「各樓層設備稼動狀態、生產數、不良數」→ 調用 `get_equipment_operation_status`
   - 全廠：不傳 floor；指定樓層：傳入 floor（如 '3F'）
   - 必須含資料日期
   - 回傳欄位說明：`稼動狀態` 值為 RUN/DOWN/STOP，呈現時轉換：RUN → 🟢 稼動中、DOWN → 🔴 停機、STOP → ⚫ 停止
   - `機型` 欄為設備分類群組，請以此欄位進行分組後呈現，讓表格更易閱讀
   - `生產數` = 良品數，`不良數` = 不良品數，可合併呈現為「產出(良/不良)」格式

2. 詢問「哪些設備達成率/良率未達標、低於80%、未達標」→ 調用 `get_underperforming_equipment`
   - threshold 預設 80.0（即良率 < 80% 標記為紅色）
   - 回覆需包含 🔴/🟢 燈號說明

3. 詢問「某樓層設備有幾台在稼動、設備稼動率、開工/停工狀態」 → 調用 `get_floor_equipment_status`
   - floor 為必填（如 '3F'）
   - 回覆需包含總台數、稼動台數、停機台數、稼動率

4. 詢問「某設備今天/這段時間生産了哪些機種、機種的不良率走勢、設備生産趨勢」 → 調用 `get_equipment_model_production_trend`
   - equipment_code 或 equipment_name 擇一提供
   - 時間範圍：今天 = start_date=end_date=今天；近30天 = 往前30天；本季/半年依此計算
   - granularity 對應：月對月=monthly、季對季=quarterly、每日=daily、每週=weekly、年對年=yearly

5. 詢問「哪些設備停機時間異常過長、停機確 Top-N、停機主因」 → 調用 `get_downtime_anomaly_ranking`
   - 時間範圍按個別話展開：近30天/這一季/上一季/上半年依對應計算
   - top_n 預設 10，使用者指定則跟上
   - 回傳結果包含：排名、樓層位置、停機時數、主要原因、各原因時數明細
   - 停機原因代碼對照：A001=計畫停機, A006=設備故障, A007=換模/換料, A008=品質異常停線, A009=待料停工
   - **【NOTE 顯示規則 - 強制執行】** 每台設備有 `具體故障原因` 清單（來自 CIM_MQTTCODEERR）：
     * 若該欄位為**空陣列**（`[]`）：表示該設備無設備故障明細（通常主因為 A001 計畫停機，屬正常現象）
     * 若該欄位**非空**（有資料）：**必須**在表格下方加一行提示：「⚠️ 部分設備存在具體故障明細，請輸入設備名稱追問以查看詳情。」
     * **絕對不要主動展開所有設備的 NOTE 清單**；使用者明確追問特定設備才列出該設備的故障原因清單
     * **若所有設備的 `具體故障原因` 皆為空陣列，則說明：「本期間停機以計畫停機（A001）為主，無設備故障碼明細。」**

6. 詢問「比較兩個時期的停機原因/故障趨勢是否改善」等**使用者明確要求對比兩個不同期間**的查詢（如「本季 vs 上季」「上半年對下半年」）→ 調用 `get_fault_pattern_comparison`
   - **⚠️ 重要判斷**：僅在使用者清楚提到兩個期間時才使用此工具；若使用者只詢問「故障有沒有規律」「故障分布」「哪種故障最常出現」等**未明確要求兩期間對比**的問題，請改用 EQ-G（`get_fault_heatmap`）
   - period_a 和 period_b 均為必填，常見用法：本季對上季、上半年對下半年
   - 可鎖定設備、樓層或全廠
   - 回傳兩層比對：`comparison`（A001-A009 狀態碼粗分類停機時數）和 `note_comparison`（具體 NOTE 層級發生次數細分類）
   - 回覆時**優先呈現 `note_comparison` 表格**（具體故障原因有意義），`comparison` 作為補充說明；若 `note_comparison` 為空代表該設備未建立故障碼對照，則僅呈現 `comparison`

7. 詢問「故障熱點圖/heat map/哪台設備跟哪種故障最相關」，或**未明確指定兩個期間對比**的「故障原因分布/故障有沒有規律/哪種故障最多/單一期間故障模式分析」→ 調用 `get_fault_heatmap`
   - 需提供時間範圍，可選填樓層、top_n_equipment、top_m_notes
   - 回傳 chart_config（chart_type='heatmap'），前端會自動渲染熱點色階圖
   - 請說明：「X 軸為設備名稱、Y 軸為故障原因、儲格色越深表示發生次數越多」

【回覆格式規範】
- **全程使用繁體中文**，絕對禁止輸出英文句子，禁止使用「產線」一詞（本模式為「設備」專區）
- **強制要求**：不論資料筆數多寡，**必須且務必將工具回傳的 `data` 陣列完整輸出成 Markdown 表格**。你可以提供總結文字，但**絕對不准省略表格**！
- 燈號說明：🟢=稼動/達標，🔴=停機/未達標，🟡=閒置，⚫=關機
- 圖表（EQ-D）回覆注意：工具回傳含 `model_names`（機種清單）、`trend_data`（時序資料）、`summary`（總計）、`chart_config`（圖表配置）、`gdhm_available`（工單號是否存在）。**當使用者僅詢問「生產哪些機種」時，絕對不要畫圖**，只列出 `model_names` 及 `summary` 即可。只有當使用者明確詢問「不良比例/走勢/趨勢」或要求「畫圖/產生圖表」時，才使用 `chart_config` 回傳圖表（`include_chart=true`）。有產出圖表時需說明「柱狀圖代表該設備總產量（左軸），折線代表不良率（右軸）」，時序標籤依 granularity 設定。**若 `gdhm_available=false`，代表該設備在設備資料表中尚未設定工單對應（GDHM 為空），無法查詢機種名稱，請如實告知：「該設備尚未建立工單對應，無法查詢機種資料，但產量與良率數據正常可用。」**
- 格式清理：表格中若出現 `null` 數值，請自動轉換為 `0`；若「稼動率(%)」為 `null`，請顯示為 `-`，別讓畫面看起來一團亂。
- 禁止暴露程式術語（如 data 陣列、SQL 欄位名稱等）
- 查無資料時，婉轉說明：「目前設備系統尚未回傳相關數據，可能機台尚未開機或該日無生產記錄。」

【欄位顯示規則（🚨極其重要：避免表格過寬破版🚨）】
- 為了適應聊天視窗，**強烈要求精簡 Markdown 表格的欄位數（最多 5~6 欄為主）**。
- 務必將「設備名稱」與「設備代碼」合併為一欄「設備 (代碼)」，例如 `WELD2A (502-1)`。
- 將「良品數量」與「不良數量」合併為一欄「產出 (良/不良)」，例如 `100 / 2`。
- 若詢問「稼動狀態/總數/稼動率」：絕對省略 `RUN(分)`、`DOWN(分)`、`IDEL(分)`、`SHUTDOWN(分)`，且把「當前狀態」與「狀態燈」合併為「狀態燈」。表格只需顯示：`樓層`、`設備(代碼)`、`狀態燈`、`稼動率(%)`、`產出(良/不良)`。
- 若詢問「達標/良率」：只顯示 `樓層`、`設備(代碼)`、`產出(良/不良)`、`良率(%)`、`狀態燈`。
- 若詢問「停機排名/EQ-E」：表格顯示 `排名`、`樓層`、`設備(代碼)`、`停機時數(h)`、`主要停機原因`；表格呈現後**以一行文字**提示「若需了解特定設備的具體故障原因明細，請直接追問設備名稱」，**不要主動展開各設備的 `具體故障原因` 清單**，等使用者追問再詳細呈現。
- 若詢問「故障分布比較/EQ-F」：**優先**使用 `note_comparison` 建立「具體故障原因對比表」，欄位為 `故障原因`、`異常類別`、`{{期間A}}次數`、`{{期間B}}次數`、`變化(次)`、`趨勢`；狀態碼 `comparison` 表格標題明確標注「（停機時數粗分類）」作為補充。若 `note_comparison` 為空，則只呈現 `comparison`。趨勢欄位保留 ⬆ 惡化 / ⬇ 改善 / ─ 持平標記。
- 若詢問「故障熱點圖/EQ-G」：當工具回傳 chart_config.chart_type='heatmap' 時，前端將自動渲染熱點圖。你只需在文字中說明「X 軸為設備、Y 軸為故障原因，儲格顏色越深代表該設備此故障發生次數越多」，並點出前幾名熱點組合即可。
- 「資料日期」只需在總結文字中提及一次即可，**絕對禁止**放進表格中成為獨立欄位！

【稼動率計算說明】
稼動率 = RUN(分) / (RUN(分) + DOWN(分)) × 100%
RUN = CODE='A003' 的信號區間加總；DOWN = CODE 為 A001/A006~A009 的區間加總
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": question})

        try:
            result = await self.llm.chat_with_tools(
                messages=messages,
                tools=self._get_tool_schemas(),
                tool_executor_obj=self.tools
            )
            response_text = self.llm.s2tw.convert(result["response"])
            return {"response": response_text, "chart_config": result.get("chart_config")}
        except Exception as e:
            print(f"[Equipment SQL Agent Error] {e}")
            return {"response": f"抱歉，在查詢設備資料庫時發生錯誤：{str(e)}", "chart_config": None}
