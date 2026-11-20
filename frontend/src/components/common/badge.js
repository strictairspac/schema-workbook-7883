import {RUN_STATES,WITHDRAWAL_STATES} from '../../constants/enums.js';
import {esc} from '../../utils/html.js';
export const badge=value=>`<span class="badge ${esc(value)}">${esc(RUN_STATES[value]||value)}</span>`;
export const withdrawalBadge=value=>`<span class="badge ${esc(value)}">${esc(WITHDRAWAL_STATES[value]||value)}</span>`;