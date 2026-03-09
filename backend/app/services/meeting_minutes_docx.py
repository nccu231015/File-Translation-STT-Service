"""
meeting_minutes_docx.py

Generates a bilingual (Traditional Chinese / English) meeting minutes Word document.
Each section displays Chinese text followed directly by the English translation —
same font size, same indentation, no prefix labels.
"""

from io import BytesIO
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime


class MeetingMinutesDocxService:
    """
    Service for generating professional, bilingual Word documents
    from meeting analysis results.
    """

    # Shared font sizes
    BODY_PT = 11

    def generate_minutes(
        self,
        file_name: str,
        meeting_objective: str = "",
        discussion_summary=None,
        decisions: list = None,
        action_items: list = None,
        attendees=None,
        schedule_notes: str = "",
        date: datetime = None,
        # English counterparts (optional — if provided, show bilingual)
        en_meeting_objective: str = "",
        en_discussion_summary=None,
        en_decisions: list = None,
        en_action_items: list = None,
        en_schedule_notes: str = "",
    ) -> bytes:
        doc = Document()

        decisions = decisions or []
        action_items = action_items or []
        attendees = attendees or []
        en_decisions = en_decisions or []
        en_action_items = en_action_items or []

        # ── Helpers ───────────────────────────────────────────────────────────
        ZH_COLOR = RGBColor(30, 80, 180)    # Blue for Chinese
        EN_COLOR = RGBColor(60, 60, 60)     # Dark grey for English

        def fmt(val) -> str:
            """Recursively stringify nested structures."""
            if isinstance(val, list):
                if val and isinstance(val[0], dict):
                    lines = []
                    for item in val:
                        for k, v in item.items():
                            lines.append(f"{k.replace('_',' ').capitalize()}: {fmt(v)}")
                        lines.append("")
                    return "\n".join(lines).strip()
                return "\n".join(str(v) for v in val)
            if isinstance(val, dict):
                return "\n".join(f"{k}: {v}" for k, v in val.items())
            return str(val) if val is not None else ""

        def add_body(doc, text: str, color: RGBColor):
            """Add a normal body paragraph with consistent size."""
            if not text:
                return
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.font.size = Pt(self.BODY_PT)
            run.font.color.rgb = color

        def add_bilingual(doc, zh: str, en: str):
            """Chinese paragraph then English paragraph — same size, same indent."""
            add_body(doc, zh, ZH_COLOR)
            add_body(doc, en, EN_COLOR)

        # ── Title ─────────────────────────────────────────────────────────────
        title = doc.add_heading("會議記錄 Meeting Minutes", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ── 一、基本資訊 ──────────────────────────────────────────────────────
        doc.add_heading("一、會議基本資訊  |  1. Meeting Information", level=1)

        for label, value in [
            ("會議主題 Topic：", file_name or "未命名會議"),
            ("會議日期 Date：", (date or datetime.now()).strftime("%Y年%m月%d日 %H:%M")),
            ("會議方式 Mode：", "線上會議 / Online Meeting"),
        ]:
            p = doc.add_paragraph()
            b = p.add_run(label)
            b.bold = True
            b.font.size = Pt(self.BODY_PT)
            v = p.add_run(value)
            v.font.size = Pt(self.BODY_PT)

        if attendees:
            if isinstance(attendees, str):
                sep = "," if "," in attendees else "、"
                attendees = [a.strip() for a in attendees.replace("、", ",").replace("；", ",").split(",") if a.strip()]

            p = doc.add_paragraph()
            b = p.add_run("與會人員 Attendees：")
            b.bold = True
            b.font.size = Pt(self.BODY_PT)
            for a in attendees:
                if a.strip():
                    ap = doc.add_paragraph(a.strip(), style="List Bullet")
                    for r in ap.runs:
                        r.font.size = Pt(self.BODY_PT)

        doc.add_paragraph()

        # ── 二、會議目的 ──────────────────────────────────────────────────────
        doc.add_heading("二、會議目的  |  2. Meeting Objective", level=1)
        zh_obj = fmt(meeting_objective) or "依會議內容進行需求討論與確認"
        en_obj = fmt(en_meeting_objective)
        add_bilingual(doc, zh_obj, en_obj)
        doc.add_paragraph()

        # ── 三、討論摘要 ──────────────────────────────────────────────────────
        doc.add_heading("三、討論摘要  |  3. Discussion Summary", level=1)

        def split_paras(val):
            text = fmt(val) if val else ""
            return [p.strip() for p in text.split("\n\n") if p.strip()]

        zh_paras = split_paras(discussion_summary)
        en_paras = split_paras(en_discussion_summary)
        count = max(len(zh_paras), len(en_paras), 1)
        for i in range(count):
            zh_p = zh_paras[i] if i < len(zh_paras) else ""
            en_p = en_paras[i] if i < len(en_paras) else ""
            add_bilingual(doc, zh_p, en_p)
            doc.add_paragraph()

        # ── 四、決策事項 ──────────────────────────────────────────────────────
        doc.add_heading("四、決策事項  |  4. Decisions", level=1)
        if decisions:
            for idx, decision in enumerate(decisions, 1):
                en_dec = en_decisions[idx - 1] if idx - 1 < len(en_decisions) else ""

                # Chinese
                p_zh = doc.add_paragraph()
                num = p_zh.add_run(f"{idx}. ")
                num.bold = True
                num.font.size = Pt(self.BODY_PT)
                num.font.color.rgb = RGBColor(34, 120, 34)
                txt = p_zh.add_run(str(decision))
                txt.font.size = Pt(self.BODY_PT)
                txt.font.color.rgb = RGBColor(34, 120, 34)

                # English (same indent = none, same size)
                if en_dec:
                    p_en = doc.add_paragraph()
                    en_num = p_en.add_run(f"{idx}. ")
                    en_num.bold = True
                    en_num.font.size = Pt(self.BODY_PT)
                    en_num.font.color.rgb = RGBColor(80, 140, 80)
                    en_txt = p_en.add_run(str(en_dec))
                    en_txt.font.size = Pt(self.BODY_PT)
                    en_txt.font.color.rgb = RGBColor(80, 140, 80)

                doc.add_paragraph()
        else:
            add_bilingual(
                doc,
                "本次會議無決策事項",
                "No decisions made in this meeting.",
            )

        doc.add_paragraph()

        # ── 五、時程安排 ──────────────────────────────────────────────────────
        doc.add_heading("五、時程與後續安排  |  5. Schedule & Follow-Up", level=1)
        zh_sch = fmt(schedule_notes) or "依會議討論結果進行後續規劃與執行"
        en_sch = fmt(en_schedule_notes)
        add_bilingual(doc, zh_sch, en_sch)
        doc.add_paragraph()

        # ── 六、待辦事項 ──────────────────────────────────────────────────────
        doc.add_heading("六、待辦事項  |  6. Action Items", level=1)
        if action_items:
            for idx, action in enumerate(action_items):
                en_action = en_action_items[idx] if idx < len(en_action_items) else {}

                # Build Chinese string
                if isinstance(action, dict):
                    task = str(action.get("task", ""))
                    owner = str(action.get("owner", ""))
                    deadline = str(action.get("deadline", ""))
                    zh_text = f"【{owner}】{task}" if owner else task
                    if deadline and deadline.lower() not in ("ongoing", "持續進行"):
                        zh_text += f"（期限：{deadline}）"
                else:
                    zh_text = str(action)

                # Build English string
                if isinstance(en_action, dict):
                    en_task = str(en_action.get("task", ""))
                    en_owner = str(en_action.get("owner", ""))
                    en_deadline = str(en_action.get("deadline", ""))
                    en_text = f"[{en_owner}] {en_task}" if en_owner else en_task
                    if en_deadline and en_deadline.lower() != "ongoing":
                        en_text += f" (Due: {en_deadline})"
                else:
                    en_text = str(en_action) if en_action else ""

                # Chinese bullet
                p_zh = doc.add_paragraph(style="List Bullet")
                r_zh = p_zh.add_run(zh_text)
                r_zh.font.size = Pt(self.BODY_PT)
                r_zh.font.color.rgb = ZH_COLOR

                # English bullet — same style, same size, directly below
                if en_text:
                    p_en = doc.add_paragraph(style="List Bullet")
                    r_en = p_en.add_run(en_text)
                    r_en.font.size = Pt(self.BODY_PT)
                    r_en.font.color.rgb = EN_COLOR

                doc.add_paragraph()
        else:
            add_bilingual(doc, "本次會議無待辦事項", "No action items.")

        doc.add_paragraph()

        # ── 七、備註 ──────────────────────────────────────────────────────────
        doc.add_heading("七、備註  |  7. Notes", level=1)
        note_zh = doc.add_paragraph(
            "本會議記錄由語音轉文字系統自動生成，如有遺漏或錯誤，請以實際會議內容為準。"
        )
        for r in note_zh.runs:
            r.font.size = Pt(self.BODY_PT)
            r.font.color.rgb = ZH_COLOR

        note_en = doc.add_paragraph(
            "This meeting record was automatically generated by an AI speech-to-text system. "
            "Please verify against the actual meeting content."
        )
        for r in note_en.runs:
            r.font.size = Pt(self.BODY_PT)
            r.font.color.rgb = EN_COLOR

        # ── Serialize ─────────────────────────────────────────────────────────
        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()
