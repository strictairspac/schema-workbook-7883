import {withdrawalsApi} from '../api/withdrawals.js';
export const withdrawalsStore={items:[],async refresh(){this.items=await withdrawalsApi.list();return this.items;}};
