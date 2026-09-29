import {DdsComposer} from './DdsComposer';
import {useEffect,useState} from 'react';
import {api} from '../api/client';
import {User} from '../types';

interface Issue {code:string;message:string;sheet?:string;row?:number;cell?:string}
interface Version {
 import_id:string;filename:string;status:string;format:string;created_by:string;created_at:string;
 source_sha256:string;statistics:Record<string,number>;validation_errors:Issue[];warnings:Issue[];
 metadata?:{services:{key:string;name:string}[];sheets:any[]};
}
interface Entry {
 id:string;code:string;title:string;source_sheet:string;source_row:number;
 group_name:string|null;features:Record<string,string|null>;response_scenario_code:string|null;
 lead_service_code:string|null;review_required:boolean;rule_count:number;
}
interface EntryDetails extends Entry {raw:Record<string,unknown>;formulas:Record<string,string>;rules:any[];warnings:Issue[]}

function Issues({items}:{items:Issue[]}) {
 return <ul>{items.map((item,i)=><li key={i}>{item.message}{item.sheet&&<span>{item.sheet}!{item.cell||('строка '+item.row)}</span>}</li>)}</ul>
}

export function ClassifierPanel({user,onCreated}:{user:User;onCreated:()=>Promise<void>}) {
 const [file,setFile]=useState<File|null>(null);
 const [versions,setVersions]=useState<Version[]>([]);
 const [versionOffset,setVersionOffset]=useState(0),[versionTotal,setVersionTotal]=useState(0);
 const [version,setVersion]=useState<Version|null>(null);
 const [entries,setEntries]=useState<Entry[]>([]);
 const [total,setTotal]=useState(0),[offset,setOffset]=useState(0);
 const [q,setQ]=useState(''),[service,setService]=useState(''),[reviewOnly,setReviewOnly]=useState(false);
 const [detail,setDetail]=useState<EntryDetails|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const refresh=async(next=versionOffset)=>{const r=await api.classifierImports(next);setVersions(r.items);setVersionTotal(r.total);setVersionOffset(next)};
 const search=async(id:string,start=0,query=q,svc=service,review=reviewOnly)=>{
  const params=new URLSearchParams({q:query,offset:String(start),limit:'25',review_only:String(review)});
  if(svc)params.set('service_key',svc);
  const r=await api.classifierEntries(id,params.toString());setEntries(r.items);setTotal(r.total);setOffset(start);setDetail(null);
 };
 const select=async(id:string)=>{
  setVersion(null);setEntries([]);setDetail(null);setTotal(0);setQ('');setService('');setReviewOnly(false);
  const v:Version=await api.classifier(id);setVersion(v);
  if(v.status==='COMMITTED'&&v.format==='ekp')await search(id,0,'','',false);
 };
 useEffect(()=>{void run(()=>refresh(0))},[]);
 const stats=version?.statistics;
 return <section className="card classifier"><h2>Классификатор ЕКП</h2>
 <p>Загрузите XLSX, проверьте замечания и сохраните версию. Откройте пункт ЕКП, чтобы подготовить карточку и выбрать получателей.</p>
 {error&&<div className="error" role="alert">{error}</div>}
 {busy&&<p role="status">Обработка данных…</p>}
 <fieldset disabled={busy}>
 <div className="row classifier-upload"><label>Файл классификатора (.xlsx, до 10 МБ)<input type="file" accept=".xlsx" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
 <button disabled={!file} onClick={()=>run(async()=>{if(!file)return;const r=await api.stageClassifier(file);await refresh(0);await select(r.import_id)})}>Проверить файл</button></div>
 <label>Загруженные версии<select value={version?.import_id||''} onChange={e=>{if(e.target.value)void run(()=>select(e.target.value))}}>
 <option value="">Выберите версию</option>{versions.map(v=><option key={v.import_id} value={v.import_id}>{new Date(v.created_at).toLocaleString('ru-RU')} · {v.filename} · {v.status==='COMMITTED'?'Сохранён':'Черновик'}</option>)}</select></label>
 <div className="row"><button onClick={()=>run(()=>refresh(0))}>Обновить версии</button><button disabled={versionOffset===0} onClick={()=>run(()=>refresh(Math.max(0,versionOffset-30)))}>Предыдущие версии</button><button disabled={versionOffset+30>=versionTotal} onClick={()=>run(()=>refresh(versionOffset+30))}>Следующие версии</button></div>
 {version&&<div>
 <h3>{version.filename}</h3><p>Формат: {version.format==='ekp'?'ЕКП':version.format==='legacy'?'Старый импорт — загрузите исходник повторно':'Обычная таблица, не справочник ЕКП'}.
 Состояние: {version.status==='COMMITTED'?'Сохранён в базе':'Проверен, ожидает сохранения'}.</p>
 {stats&&<p>Строк источника: {stats.source_rows??'—'} · Происшествий: {stats.incident_count??0} · Групп: {stats.group_count??0} · Служб: {stats.service_count??0} · Правил: {stats.rule_count??0}</p>}
 {version.validation_errors.length>0&&<div className="error"><b>Сохранение невозможно. Исправьте ошибки исходного файла:</b><Issues items={version.validation_errors}/></div>}
 {version.warnings.length>0&&<details className="classifier-warning"><summary>Замечания: {version.warnings.length}. Неоднозначные условия требуют уточнения.</summary><Issues items={version.warnings}/></details>}
 {version.status==='STAGED'&&<button className="primary" disabled={version.validation_errors.length>0||version.format==='legacy'||(user.role!=='ADMIN'&&version.created_by!==user.id)}
 onClick={()=>run(async()=>{await api.commitClassifier(version.import_id);await refresh(0);await select(version.import_id)})}>Сохранить версию в справочник</button>}
 <details><summary>Структура файла и контрольная сумма</summary><p className="hash">SHA-256: {version.source_sha256||'Нет в старом импорте'}</p>
 {version.metadata?.sheets.map((sheet:any)=><div key={sheet.name}><h4>{sheet.name}: {sheet.column_count??sheet.columns} столбцов, {sheet.rows} строк</h4>
 {Array.isArray(sheet.columns)&&<div className="table-scroll"><table><thead><tr><th>Столбец</th><th>Заголовок</th><th>Условие</th></tr></thead>
 <tbody>{sheet.columns.map((c:any)=><tr key={c.column}><td>{c.column}</td><td>{c.path.join(' / ')}</td><td>{c.condition_label||'—'}</td></tr>)}</tbody></table></div>}</div>)}</details>
 {version.status==='COMMITTED'&&version.format==='ekp'&&<>
 <h3>Происшествия</h3><div className="classifier-filters">
 <label>Код или название<input value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();void run(()=>search(version.import_id))}}}/></label>
 <label>Служба в матрице<select value={service} onChange={e=>setService(e.target.value)}><option value="">Все службы</option>{version.metadata?.services.map(s=><option key={s.key} value={s.key}>{s.name}</option>)}</select></label>
 <label className="check"><input type="checkbox" checked={reviewOnly} onChange={e=>setReviewOnly(e.target.checked)}/>С замечаниями</label>
 <button onClick={()=>run(()=>search(version.import_id))}>Найти</button></div>
 <p>Найдено: {total}. Наличие службы в матрице не означает безусловное направление ей карточки.</p>
 <div className="table-scroll"><table><thead><tr><th>Код</th><th>Происшествие</th><th>Группа</th><th>Сценарий реагирования</th><th>Источник</th><th>Правила</th></tr></thead>
 <tbody>{entries.map(entry=><tr key={entry.id}><td>{entry.code}</td><td>{entry.title}{entry.review_required&&<span className="review-label">Есть условия для уточнения</span>}</td><td>{entry.group_name}</td><td>{entry.response_scenario_code||'Не задан'}</td><td>{entry.source_sheet}, строка {entry.source_row}</td><td><button onClick={()=>run(async()=>setDetail(await api.classifierEntry(version.import_id,entry.id)))}>Открыть</button></td></tr>)}</tbody></table></div>
 {total===0&&<p>Ничего не найдено.</p>}
 <div className="row"><button disabled={offset===0} onClick={()=>run(()=>search(version.import_id,Math.max(0,offset-25)))}>Назад</button><span>{total?offset+1:0}–{Math.min(offset+25,total)} из {total}</span><button disabled={offset+25>=total} onClick={()=>run(()=>search(version.import_id,offset+25))}>Далее</button></div>
 {detail&&<div className="classifier-detail"><h3>{detail.code} — {detail.title}</h3>
 <DdsComposer key={detail.id} entry={detail} onCreated={onCreated}/>
 <p>Главная служба (код источника): {detail.lead_service_code||'Не задана'}</p>
 <p>Признаки: {Object.entries(detail.features).map(([k,v])=>k+': '+(v||'—')).join('; ')}</p>
 <Issues items={detail.warnings}/>
 <div className="table-scroll"><table><thead><tr><th>Ячейка</th><th>Служба / канал</th><th>Условие источника</th><th>Значение</th></tr></thead>
 <tbody>{detail.rules.map((rule:any)=><tr key={rule.source_cell}><td>{rule.source_cell}</td><td>{rule.service_name}{rule.channel&&<span>{rule.channel}</span>}</td><td>{rule.condition_label||'Без дополнительного условия в таблице'}{rule.condition.review_required&&<b className="review-label">Требует уточнения</b>}</td><td>{rule.effect==='NO_RESPONSE'?<b>Нет реагирования</b>:rule.classification}</td></tr>)}</tbody></table></div>
 <details><summary>Все исходные ячейки строки ({Object.keys(detail.raw).length})</summary><div className="table-scroll"><table><thead><tr><th>Ячейка</th><th>Значение</th><th>Формула источника</th></tr></thead>
 <tbody>{Object.entries(detail.raw).sort(([a],[b])=>a.length-b.length||a.localeCompare(b)).map(([column,value])=><tr key={column}><td>{column}{detail.source_row}</td><td>{value===null?'—':String(value)}</td><td>{detail.formulas[column]||'—'}</td></tr>)}</tbody></table></div></details>
 </div>}
 </>}
 </div>}
 </fieldset></section>
}
