import {serviceLabel,unresolvedService,technicalStudent} from './serviceLabels';
import {useEffect,useState} from 'react';
import {api} from '../api/client';

export const factLabels:Record<string,string>={no_access:'Нет доступа',threat_to_people:'Угроза людям',casualties:'Пострадавшие',offense:'Правонарушение',casualties_not_on_scene:'Пострадавшие вне места происшествия',gasified:'Газифицированный объект',medical_help:'Нужна медицинская помощь',evacuation:'Эвакуация',road_blocked:'Движение перекрыто',tunnel:'Тоннель',communications_facility:'Объект связи',construction:'Строительные работы'};

export function DdsProfiles(){
 const [students,setStudents]=useState<any[]>([]),[services,setServices]=useState<any[]>([]);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [showTechnical,setShowTechnical]=useState(false),[showUnknown,setShowUnknown]=useState(false),[query,setQuery]=useState('');
 const load=async()=>{const [a,b]=await Promise.all([api.ddsStudents(),api.ddsServices()]);setStudents(a);setServices(b)};
 const refresh=async()=>{setBusy(true);setError('');try{await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 useEffect(()=>{void refresh()},[]);
 const technicalCount=students.filter(technicalStudent).length;
 const unknownCount=services.filter(s=>unresolvedService(s.name)).length;
 const displayed=students.filter(s=>showTechnical||!technicalStudent(s));
 const choices=services.filter(s=>(showUnknown||!unresolvedService(s.name))&&(serviceLabel(s.name)+' '+s.name).toLocaleLowerCase('ru-RU').includes(query.trim().toLocaleLowerCase('ru-RU'))).sort((a,b)=>serviceLabel(a.name).localeCompare(serviceLabel(b.name),'ru'));
 return <div className="card"><h2>Какую службу представляет обучающийся</h2><p>Выберите службу, за диспетчера которой будет работать ученик. Ему будут доступны карточки происшествий, направленные этой службе. Во время работы с карточкой сменить службу нельзя.</p>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
 <div className="inbox-toolbar"><label>Поиск службы<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Например: полиция, скорая, газ"/></label><button disabled={busy} onClick={refresh}>Обновить список</button></div>
 {technicalCount>0&&<label className="check"><input type="checkbox" checked={showTechnical} onChange={e=>setShowTechnical(e.target.checked)}/>Показать технические учётные записи ({technicalCount})</label>}
 {unknownCount>0&&<label className="check"><input type="checkbox" checked={showUnknown} onChange={e=>setShowUnknown(e.target.checked)}/>Показать нераспознанные службы из импортов ({unknownCount})</label>}
 {!choices.length&&<p>Службы по этому запросу не найдены. Текущее назначение ученика сохраняется.</p>}
 {displayed.map(student=>{const assigned=services.find(s=>s.key===student.dds_service_key);const outside=assigned&&!choices.some(s=>s.key===assigned.key);return <div className="dds-profile" key={student.id}>
 <h3>{student.email==='student@example.local'?'Демонстрационный обучающийся':student.full_name}{technicalStudent(student)&&' — техническая запись'}</h3><p>Логин: {student.email}</p>
 <label>Служба обучающегося<select disabled={busy} value={student.dds_service_key||''} onChange={async e=>{const key=e.target.value;setBusy(true);setError('');setNotice('');try{await api.ddsProfile(student.id,key);await load();setNotice('Назначена служба: '+serviceLabel(services.find(s=>s.key===key)?.name||key))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>
 <option value="" disabled>Выберите службу</option>
 {outside&&<optgroup label="Текущее назначение"><option value={assigned.key}>{serviceLabel(assigned.name)}</option></optgroup>}
 {student.dds_service_key&&!assigned&&<option value={student.dds_service_key}>Назначенная служба отсутствует в справочнике</option>}
 {choices.map(s=><option key={s.key} value={s.key}>{serviceLabel(s.name)}</option>)}</select></label>
 {assigned&&<small>Название в исходном ЕКП: {assigned.name.replace(/\s+/g,' ').trim()}</small>}
 {!assigned&&!student.dds_service_key&&<p>Служба пока не назначена.</p>}
 </div>})}
 {!displayed.length&&!busy&&<p>Обучающиеся не найдены.</p>}
 </div>
}

export function DdsComposer({entry,onCreated}:{entry:any;onCreated:()=>Promise<void>}){
 const [facts,setFacts]=useState<Record<string,boolean>>({}),[preview,setPreview]=useState<any>(null);
 const [recipients,setRecipients]=useState<string[]>([]),[reason,setReason]=useState('');
 const [title,setTitle]=useState(entry.title.slice(0,255)),[address,setAddress]=useState(''),[message,setMessage]=useState('');
 const [limit,setLimit]=useState(120),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const features=Array.from(new Set<string>(entry.rules.flatMap((r:any)=>r.condition.feature?[r.condition.feature]:r.condition.features||[])));
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <div className="card"><h3>Подготовить карточку 112 по этому пункту ЕКП</h3>
 <p>Заполните сведения, рассчитайте получателей и проверьте решение. Сценарий сохраняется черновиком.</p>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 <fieldset disabled={busy}><label>Название<input value={title} maxLength={255} onChange={e=>setTitle(e.target.value)}/></label>
 <label>Адрес<input value={address} onChange={e=>setAddress(e.target.value)}/></label><label>Описание происшествия<textarea value={message} onChange={e=>setMessage(e.target.value)}/></label>
 <label>Норматив, секунд<input type="number" min={1} max={3600} value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label>
 {features.map(f=><label key={f}>{factLabels[f]||f}<select value={facts[f]===undefined?'':String(facts[f])} onChange={e=>{const next={...facts};if(e.target.value==='')delete next[f];else next[f]=e.target.value==='true';setFacts(next);setPreview(null);setRecipients([]);setReason('')}}><option value="">Не определено</option><option value="true">Да</option><option value="false">Нет</option></select></label>)}
 <button onClick={()=>run(async()=>{const p=await api.routingPreview({entry_id:entry.id,facts});setPreview(p);setRecipients(p.recipients.map((s:any)=>s.key));setReason('')})}>Рассчитать получателей</button>
 {preview&&<><p>Неопределённых условий: {preview.pending_cells.length}. {preview.review_required?'Необходимо пояснение преподавателя.':'Условия рассчитаны.'}</p>
 <details><summary>Проверить основания расчёта</summary>{preview.evidence.map((r:any)=><p key={r.source_cell}>{r.source_cell}: {r.service_name} · {r.condition_label||'Без условия'} · {r.effect==='NO_RESPONSE'?'Нет реагирования':r.classification} · {r.match===null?'Нужно уточнение':r.match?'Условие выполнено':'Условие не выполнено'}</p>)}</details>
 <h4>Получатели карточки</h4>{preview.services.map((s:any)=><label className="check" key={s.key}><input type="checkbox" checked={recipients.includes(s.key)} onChange={()=>setRecipients(recipients.includes(s.key)?recipients.filter(k=>k!==s.key):[...recipients,s.key])}/>{serviceLabel(s.name)}</label>)}
 <label>Пояснение решения по неоднозначным правилам / изменению получателей<textarea value={reason} onChange={e=>setReason(e.target.value)}/></label>
 <button className="primary" disabled={!recipients.length||!title.trim()||!address.trim()||!message.trim()||!Number.isInteger(limit)||limit<1||limit>3600} onClick={()=>run(async()=>{await api.createDdsScenario({entry_id:entry.id,facts,title,address,message,time_limit_sec:limit,recipients,review_reason:reason});setPreview(null);setRecipients([]);await onCreated();setNotice('Черновик карточки сохранён. Откройте «Сценарии и эталоны», утвердите эталон и опубликуйте сценарий. Затем создайте занятие во вкладке «Занятия».')})}>Сохранить сценарий карточки</button></>}
 </fieldset></div>
}
