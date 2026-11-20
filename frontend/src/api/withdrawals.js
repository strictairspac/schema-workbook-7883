import {api} from './client.js';
export const withdrawalsApi={list:()=>api('/withdrawals'),create:data=>api('/withdrawals','POST',data),resume:id=>api('/withdrawals/'+id+'/resume','POST',{})};
