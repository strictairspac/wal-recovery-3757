import {api} from './client.js';
const query=params=>{const search=new URLSearchParams();for(const [key,value] of Object.entries(params||{}))if(value!==undefined&&value!==null&&value!=='')search.set(key,value);const text=search.toString();return text?'?'+text:'';};
export const logSetsAPI={list:()=>api('/log-sets'),create:data=>api('/log-sets',{method:'POST',body:JSON.stringify(data)}),
 readings:(id,params)=>api('/log-sets/'+id+'/readings'+query(params)),
 handovers:(id,params)=>api('/log-sets/'+id+'/handovers'+query(params)),
 correct:(id,data)=>api('/log-sets/'+id+'/corrections',{method:'POST',body:JSON.stringify(data)})};
export const crashCasesAPI={list:()=>api('/crash-cases'),create:data=>api('/crash-cases',{method:'POST',body:JSON.stringify(data)}),
 readings:(id,params)=>api('/crash-cases/'+id+'/readings'+query(params)),
 handovers:(id,params)=>api('/crash-cases/'+id+'/handovers'+query(params))};
export const recoveriesAPI={list:()=>api('/recoveries'),get:id=>api('/recoveries/'+id),create:data=>api('/recoveries',{method:'POST',body:JSON.stringify(data)}),
 readings:(id,params)=>api('/recoveries/'+id+'/readings'+query(params)),
 handovers:(id,params)=>api('/recoveries/'+id+'/handovers'+query(params))};
