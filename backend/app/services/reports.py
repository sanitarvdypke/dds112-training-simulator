import csv
import io
from html import escape
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def report_font():
    for path in [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('C:/Windows/Fonts/arial.ttf')]:
        if path.exists():
            if 'ReportFont' not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont('ReportFont',str(path)))
            return 'ReportFont'
    raise RuntimeError('Установите шрифт DejaVu Sans для PDF')


def report_rows(result):
    rows=[('Балл',f'{result.score} / {result.max_score}'),('Время, сек',result.duration_sec),('Превышение общего норматива','Да' if result.over_time else 'Нет')]
    labels={'student':'Обучающийся','session':'Занятие','scenario':'Сценарий','number':'Номер карточки','service':'Служба','started_at':'Получение (ISO, UTC)','completed_at':'Завершение (ISO, UTC)','scenario_version':'Версия сценария'}
    details=result.details or {}
    for k,v in details.get('summary',{}).items(): rows.append((labels.get(k,k),v))
    approval=details.get('rubric_approval')
    if approval:
        rows.append(('Утверждение эталона',f"{approval['id']}; автор {approval['approved_by']}; {approval['approved_at']}"))
    if 'total_limit_sec' in details:
        rows.extend([('Общий норматив, сек',details['total_limit_sec']),('Отклонение общего времени, сек',details['total_deviation_sec'])])
    for c in details.get('criteria',[]):
        text=f"{c['score']} / {c['max_score']}; " + ('выполнено' if c['passed'] else 'не выполнено')
        if 'elapsed_sec' in c:
            anchor='от получения' if c['anchor']=='RECEIVED' else 'от предыдущего обязательного события'
            text+=f"; факт: {c['elapsed_sec'] if c['elapsed_sec'] is not None else 'нет события/начала отсчёта'} сек; норматив: {c['limit_sec'] if c['limit_sec'] is not None else 'не задан'}; {anchor}; опоздание: {c['deviation_sec'] if c['deviation_sec'] is not None else '-'} сек"
        rows.append(('Критерий: '+c['label'],text))
    for e in details.get('errors',[]): rows.append(('Ошибка: '+e['code'],e['message']))
    if not details.get('errors'): rows.append(('Ошибки','Не обнаружены'))
    field_names={'unit':'Подразделение / бригада','responsible':'Ответственный','measures':'Принятые меры','outcome':'Результат работ'}
    for k,v in details.get('dds_fields',{}).items(): rows.append(('ДДС: '+field_names.get(k,k),v))
    event_names={'ADDED':'Добавлена в занятие','RECEIVED':'Получена службой','COMPLETED':'Практика завершена','TEXT_INPUT':'Комментарий','UPDATE_DDS':'Изменение сведений ДДС'}
    for event in details.get('history',[]):
        payload=event['payload']
        label=payload.get('status',event_names.get(event['action_type'],event['action_type']))
        text=f"{event['occurred_at']} | {event['actor']} | {event['service']} | {label}"
        for k in ('comment','text'):
            if payload.get(k): text+='\n'+payload[k]
        for k,v in payload.get('fields',{}).items(): text+='\n'+field_names.get(k,k)+': '+(v or '(очищено)')
        rows.append(('Событие '+str(event.get('sequence_no','')),text))
    feedback=result.ai_feedback or {}
    rows.append(('Проверка текста (локальный mock AI)', '; '.join(feedback.get('grammar_issues',[])) or 'Замечаний не найдено; экспертная проверка не заменяется.'))
    if not details.get('history'): rows.append(('История','Старый результат: подробный снимок истории не сохранён.'))
    return rows


def assessment_csv(result) -> bytes:
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['Показатель','Значение'])
    for row in report_rows(result): writer.writerow([safe(v) for v in row])
    return out.getvalue().encode('utf-8-sig')


def assessment_pdf(result) -> bytes:
    out=io.BytesIO();font=report_font()
    body=ParagraphStyle('body',fontName=font,fontSize=9,leading=13,spaceAfter=8,splitLongWords=True)
    heading=ParagraphStyle('heading',parent=body,fontSize=16,leading=21,spaceAfter=18,textColor=colors.HexColor('#123b5d'))
    label=ParagraphStyle('label',parent=body,fontSize=10,spaceAfter=3,keepWithNext=True,textColor=colors.HexColor('#123b5d'))
    story=[Paragraph('Отчёт учебного тренажёра ДДС-112',heading)]
    for name,value in report_rows(result):
        story.extend([Paragraph(escape(str(name)),label),Paragraph(escape(str(value)).replace('\n','<br/>'),body)])
    def footer(canvas,doc):
        canvas.setFont(font,8);canvas.drawRightString(A4[0]-42,24,'Страница '+str(doc.page))
    SimpleDocTemplate(out,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=40,title='Отчёт ДДС-112').build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
