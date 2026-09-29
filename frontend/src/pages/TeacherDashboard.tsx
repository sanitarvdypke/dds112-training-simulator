import {RubricEditor} from '../components/RubricEditor';
import {AssessmentDetails} from '../components/AssessmentDetails';
import {DdsProfiles} from '../components/DdsComposer';
import {useEffect,useState} from 'react';
import {api} from '../api/client';
import {Scenario,TrainingSession,User} from '../types';
import {ClassifierPanel} from '../components/ClassifierPanel';
import {AdminPanel} from '../components/AdminPanel';
import {GroupManager} from '../components/GroupManager';

export function TeacherDashboard({user}:{user:User}) {
 const [view,setView]=useState('sessions'),[query,setQuery]=useState(''),[showQa,setShowQa]=useState(false);
 const [scenarios,setScenarios]=useState<Scenario[]>([]);
 const [sessions,setSessions]=useState<TrainingSession[]>([]);
 const [reports,setReports]=useState<any[]>([]);
 const [summary,setSummary]=useState<any>(null),[groups,setGroups]=useState<any[]>([]),[groupId,setGroupId]=useState('');
 const [category,setCategory]=useState('ДТП');
 const [title,setTitle]=useState('Практическое занятие ДДС-112');
 const [selected,setSelected]=useState('');
 const [draft,setDraft]=useState<any>(null);
 const [message,setMessage]=useState('');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const load=async(includeQa=showQa)=>{const [sc,se,re,su,gr]=await Promise.all([api.scenarios(),api.sessions(),api.reports(),api.reportSummary(includeQa),api.groups()]);setScenarios(sc);setSessions(se);setReports(re);setSummary(su);setGroups(gr)};
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 useEffect(()=>{void run(load)},[]);
 const save=async()=>{await api.createScenario({...draft,code:'CUSTOM-'+crypto.randomUUID(),published:false,expected_state:{status:'ПРИНЯТО',services:['ДДС']}});setDraft(null);setMessage('Черновик сохранён. Проверьте его и опубликуйте.');await load()};
 const match=(text:string)=>text.toLocaleLowerCase('ru-RU').includes(query.trim().toLocaleLowerCase('ru-RU'));
 const visibleScenarios=scenarios.filter(s=>(showQa||!/^QA[- ]/i.test(s.code)&&!/^QA /i.test(s.title))&&match(s.title+' '+s.category));
 const visibleSessions=sessions.filter(s=>(showQa||!/^QA /i.test(s.title))&&match(s.title));
 const visibleReports=reports.filter(r=>(showQa||!/^QA /i.test(r.session)&&!/^QA /i.test(r.student))&&match(r.student+' '+r.session));
 return <section className="teacher-workspace"><h1>{user.role==='ADMIN'?'Панель администратора':'Панель преподавателя'}</h1>
 {error&&<div className="error" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}
 <button disabled={busy} onClick={()=>run(load)}>Обновить данные</button>
 <nav className="workspace-tabs" aria-label="Разделы преподавателя">{[['sessions','Занятия'],['students','Обучающиеся и службы'],['classifier','ЕКП и подготовка карточек'],['scenarios','Сценарии и эталоны'],['reports','Отчёты'],...(user.role==='ADMIN'?[['admin-users','Пользователи'],['system','Состояние системы']]:[])].map(([key,title])=><button key={key} aria-pressed={view===key} onClick={()=>{setView(key);setQuery('')}}>{title}</button>)}</nav>
 <div hidden={!['sessions','scenarios','reports'].includes(view)} className="teacher-filters"><label>Поиск<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Название занятия, сценария или имя"/></label><label className="check"><input type="checkbox" checked={showQa} onChange={e=>{const checked=e.currentTarget.checked;setShowQa(checked);void run(()=>load(checked))}}/>Показать записи автоматических проверок</label></div>
 <div hidden={view!=='students'}><GroupManager onChanged={load}/><DdsProfiles/></div>
 <div hidden={view!=='classifier'}><ClassifierPanel user={user} onCreated={load}/></div>
 {user.role==='ADMIN'&&view==='admin-users'&&<AdminPanel section="users" currentUser={user}/>}
 {user.role==='ADMIN'&&view==='system'&&<AdminPanel section="system" currentUser={user}/>}
 <fieldset disabled={busy}><div><div hidden={view!=='scenarios'} className="card"><h2>Сценарии</h2>
 <details><summary>Старые упражнения без маршрутизации ЕКП</summary><label>Категория<select value={category} onChange={e=>setCategory(e.target.value)}>{['ДТП','БПЛА','Ребенок в опасности','Прочие происшествия'].map(v=><option key={v}>{v}</option>)}</select></label>
 <button onClick={()=>run(async()=>{setDraft(await api.generate(category))})}>Сгенерировать AI</button>
 <p>Используется локальный mock AI. Перед публикацией проверьте содержание.</p>
 {draft&&<div className="card"><label>Название сценария<input value={draft.title} onChange={e=>setDraft({...draft,title:e.target.value})}/></label>
 <label>Описание происшествия<textarea value={draft.incident_payload.message} onChange={e=>setDraft({...draft,incident_payload:{...draft.incident_payload,message:e.target.value}})}/></label>
 <p>Эталон: {draft.category}, ПРИНЯТО, ДДС, все указанные теги, непустой комментарий.</p>
 <button onClick={()=>run(save)}>Сохранить черновик</button></div>}
 </details><ul className="scenario-list">{visibleScenarios.map(s=><li key={s.id}><b>{s.title}</b><span>{s.category} · {s.published?'Опубликован':'Черновик'} · v{s.version}</span>
 {s.incident_payload.mode==='DDS_MESSAGE'&&<RubricEditor key={s.id} scenario={s} onSaved={load}/>}
 {!s.published&&<button onClick={()=>run(async()=>{await api.publishScenario(s.id);await load()})}>Опубликовать</button>}</li>)}</ul></div>
 <div hidden={view!=='sessions'} className="card"><h2>Подготовка и проведение занятия</h2><label>Название<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
 <label>Учебная группа<select value={groupId} onChange={e=>setGroupId(e.target.value)}><option value="">Все обучающиеся</option>{groups.filter(group=>showQa||!/^QA\b/i.test(group.name)).map(group=><option key={group.id} value={group.id}>{group.name} ({group.members.length})</option>)}</select></label>
 <label>Сценарий<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Выберите сценарий</option>{scenarios.filter(s=>s.published&&s.incident_payload.mode==='DDS_MESSAGE'&&(showQa||!/^QA[- ]/i.test(s.code)&&!/^QA /i.test(s.title))).map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select></label>
 <button className="primary" disabled={!selected||!title.trim()} onClick={()=>run(async()=>{await api.createSession({title,group_id:groupId||null,scenario_ids:[selected]});setMessage('Занятие создано');await load()})}>Создать занятие</button>
 <ul className="session-list">{visibleSessions.map(s=><li key={s.id}><b>{s.title}</b><span>{({DRAFT:'Черновик',RUNNING:'Идёт занятие',COMPLETED:'Завершено',CANCELLED:'Отменено'} as any)[s.status]||s.status}{s.group_id?` · группа: ${groups.find(g=>g.id===s.group_id)?.name||'не найдена'}`:' · все обучающиеся'}</span>
 {s.status==='DRAFT'&&<button onClick={()=>run(async()=>{await api.startSession(s.id);await load()})}>Запустить</button>}
 {s.status==='RUNNING'&&<><button onClick={()=>run(async()=>{await api.finishSession(s.id);setMessage('Занятие завершено.');await load()})}>Завершить занятие</button><button className="danger-action" onClick={()=>{if(window.confirm('Досрочно завершить занятие? Все активные карточки будут закрыты и оценены по уже выполненным действиям.'))void run(async()=>{const result=await api.forceFinishSession(s.id);setMessage(`Занятие завершено досрочно. Закрыто активных карточек: ${result.forced_cards}.`);await load()})}}>Завершить досрочно</button></>}</li>)}</ul></div></div>
 <div hidden={view!=='reports'} className="card"><h2>Результаты и отчёты</h2>{summary&&<section className="progress-summary"><div className="system-status-grid"><div><small>Завершено карточек</small><b>{summary.total_results}</b></div><div><small>Обучающихся с результатами</small><b>{summary.students_count}</b></div><div><small>Средний результат</small><b>{summary.average_percent}%</b></div><div><small>Среднее время</small><b>{summary.average_duration} сек</b></div></div>
 {summary.students.length>0&&<><h3>Динамика обучающихся</h3>{summary.students.map((student:any)=><div className="student-progress" key={student.student_id}><div><b>{student.student}</b><small>{student.attempts} попыток · лучший результат {student.best_percent}% · превышений времени {student.overtime_count}</small></div><div className="progress-track" title={`Средний результат: ${student.average_percent}%`}><i style={{width:`${Math.min(100,student.average_percent)}%`}}/></div><strong>{student.average_percent}%</strong><div className="recent-results" aria-label="Последние результаты">{student.recent.map((result:any,index:number)=><i key={index} style={{height:`${Math.max(3,result.percent)}%`}} title={`${new Date(result.at).toLocaleDateString('ru-RU')}: ${result.percent}%`}/>)}</div></div>)}</>}</section>}{visibleReports.length===0&&<p>Завершённых карточек пока нет.</p>}
 {visibleReports.map(r=><div className="session" key={r.id}><div><b>{r.student} — {r.session}</b><p>{r.score} / {r.max_score} · {r.duration_sec} сек · {r.over_time?'Общее время превышено':'В пределах общего времени'}</p>
 {r.details.errors.map((e:any,i:number)=><p key={i}>{e.message}</p>)}</div><div className="row">
 <button onClick={()=>run(async()=>{await api.downloadReport(r.id,'csv')})}>CSV</button><button onClick={()=>run(async()=>{await api.downloadReport(r.id,'pdf')})}>PDF</button></div><AssessmentDetails id={r.id}/></div>)}</div></fieldset></section>
}
