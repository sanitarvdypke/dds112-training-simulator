import {useEffect,useState} from 'react';
import {api} from '../api/client';
import {technicalStudent} from './serviceLabels';

export function GroupManager({onChanged}:{onChanged:()=>Promise<void>}){
 const [groups,setGroups]=useState<any[]>([]),[students,setStudents]=useState<any[]>([]),[name,setName]=useState('');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[showTechnical,setShowTechnical]=useState(false),[showTechnicalGroups,setShowTechnicalGroups]=useState(false);
 const load=async()=>{const [g,s]=await Promise.all([api.groups(),api.ddsStudents()]);setGroups(g);setStudents(s)};
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 useEffect(()=>{void run(load)},[]);
 const visibleStudents=students.filter(s=>showTechnical||!technicalStudent(s));
 const technicalGroups=groups.filter(group=>/^QA\b/i.test(group.name));
 const visibleGroups=groups.filter(group=>showTechnicalGroups||!/^QA\b/i.test(group.name));
 const toggle=(group:any,studentId:string)=>{const ids=group.members.map((m:any)=>m.id);const member_ids=ids.includes(studentId)?ids.filter((id:string)=>id!==studentId):[...ids,studentId];setGroups(groups.map(g=>g.id===group.id?{...g,members:students.filter(s=>member_ids.includes(s.id))}:g))};
 return <div className="card"><h2>Учебные группы</h2><p>Сформируйте состав группы, затем выберите её при создании занятия. Карточки такого занятия увидят только участники группы.</p>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
 <fieldset disabled={busy}><div className="row"><input aria-label="Название новой группы" value={name} maxLength={200} onChange={e=>setName(e.target.value)} placeholder="Например: ДДС МВД — поток 1"/><button className="primary" disabled={name.trim().length<2} onClick={()=>run(async()=>{await api.createGroup({name,member_ids:[]});setName('');setNotice('Группа создана.');await load();await onChanged()})}>Создать группу</button></div>
 {students.some(technicalStudent)&&<label className="check"><input type="checkbox" checked={showTechnical} onChange={e=>setShowTechnical(e.target.checked)}/>Показать технические учётные записи</label>}
 {technicalGroups.length>0&&<label className="check"><input type="checkbox" checked={showTechnicalGroups} onChange={e=>setShowTechnicalGroups(e.target.checked)}/>Показать группы автоматических проверок ({technicalGroups.length})</label>}
 {visibleGroups.length===0&&<p>Пользовательские учебные группы пока не созданы.</p>}
 {visibleGroups.map(group=><section className="group-editor" key={group.id}><div className="group-heading"><label>Название<input value={group.name} onChange={e=>setGroups(groups.map(g=>g.id===group.id?{...g,name:e.target.value}:g))}/></label><span>{group.members.length} участн.</span></div>
 <div className="group-members">{visibleStudents.map(student=><label className="check" key={student.id}><input type="checkbox" checked={group.members.some((m:any)=>m.id===student.id)} onChange={()=>toggle(group,student.id)}/><span>{student.full_name}<small>{student.email}</small></span></label>)}</div>
 <div className="row"><button className="primary" disabled={group.name.trim().length<2} onClick={()=>run(async()=>{await api.updateGroup(group.id,{name:group.name,member_ids:group.members.map((m:any)=>m.id)});setNotice('Состав группы сохранён.');await load();await onChanged()})}>Сохранить состав</button><button className="danger-action" onClick={()=>{if(window.confirm(`Удалить группу «${group.name}»?`))void run(async()=>{await api.deleteGroup(group.id);setNotice('Группа удалена.');await load();await onChanged()})}}>Удалить</button></div></section>)}</fieldset></div>
}
