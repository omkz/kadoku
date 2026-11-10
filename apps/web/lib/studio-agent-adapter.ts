"use client";

/**
 * AG Studio 3.1 direct-LLM adapter, backed by an admin-only Kadoku endpoint.
 * The model and its credentials live only in FastAPI. The browser performs
 * AG Studio's tool operations after the model returns validated tool calls.
 *
 * The backend sends one complete turn (not SSE). This adapter emits the same
 * AG-UI event types Studio expects, once the server replies.
 */
import type {
  AgAiEvent,
  AgAiOutputItem,
  AgLlmAdapter,
  AgLlmRequest,
  AgLlmResponse,
  AgLlmResponseHandler,
} from "ag-studio";
import {authHeaders} from "./auth-client";

function eventsFor(item:AgAiOutputItem):AgAiEvent[] {
  if(item.type==="message"){
    const messageId=item.id;
    const events:AgAiEvent[]=[{
      type:"TEXT_MESSAGE_START",messageId,role:"assistant",
    }];
    for(const content of item.content){
      if(content.type==="text" && content.text) {
        events.push({type:"TEXT_MESSAGE_CONTENT",messageId,delta:content.text});
      }
    }
    events.push({type:"TEXT_MESSAGE_END",messageId});
    return events;
  }
  if(item.type==="function_call") {
    return [
      {type:"TOOL_CALL_START",toolCallId:item.callId,toolCallName:item.name},
      {type:"TOOL_CALL_ARGS",toolCallId:item.callId,delta:item.arguments},
      {type:"TOOL_CALL_END",toolCallId:item.callId},
    ];
  }
  // Reasoning is not forwarded by this provider adapter.
  return [];
}

export function createKadokuStudioAdapter():AgLlmAdapter {
  return {
    executeTurn(request:AgLlmRequest,options?:{signal?:AbortSignal}):AgLlmResponseHandler {
      let resolveComplete!:(value:AgLlmResponse)=>void;
      let rejectComplete!:(reason:Error)=>void;
      const complete=new Promise<AgLlmResponse>((resolve,reject)=>{
        resolveComplete=resolve;
        rejectComplete=reject;
      });
      // A cancelled/abandoned stream must not cause an unhandled rejection.
      void complete.catch(()=>{});

      async function* run():AsyncIterableIterator<AgAiEvent> {
        try {
          const headers=await authHeaders(true);
          const response=await fetch("/backend/api/v1/admin/analytics/agent/turn",{
            method:"POST",
            headers:{"Content-Type":"application/json",...headers},
            body:JSON.stringify({
              input:request.input,
              instructions:request.instructions,
              tools:request.tools,
              toolChoice:request.toolChoice,
              responseFormat:request.responseFormat,
            }),
            signal:options?.signal,
            cache:"no-store",
          });
          const data:unknown=await response.json().catch(()=>({}));
          if(!response.ok){
            const detail=(data && typeof data==="object" && "detail" in data)
              ? (data as {detail:unknown}).detail:null;
            throw new Error(typeof detail==="string" ? detail : "Studio AI request failed ("+response.status+")");
          }
          if(!data || typeof data!=="object" || !("output" in data)
            || !Array.isArray((data as {output:unknown}).output)){
            throw new Error("Invalid response from Studio AI backend");
          }
          const result=data as AgLlmResponse;
          for(const item of result.output){
            for(const event of eventsFor(item)){
              yield event;
            }
          }
          resolveComplete(result);
        } catch(reason){
          rejectComplete(reason instanceof Error?reason:new Error(String(reason)));
        }
      }
      const iterator=run();
      return {
        stream:{[Symbol.asyncIterator]:()=>iterator},
        complete,
      };
    },
  };
}
