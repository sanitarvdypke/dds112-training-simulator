import React,{useEffect,useState} from 'react';
import {User} from '../types';
export function Layout({user,children,onLogout}:{user:User;children:React.ReactNode;onLogout:()=>void}){
 const [now,setNow]=useState(new Date());useEffect(()=>{const timer=setInterval(()=>setNow(new Date()),1000);return()=>clearInterval(timer)},[]);
 return <div className={'shell '+(user.role==='STUDENT'?'student-shell':'teacher-shell')}><header className="app-header"><div className="brand"><strong>112</strong><span>Учебный тренажёр <b>ДДС</b></span><small>Локальный контур</small></div><div className="user"><span>{user.full_name}<small>{({STUDENT:'Обучающийся',TEACHER:'Преподаватель',ADMIN:'Администратор'})[user.role]}</small></span><button onClick={onLogout}>Выйти</button><div className="system-clock"><small>{now.toLocaleDateString('ru-RU')}</small><time>{now.toLocaleTimeString('ru-RU')}</time></div></div></header><main>{children}</main><footer>Учебный контур системы 112 · реальные сообщения экстренным службам не отправляются</footer></div>
}
