import { createInterface } from 'node:readline';
import { uploadApproved, verifyStored } from './client.mjs';
const lines=createInterface({input:process.stdin,crlfDelay:Infinity})[Symbol.asyncIterator]();
const send=data=>process.stdout.write(JSON.stringify(data,(_k,v)=>typeof v==='bigint'?v.toString():v)+'\n');
try {
 const input=JSON.parse((await lines.next()).value);
 const receipt=input.receipt ? await verifyStored(input,input.receipt) : await uploadApproved(input,async data=>{send({event:'sign',data});const reply=JSON.parse((await lines.next()).value);if(typeof reply.signature!=='string')throw Error('Signing denied');return reply.signature;});
 send({event:'complete',receipt});
}catch(e){send({event:'error',error:e.message});process.exitCode=1;}
process.stdin.destroy();
