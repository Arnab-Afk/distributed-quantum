import { createHash } from 'node:crypto';
import { x402Client } from '@x402/core/client';
import { decodePaymentRequiredHeader, decodePaymentResponseHeader, encodePaymentSignatureHeader } from '@x402/core/http';
import { ExactEvmScheme } from '@x402/evm/exact/client';
import { createPublicClient, http, parseEventLogs, erc20Abi } from 'viem';
import { baseSepolia } from 'viem/chains';
import { NETWORK, USDC, MAX_BYTES } from './policy.mjs';

const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.toLowerCase()===b.toLowerCase();
export function validateChallenge(required,approved) {
  const r=required.accepts?.[0];
  if(required.x402Version!==2||required.resource?.url!==approved.url||required.accepts?.length!==1||r.scheme!=='exact'||r.network!==NETWORK||!same(r.asset,USDC)||!same(r.payTo,approved.payTo)||r.amount!==approved.amount||!/^\d+$/.test(r.amount)||BigInt(r.amount)<1n||BigInt(r.amount)>24n||!Number.isInteger(r.maxTimeoutSeconds)||r.maxTimeoutSeconds<1||r.maxTimeoutSeconds>120||r.extra?.name!=='USDC'||r.extra?.version!=='2')throw Error('Testnet payment challenge differs from approval.');
}
export function validateTypedData(data,approved) {
 const d=data.domain,m=data.message,now=Math.floor(Date.now()/1000);
 if(d?.name!=='USDC'||d.version!=='2'||Number(d.chainId)!==84532||!same(d.verifyingContract,USDC)||data.primaryType!=='TransferWithAuthorization'||!same(m?.from,approved.address)||!same(m?.to,approved.payTo)||String(m?.value)!==approved.amount||!/^0x[0-9a-fA-F]{64}$/.test(m?.nonce||'')||!Number.isSafeInteger(Number(m?.validAfter))||Number(m.validAfter)>now||Number(m.validAfter)<0||!Number.isSafeInteger(Number(m?.validBefore))||Number(m.validBefore)<=now||Number(m.validBefore)>now+180)throw Error('Refusing an unapproved typed-data signature.');
}
export async function uploadApproved(input,signTypedData) {
 const bytes=Buffer.from(input.content,'utf8');
 if(bytes.length<1||bytes.length>MAX_BYTES||createHash('sha256').update(bytes).digest('hex')!==input.sha256)throw Error('Approved artifact changed.');
 const endpoint=new URL(input.endpoint);
 if(endpoint.protocol!=='https:'&&!(endpoint.protocol==='http:'&&['localhost','127.0.0.1'].includes(endpoint.hostname)))throw Error('HTTPS endpoint required.');
 const url=new URL('/upload/agent',endpoint);
 url.search=new URLSearchParams({size:String(bytes.length),duration:'30',sha256:input.sha256,id:input.id}).toString();
 const approved={...input,url:url.href};
 const headers={};
 const form=()=>{const f=new FormData();f.set('file',new Blob([bytes],{type:input.mime}),input.filename);return f;};
 const response=await fetch(url,{method:'POST',body:form(),headers,redirect:'error',signal:AbortSignal.timeout(60000)});
 if(response.status!==402)throw Error(`Storage challenge unavailable (HTTP ${response.status}).`);
 const required=decodePaymentRequiredHeader(response.headers.get('PAYMENT-REQUIRED')||'');
 validateChallenge(required,approved);
 const client=new x402Client().register(NETWORK,new ExactEvmScheme({address:input.address,signTypedData:async data=>{validateTypedData(data,approved);return signTypedData(data);}}));
 const payment=await client.createPaymentPayload(required);
 // A signed request is sent once. An uncertain response requires receipt reconciliation.
 const result=await fetch(url,{method:'POST',body:form(),headers:{...headers,'PAYMENT-SIGNATURE':encodePaymentSignatureHeader(payment)},redirect:'error',signal:AbortSignal.timeout(90000)});
 if(!result.ok){
   let reason='unknown';
   try {const failure=decodePaymentResponseHeader(result.headers.get('PAYMENT-RESPONSE')||'');if(/^[a-z0-9_:-]{1,100}$/i.test(failure.errorReason||''))reason=failure.errorReason;}catch{}
   throw Error(`Storage settlement not verified (HTTP ${result.status}; ${reason}). Do not pay again; check receipt.`);
 }
 const receipt=await result.json();
 const settlement=decodePaymentResponseHeader(result.headers.get('PAYMENT-RESPONSE')||'');
 if(!settlement.success||settlement.network!==NETWORK||!/^0x[0-9a-fA-F]{64}$/.test(settlement.transaction||'')||receipt.sha256!==input.sha256||receipt.id!==input.id||!/^[a-zA-Z0-9]+$/.test(receipt.cid||''))throw Error('Storage receipt is not verified.');
 return verifyStored(input,{...receipt,transaction:settlement.transaction,network:settlement.network,status:'stored'});
}

export async function verifyStored(input,receipt) {
 if(receipt.status!=='stored'||receipt.network!==NETWORK||receipt.sha256!==input.sha256||receipt.id!==input.id||!/^0x[0-9a-fA-F]{64}$/.test(receipt.transaction||'')||!/^[a-zA-Z0-9]+$/.test(receipt.cid||''))throw Error('Stored receipt does not match the approved export.');
 const chain=createPublicClient({chain:baseSepolia,transport:http('https://sepolia.base.org')});
 const tx=await chain.getTransactionReceipt({hash:receipt.transaction});
 const transfers=parseEventLogs({abi:erc20Abi,eventName:'Transfer',logs:tx.logs});
 if(tx.status!=='success'||!transfers.some(log=>same(log.address,USDC)&&same(log.args.from,input.address)&&same(log.args.to,input.payTo)&&log.args.value===BigInt(input.amount)))throw Error('On-chain testnet payment does not match approval.');
 const url=`https://gateway.pinata.cloud/ipfs/${receipt.cid}/${encodeURIComponent(input.filename)}`;
 const saved=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(60000)});
 if(!saved.ok||!saved.body)throw Error('Payment succeeded but public retrieval is not yet verified. Check receipt.');
 const chunks=[];let size=0;
 for await(const chunk of saved.body){size+=chunk.length;if(size>MAX_BYTES)throw Error('Retrieved content exceeds approved size.');chunks.push(chunk);}
 if(createHash('sha256').update(Buffer.concat(chunks)).digest('hex')!==input.sha256)throw Error('Public content hash does not match approval.');
 return {...receipt,url,verified:true};
}
