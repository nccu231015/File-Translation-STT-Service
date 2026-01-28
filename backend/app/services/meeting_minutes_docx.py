import os
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime

class MeetingMinutesDocxService:
    """
    Service for generating professional, structured Word documents from meeting analysis results.
    """
    
    def generate_minutes(
        self,
        file_name: str,
        meeting_objective: str = "",
        discussion_summary: str = "",
        decisions: list[str] = None,
        action_items: list[str] = None,
        attendees: list[str] = None,
        schedule_notes: str = "",
        date: datetime = None
    ) -> bytes:
        """
        Generate a professionally formatted Word document for meeting minutes.
        
        Args:
            file_name: Original audio file name
            summary: Meeting summary text
            decisions: List of decision items
            action_items: List of action items with assignees
            attendees: Optional list of attendee names
            date: Optional meeting date (defaults to now)
            
        Returns:
            Bytes of the generated .docx file
        """
        doc = Document()
        
        # Safety: Ensure lists are not None
        decisions = decisions or []
        action_items = action_items or []
        attendees = attendees or []
        
        # Helper to ensure string and format nested structures
        def format_content(val):
            if isinstance(val, list):
                # If list of dictionaries (e.g. topics)
                if val and isinstance(val[0], dict):
                    text = ""
                    for item in val:
                        for k, v in item.items():
                            # Clean up keys for display
                            key_display = k.replace('_', ' ').capitalize()
                            text += f"{key_display}: {format_content(v)}\n"
                        text += "\n"
                    return text.strip()
                return "\n".join([str(v) for v in val])
            elif isinstance(val, dict):
                text = ""
                for k, v in val.items():
                    text += f"{k}: {v}\n"
                return text.strip()
            return str(val) if val is not None else ""

        # Document title
        title = doc.add_heading('會議記錄', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 一、會議基本資訊
        doc.add_heading('一、會議基本資訊', level=1)
        
        # 會議主題
        p = doc.add_paragraph()
        p.add_run('會議主題：').bold = True
        p.add_run(file_name or '未命名會議')
       
        # 會議日期
        p = doc.add_paragraph()
        p.add_run('會議日期：').bold = True
        date_str = (date or datetime.now()).strftime('%Y年%m月%d日 %H:%M')
        p.add_run(date_str)
        
        # 會議方式
        p = doc.add_paragraph()
        p.add_run('會議方式：').bold = True
        p.add_run('線上會議')
        
        # 與會人員
        if attendees:
            p = doc.add_paragraph()
            p.add_run('與會人員：').bold = True
            doc.add_paragraph()
            for attendee in attendees:
                doc.add_paragraph(str(attendee), style='List Bullet')
        
        doc.add_paragraph()  # Spacing
        
        # 二、會議目的
        doc.add_heading('二、會議目的', level=1)
        objective_text = format_content(meeting_objective) if meeting_objective else '依會議內容進行需求討論與確認'
        doc.add_paragraph(objective_text)
        doc.add_paragraph()
        
        # 三、會議討論重點摘要
        doc.add_heading('三、會議討論重點摘要', level=1)
        summary_text = format_content(discussion_summary) if discussion_summary else '詳見決策事項與待辦事項'
        summary_paragraphs = summary_text.split('\n\n') if '\n\n' in summary_text else [summary_text]
        for idx, para_text in enumerate(summary_paragraphs, 1):
            if para_text.strip():
                if len(summary_paragraphs) > 1:
                    sub_heading = doc.add_heading(f'（{self._num_to_chinese(idx)}）討論要點', level=2)
                doc.add_paragraph(para_text.strip())
                doc.add_paragraph()
        
        # 四、決策事項
        doc.add_heading('四、決策事項', level=1)
        if decisions:
            for idx, decision in enumerate(decisions, 1):
                # 使用編號格式
                p = doc.add_paragraph()
                run_num = p.add_run(f'{idx}. ')
                run_num.bold = True
                run_num.font.color.rgb = RGBColor(34, 139, 34)
                
                run_text = p.add_run(decision)
                run_text.font.color.rgb = RGBColor(34, 139, 34)
                
                doc.add_paragraph()
        else:
            doc.add_paragraph('本次會議無決策事項')
        
        doc.add_paragraph()
        
        # 五、時程與後續安排
        doc.add_heading('五、時程與後續安排', level=1)
        schedule_text = format_content(schedule_notes) if schedule_notes else '依會議討論結果進行後續規劃與執行'
        doc.add_paragraph(schedule_text)
        doc.add_paragraph()
        
        # 六、待辦事項 (Action Items)
        doc.add_heading('六、待辦事項（Action Items）', level=1)
        if action_items:
            for action in action_items:
                text = ""
                if isinstance(action, dict):
                    # Format: 【Owner】Task (Deadline: ...)
                    task = str(action.get('task', ''))
                    owner = str(action.get('owner', ''))
                    deadline = str(action.get('deadline', ''))
                    
                    # 格式化為：【業主方】提供完整教室平面圖與配置圖 (期限: 2024-02-01)
                    if owner:
                        text = f"【{owner}】"
                    text += task
                    if deadline and deadline.lower() not in ['ongoing', '持續進行']:
                        text += f" (期限: {deadline})"
                else:
                    text = str(action)
                
                # 使用項目符號並加上藍色標記
                p = doc.add_paragraph(text, style='List Bullet')
                for run in p.runs:
                    run.font.color.rgb = RGBColor(30, 144, 255)
                
                doc.add_paragraph()
        else:
            doc.add_paragraph('本次會議無待辦事項')
        
        doc.add_paragraph()
        
        # 七、備註
        doc.add_heading('七、備註', level=1)
        doc.add_paragraph('本會議記錄由語音轉文字系統自動生成，如有遺漏或錯誤，請以實際會議內容為準。')
        
        # Save to bytes
        from io import BytesIO
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
    
    def _num_to_chinese(self, num: int) -> str:
        """Convert number to Chinese character (一、二、三...)"""
        chinese_nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        if num <= 10:
            return chinese_nums[num - 1]
        return str(num)
