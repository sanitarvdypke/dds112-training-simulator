import {useEffect,useState} from 'react';
import {api} from '../api/client';
import {Role,User} from '../types';

const roleLabel:Record<Role,string>={ADMIN:'Администратор',TEACHER:'Преподаватель',STUDENT:'Обучающийся'};
const gigabytes=(value:number|null|undefined)=>value==null?'—':`${(value/1024/1024/1024).toFixed(1)} ГБ`;

export function AdminPanel({section,currentUser}:{section:'users'|'system';currentUser:User}){
 const [users,setUsers]=useState<any[]>([]),[status,setStatus]=useState<any>(null);
 const [form,setForm]=useState({email:'',full_name:'',password:'',role:'STUDENT' as Role});
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const load=async()=>{if(section==='users')setUsers(await api.adminUsers());else setStatus(await api.systemStatus())};
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 useEffect(()=>{void run(load)},[section]);
 if(section==='system')return <section className="card"><h2>Состояние локального комплекса</h2>{error&&<p className="error" role="alert">{error}</p>}<button disabled={busy} onClick={()=>run(load)}>Обновить состояние</button>{status&&<div className="system-status-grid">
  <div><small>Общее состояние</small><b>{status.status==='ok'?'Работает':'Ошибка'}</b></div><div><small>База данных</small><b>{status.database==='available'?'Доступна':status.database}</b></div>
  <div><small>Активные пользователи</small><b>{status.users.active} / {status.users.total}</b></div><div><small>События аудита</small><b>{status.audit_events}</b></div>
  <div><small>Занятия</small><b>идут: {status.sessions.RUNNING}, завершены: {status.sessions.COMPLETED}</b></div><div><small>Контур</small><b>{status.mode}</b></div>
  <div><small>ИИ</small><b>{status.providers.ai==='mock'?'Учебная модель (mock)':status.providers.ai}</b></div><div><small>Телефонный вызов</small><b>Отключён для карточек ДДС</b></div>
  {status.host&&<><div><small>Процессор</small><b>{status.host.cpu_count} ядер</b><small>нагрузка: {status.host.load_average?.join(' / ')||'—'}</small></div><div><small>Оперативная память</small><b>{gigabytes(status.host.memory_available_bytes)} свободно</b><small>из {gigabytes(status.host.memory_total_bytes)}</small></div><div><small>Диск</small><b>{gigabytes(status.host.disk_free_bytes)} свободно</b><small>из {gigabytes(status.host.disk_total_bytes)}</small></div></>}
 </div>}<p>Экран показывает текущее состояние приложения, базы и ресурсов контейнера. Автоматические оповещения требуют отдельной системы мониторинга.</p></section>;
 return <section className="card"><h2>Пользователи и роли</h2><p>Администратор может создать учётную запись, назначить роль и временно заблокировать вход. Пароль показывается только при создании.</p>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
 <fieldset disabled={busy}><div className="grid two"><label>Логин (email)<input type="email" autoComplete="off" value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></label><label>Имя<input value={form.full_name} onChange={e=>setForm({...form,full_name:e.target.value})}/></label><label>Начальный пароль<input type="password" minLength={8} autoComplete="new-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></label><label>Роль<select value={form.role} onChange={e=>setForm({...form,role:e.target.value as Role})}>{Object.entries(roleLabel).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
 <button className="primary" disabled={!form.email.trim()||!form.full_name.trim()||form.password.length<8} onClick={()=>run(async()=>{await api.createAdminUser(form);setForm({email:'',full_name:'',password:'',role:'STUDENT'});setNotice('Пользователь создан.');await load()})}>Создать пользователя</button></fieldset>
 <div className="table-scroll"><table><thead><tr><th>Имя и логин</th><th>Роль</th><th>Состояние</th><th>Действия</th></tr></thead><tbody>{users.map(row=><tr key={row.id}><td><b>{row.full_name}</b><small>{row.email}</small></td><td><select disabled={busy||row.id===currentUser.id} aria-label={'Роль '+row.email} value={row.role} onChange={e=>run(async()=>{await api.updateAdminUser(row.id,{role:e.target.value});setNotice('Роль изменена.');await load()})}>{Object.entries(roleLabel).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></td><td>{row.is_active?'Активен':'Заблокирован'}</td><td><button disabled={busy||row.id===currentUser.id} onClick={()=>run(async()=>{await api.updateAdminUser(row.id,{is_active:!row.is_active});setNotice(row.is_active?'Вход пользователя заблокирован.':'Доступ пользователя восстановлен.');await load()})}>{row.is_active?'Заблокировать':'Разблокировать'}</button></td></tr>)}</tbody></table></div></section>;
}
