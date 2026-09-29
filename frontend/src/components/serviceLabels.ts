// Presentation only: keys and original EKP names must remain unchanged.
const labels:Record<string,string>={
 'Классификатор МВД':'Полиция (МВД)',
 'Классификатор СМП':'Скорая медицинская помощь (СМП)',
 'Классификатор МОСГАЗ':'Газовая служба — МОСГАЗ',
 'Классификатор Мособлгаз':'Газовая служба — Мособлгаз',
 'Классификатор ФСБ':'ФСБ',
 'Служба 101':'Пожарная охрана — 101',
 'Гор. Хозяйство':'Городское хозяйство',
 'ДГП (Департамент градостроительной политики)':'Департамент градостроительной политики (ДГП)',
 'МОЭСК (ПАО "Россети Московский регион")':'Россети Московский регион (МОЭСК)',
 'Метро':'Метрополитен',
};
export function serviceLabel(name:string){const clean=name.replace(/\s+/g,' ').trim();return labels[clean]||clean}
export function unresolvedService(name:string){return name.startsWith('Неизвестная служба')}
export function technicalStudent(student:{email:string;full_name:string}){
 return student.full_name==='QA ДДС'&&/^qa-dds-[0-9a-f-]{36}@example\.local$/i.test(student.email);
}
