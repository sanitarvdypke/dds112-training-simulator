import {useState} from 'react';
import {api} from '../api/client';
const statuses=['ПРИНЯТО','НЕ ПРИНЯТО','НАЧАЛО РЕАГИРОВАНИЯ','ПРИБЫТИЕ','ПРОВЕДЕНИЕ РАБОТ','ОТКАЗ ОТ ВЫПОЛНЕНИЯ РАБОТ','РАБОТЫ ЗАВЕРШЕНЫ'];
const fields:Record<string,string>={unit:'Подразделение',responsible:'Ответственный',measures:'Принятые меры',outcome:'Результат работ'};
const initial={steps:[{status:'ПРИНЯТО',weight:2,within_sec:30,anchor:'RECEIVED',require_comment:false},{status:'НАЧАЛО РЕАГИРОВАНИЯ',weight:2,within_sec:120,anchor:'PREVIOUS',require_comment:false},{status:'РАБОТЫ ЗАВЕРШЕНЫ',weight:2,within_sec:300,anchor:'PREVIOUS',require_comment:false}],total_time_sec:600,require_comment:true,required_fields:['measures','outcome']};

export function RubricEditor({scenario,onSaved}:{scenario:any;onSaved:()=>Promise<void>}){
 const [open,setOpen]=useState(false);
 const [rubric,setRubric]=useState<any>(scenario.expected_state.rubric||initial),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const update=(i:number,patch:any)=>setRubric({...rubric,steps:rubric.steps.map((s:any,n:number)=>n===i?{...s,...patch}:s)});
 const move=(i:number,delta:number)=>{const steps=[...rubric.steps];[steps[i],steps[i+delta]]=[steps[i+delta],steps[i]];steps[0]={...steps[0],anchor:'RECEIVED'};setRubric({...rubric,steps})};
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <details className="card" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Эталон и нормативы: {scenario.title}</summary>
 {open&&<><p>{scenario.expected_state.rubric_approval?'Эталон утверждён '+new Date(scenario.expected_state.rubric_approval.approved_at).toLocaleString('ru-RU'):scenario.expected_state.rubric?'Требуется утверждение':'Пока используется прежняя базовая оценка. Ниже предложен шаблон для утверждения.'}</p>
 <p>Строки задают обязательный порядок. Для оценки используется первое появление каждого статуса. Повтор не отменяет ошибку порядка или опоздание. Баллы строки начисляются при соблюдении всех её условий; дополнительные статусы не штрафуются. Общее превышение времени фиксируется отдельно без дополнительного снятия баллов.</p>
 {error&&<p className="error">{error}</p>}{message&&<p className="notice">{message}</p>}
 {scenario.published&&<button disabled={busy} onClick={()=>run(async()=>{await api.cloneScenario(scenario.id);await onSaved();setMessage('Создан отдельный черновик. Найдите сценарий с пометкой «копия» и утвердите его эталон.')})}>Создать копию для изменения</button>}
 <fieldset disabled={busy||scenario.published}>
 {rubric.steps.map((step:any,i:number)=><div className="card" key={i}><h4>Шаг {i+1}</h4><label>Статус<select value={step.status} onChange={e=>update(i,{status:e.target.value})}>{statuses.map(s=><option key={s}>{s}</option>)}</select></label>
 <div className="grid two"><label>Баллы<input type="number" min={1} max={20} value={step.weight} onChange={e=>update(i,{weight:Number(e.target.value)})}/></label><label>Норматив, сек (пусто — без срока)<input type="number" min={1} max={3600} value={step.within_sec??''} onChange={e=>update(i,{within_sec:e.target.value?Number(e.target.value):null})}/></label></div>
 <label>Начало отсчёта<select value={step.anchor} onChange={e=>update(i,{anchor:e.target.value})}><option value="RECEIVED">Получение карточки</option>{i>0&&<option value="PREVIOUS">Предыдущий обязательный статус</option>}</select></label>
 <label className="check"><input type="checkbox" checked={step.require_comment} onChange={e=>update(i,{require_comment:e.target.checked})}/>Комментарий к статусу обязателен</label>
 <button disabled={i===0} onClick={()=>move(i,-1)}>Выше</button><button disabled={i===rubric.steps.length-1} onClick={()=>move(i,1)}>Ниже</button><button disabled={rubric.steps.length===1} onClick={()=>{const steps=rubric.steps.filter((_:any,n:number)=>n!==i);steps[0]={...steps[0],anchor:'RECEIVED'};setRubric({...rubric,steps})}}>Удалить шаг</button></div>)}
 <button disabled={rubric.steps.length===7} onClick={()=>{const status=statuses.find(s=>!rubric.steps.some((r:any)=>r.status===s));if(status)setRubric({...rubric,steps:[...rubric.steps,{status,weight:2,within_sec:null,anchor:'PREVIOUS',require_comment:false}]})}}>Добавить шаг</button>
 <label>Общий норматив практики, сек<input type="number" min={1} max={3600} value={rubric.total_time_sec} onChange={e=>setRubric({...rubric,total_time_sec:Number(e.target.value)})}/></label>
 <label className="check"><input type="checkbox" checked={rubric.require_comment} onChange={e=>setRubric({...rubric,require_comment:e.target.checked})}/>Отдельный комментарий диспетчера (1 балл)</label>
 <p>Обязательные поля ДДС: по 1 баллу за непустое итоговое значение.</p>{Object.entries(fields).map(([key,label])=><label className="check" key={key}><input type="checkbox" checked={rubric.required_fields.includes(key)} onChange={()=>setRubric({...rubric,required_fields:rubric.required_fields.includes(key)?rubric.required_fields.filter((v:string)=>v!==key):[...rubric.required_fields,key]})}/>{label}</label>)}
 <button className="primary" onClick={()=>run(async()=>{await api.approveRubric(scenario.id,rubric);await onSaved();setMessage('Эталон утверждён. Теперь опубликуйте сценарий.')})}>Сохранить и утвердить эталон</button>
 </fieldset></>}</details>
}
