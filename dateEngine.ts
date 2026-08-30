// lib/dateEngine.ts - compute occurrences for 2026-2030
export type Logic = "fixed"|"fixed_local"|"fixed_month"|"movable_nth"|"movable_liturgical"|"movable_lunar"|"movable"|"tba_government"|"tba_academic"|"tba"
export function getEaster(year:number):Date{
  // Anonymous Gregorian algorithm
  const a=year%19, b=Math.floor(year/100), c=year%100, d=Math.floor(b/4), e=b%4, f=Math.floor((b+8)/25), g=Math.floor((b-f+1)/3), h=(19*a+b-d-g+15)%30, i=Math.floor(c/4), k=c%4, l=(32+2*e+2*i-h-k)%7, m=Math.floor((a+11*h+22*l)/451), month=Math.floor((h+l-7*m+114)/31), day=((h+l-7*m+114)%31)+1;
  return new Date(year, month-1, day)
}
export function nthWeekday(year:number, month:number, weekday:number, n:number| "last"):Date{
  // weekday 0=Sun ...6=Sat
  if(n==="last"){ const last=new Date(year, month,0); while(last.getDay()!==weekday) last.setDate(last.getDate()-1); return last }
  const first=new Date(year, month-1,1); let offset=(weekday-first.getDay()+7)%7; let day=1+offset+(Number(n)-1)*7; return new Date(year, month-1, day)
}
export function addDays(d:Date, days:number){ const r=new Date(d); r.setDate(r.getDate()+days); return r }
export function occurrencesForYear(logic:string, year:number, month?:number, day?:number, rule?:any):Date|null{
  if(logic==="fixed" && month && day) return new Date(year, month-1, day)
  if(logic==="movable_nth" && rule) return nthWeekday(year, rule.month, rule.weekday, rule.n)
  if(logic==="movable_liturgical"){ const e=getEaster(year); if(rule?.anchor==="EASTER") return addDays(e, rule.offset) }
  return null
}
