import {useState} from 'react';
import {api} from '../api/client';
export function AssessmentDetails({id}:{id:string}){
 const [data,setData]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 return <div className="report-details"><button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{setData(await api.report(id))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Подробный отчёт</button>
 {error&&<p className="error">{error}</p>}{data&&<div className="card"><button onClick={()=>setData(null)}>Скрыть</button><h3>Оценка по критериям</h3>
 {data.details.rubric_approval&&<p>Эталон утверждён: {new Date(data.details.rubric_approval.approved_at).toLocaleString('ru-RU')} · версия сценария {data.details.summary?.scenario_version}</p>}
 {data.details.criteria?.map((c:any,i:number)=><p key={i}><b>{c.label}: {c.score} / {c.max_score}</b>{'elapsed_sec' in c&&<> · факт {c.elapsed_sec??'нет события'} сек · норматив {c.limit_sec??'не задан'} · {c.anchor==='RECEIVED'?'от получения':'от предыдущего обязательного события'} · опоздание {c.deviation_sec??'—'} сек</>}</p>)}
 {!data.details.criteria&&<p>Результат рассчитан по прежнему базовому эталону.</p>}
 <p>Превышение общего времени: {data.details.total_deviation_sec??(data.over_time?'да':'нет')}{data.details.total_deviation_sec!==undefined?' сек':''}</p>
 <h3>Журнал действий</h3>{data.details.history?.map((event:any)=><div key={event.id} className="card"><p>{new Date(event.occurred_at).toLocaleString('ru-RU')} · {event.actor} · {event.service}</p><b>{event.payload.status||({ADDED:'Добавлена',RECEIVED:'Получена',COMPLETED:'Практика завершена',UPDATE_DDS:'Сведения ДДС',TEXT_INPUT:'Комментарий'} as any)[event.action_type]||event.action_type}</b><p className="preserve-text">{event.payload.comment||event.payload.text||''}</p>{event.payload.fields&&<pre className="preserve-text">{JSON.stringify(event.payload.fields,null,2)}</pre>}</div>)}
 {!data.details.history&&<p>В старом результате снимок журнала не сохранён.</p>}<p>Проверка текста (mock AI): {data.ai_feedback.grammar_issues?.join('; ')||'Замечаний не найдено.'}</p></div>}</div>
}
