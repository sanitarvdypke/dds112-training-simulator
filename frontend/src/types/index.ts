export type Role='ADMIN'|'TEACHER'|'STUDENT';
export interface User{ id:string; email:string; full_name:string; role:Role; dds_service_key?:string; is_active?:boolean }
export interface Scenario{ id:string; code:string; title:string; category:string; difficulty:number; participant_role:string; incident_payload:Record<string,unknown>; expected_state:Record<string,unknown>; published:boolean; version:number }
export interface TrainingSession{ id:string; title:string; status:string; group_id?:string|null; scenario_ids:string[] }
export interface CallState{call_id:string; card_id:string; scenario:string; body:Record<string,unknown>; time_limit_sec:number;started_at:string;actions:{action_type:string;payload:any}[]}
