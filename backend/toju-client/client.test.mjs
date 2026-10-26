import test from 'node:test';
import assert from 'node:assert/strict';
import { validateChallenge, validateTypedData, verifyStored, uploadApproved } from './client.mjs';
import { encodePaymentRequiredHeader, encodePaymentResponseHeader } from '@x402/core/http';
import { createHash } from 'node:crypto';
import { NETWORK, USDC } from './policy.mjs';
const approved={amount:'1',payTo:'0x'+'1'.repeat(40),url:'https://example.test/upload/agent?sha256=abc',address:'0x'+'2'.repeat(40)};
const required=()=>({x402Version:2,resource:{url:approved.url},accepts:[{scheme:'exact',network:NETWORK,asset:USDC,amount:'1',payTo:approved.payTo,maxTimeoutSeconds:120,extra:{name:'USDC',version:'2'}}]});
test('rejects malicious challenges before any signature',()=>{
 assert.doesNotThrow(()=>validateChallenge(required(),approved));
 for(const [key,value] of [['network','eip155:8453'],['asset','0x'+'3'.repeat(40)],['payTo','0x'+'4'.repeat(40)],['amount','2'],['amount','-1'],['maxTimeoutSeconds',9999]]) {const r=required();r.accepts[0][key]=value;assert.throws(()=>validateChallenge(r,approved));}
 const r=required();r.resource.url='https://attacker.test/';assert.throws(()=>validateChallenge(r,approved));
});
test('validates typed payment and denies arbitrary contract signatures',()=>{
 const data={domain:{name:'USDC',version:'2',chainId:84532,verifyingContract:USDC},primaryType:'TransferWithAuthorization',message:{from:approved.address,to:approved.payTo,value:'1',validAfter:'0',validBefore:String(Math.floor(Date.now()/1000)+120),nonce:'0x'+'a'.repeat(64)}};
 assert.doesNotThrow(()=>validateTypedData(data,approved));
 assert.throws(()=>validateTypedData({...data,primaryType:'Permit'},approved));
 assert.throws(()=>validateTypedData({...data,message:{...data.message,to:'0x'+'3'.repeat(40)}},approved));
 assert.throws(()=>validateTypedData({...data,domain:{...data.domain,chainId:8453}},approved));
});

test('reconciliation rejects mismatched receipts before accessing a network',async()=>{
 const input={id:'export',sha256:'a'.repeat(64)};
 const receipt={id:'export',sha256:input.sha256,status:'stored',network:NETWORK,transaction:'0x'+'b'.repeat(64),cid:'bafytest'};
 for(const [key,value] of [['network','eip155:8453'],['sha256','wrong'],['id','other'],['transaction','fake'],['cid','../secret']]) await assert.rejects(()=>verifyStored(input,{...receipt,[key]:value}),/does not match/);
});

test('failed settlement reports its reason without retrying a signed payment',async(t)=>{
 const input={...approved,id:'sample',content:'draft',sha256:createHash('sha256').update('draft').digest('hex'),endpoint:'https://example.test',mime:'text/plain',filename:'report.md'};
 const challenge=required();challenge.resource.url=`https://example.test/upload/agent?size=5&duration=30&sha256=${input.sha256}&id=sample`;
 let requests=0,signatures=0;
 t.mock.method(globalThis,'fetch',async()=>{
   requests++;
   if(requests===1)return new Response('{}',{status:402,headers:{'PAYMENT-REQUIRED':encodePaymentRequiredHeader(challenge)}});
   return new Response('{}',{status:402,headers:{'PAYMENT-RESPONSE':encodePaymentResponseHeader({success:false,network:NETWORK,transaction:'',errorReason:'insufficient_funds'})}});
 });
 await assert.rejects(()=>uploadApproved(input,async()=>{signatures++;return '0x'+'1'.repeat(130)}),/insufficient_funds/);
 assert.equal(requests,2);assert.equal(signatures,1);
});
