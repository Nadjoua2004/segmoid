"use client";

import React, { useState, useEffect, useRef } from "react";
import { X, Send, Bot, User, Sparkles, BookOpen, AlertCircle } from "lucide-react";
import { ChatMessage, ProactiveChatPayload, HealthMetricsResponse } from "@/lib/types";
import { api } from "@/lib/api";

interface ProactiveChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  latestMetrics: HealthMetricsResponse | null;
}

export const ProactiveChatDrawer: React.FC<ProactiveChatDrawerProps> = ({
  isOpen,
  onClose,
  latestMetrics,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [proactiveData, setProactiveData] = useState<ProactiveChatPayload | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // Load proactive guidance when drawer opens
  useEffect(() => {
    if (isOpen) {
      api
        .getProactiveChat()
        .then((payload) => {
          setProactiveData(payload);
          if (messages.length === 0) {
            setMessages([
              {
                role: "assistant",
                content: payload.recommended_dialogue,
                citations: payload.reference_guidelines,
              },
            ]);
          }
        })
        .catch((err) => console.error("Error fetching proactive clinical payload:", err));
    }
  }, [isOpen]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (textToSend?: string) => {
    const text = textToSend || inputValue;
    if (!text.trim()) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputValue("");
    setIsLoading(true);

    try {
      const response = await api.queryFlightSurgeon(text);
      setMessages((prev) => [...prev, response]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Communication channel interrupted. Running autonomous local fallback: maintain current cardiovascular countermeasures.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity">
      <div className="relative flex flex-col w-full max-w-lg h-full bg-space-950 border-l border-cyan-800/60 shadow-[-10px_0_30px_rgba(0,240,255,0.15)] text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-space-900/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-cyan-950 border border-cyan-600/50 text-hud-cyan animate-pulse">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-mono font-bold text-white uppercase tracking-wider">
                  AI Flight Surgeon (RAG Agent)
                </h3>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-hud-cyan border border-cyan-800">
                  NASA HRP
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Autonomous Clinical Decision Support • Latency: 18.5m to MCC
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-space-850"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Proactive Trigger Alert Banner */}
        {proactiveData && (
          <div className="p-3 bg-cyan-950/30 border-b border-cyan-900/40">
            <div className="flex items-start space-x-2">
              <Sparkles className="w-4 h-4 text-hud-cyan mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs font-mono text-cyan-300 font-semibold">
                  Autonomous Clinical Surveillance Trigger
                </p>
                <p className="text-[11px] text-slate-300 mt-0.5 font-mono">
                  {proactiveData.clinical_summary}
                </p>
              </div>
            </div>

            {/* Quick Action Chips */}
            {proactiveData.suggested_actions && proactiveData.suggested_actions.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {proactiveData.suggested_actions.map((act, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(`Execute protocol: ${act}`)}
                    className="text-[10px] font-mono px-2 py-1 rounded bg-space-850 hover:bg-cyan-950 text-slate-300 hover:text-hud-cyan border border-slate-700 hover:border-cyan-700 transition-colors"
                  >
                    + {act}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Messages List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-xs">
          {messages.map((msg, index) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={index}
                className={`flex space-x-2.5 ${isUser ? "justify-end" : "justify-start"}`}
              >
                {!isUser && (
                  <div className="w-7 h-7 rounded-lg bg-cyan-950 border border-cyan-800 text-hud-cyan flex items-center justify-center flex-shrink-0">
                    <Bot className="w-4 h-4" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-xl p-3.5 leading-relaxed ${
                    isUser
                      ? "bg-cyan-700/80 text-white rounded-tr-none border border-cyan-500/50"
                      : "bg-space-900 border border-slate-800 text-slate-200 rounded-tl-none"
                  }`}
                >
                  <p className="whitespace-pre-line">{msg.content}</p>

                  {/* NASA Citations */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-slate-800/80">
                      <div className="flex items-center space-x-1 text-[10px] text-hud-cyan font-bold mb-1">
                        <BookOpen className="w-3 h-3" />
                        <span>NASA Human Research Standards Referenced:</span>
                      </div>
                      <ul className="list-disc list-inside text-[10px] text-slate-400 space-y-0.5">
                        {msg.citations.map((cite, cIdx) => (
                          <li key={cIdx}>{cite}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {isUser && (
                  <div className="w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 flex items-center justify-center flex-shrink-0">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            );
          })}
          {isLoading && (
            <div className="flex items-center space-x-2 text-slate-400 font-mono text-xs italic">
              <Bot className="w-4 h-4 animate-spin text-hud-cyan" />
              <span>Querying local ChromaDB NASA clinical guidelines...</span>
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Input Footer */}
        <div className="p-3 border-t border-slate-800 bg-space-900/90">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center space-x-2"
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask Flight Surgeon (e.g. 'Countermeasures for radiation elevation?')"
              className="flex-1 px-3 py-2 text-xs font-mono bg-space-850 rounded-lg border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim()}
              className="p-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
