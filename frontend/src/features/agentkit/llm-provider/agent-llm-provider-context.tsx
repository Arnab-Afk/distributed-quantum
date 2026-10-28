"use client";

import { createContext, useEffect, useState, type ReactNode } from "react";
import { LLM_PROVIDER_STORAGE_KEY, type AgentLlmProvider } from "./constants";

type ProviderInfo = {
  id: AgentLlmProvider;
  label: string;
  configured: boolean;
};

type AgentLlmProviderContextValue = {
  provider: AgentLlmProvider;
  setProvider: (provider: AgentLlmProvider) => void;
  providers: ProviderInfo[];
  loading: boolean;
};

export const AgentLlmProviderContext = createContext<AgentLlmProviderContextValue | null>(null);

export function AgentLlmProviderProvider({ children }: { children: ReactNode }) {
  const [provider, setProviderState] = useState<AgentLlmProvider>("groq");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);

  // Hydrate from backend on mount
  useEffect(() => {
    let cancelled = false;

    // First, try to read from localStorage
    const stored = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY);
    if (stored && (stored === "groq" || stored === "openrouter" || stored === "near")) {
      setProviderState(stored);
    }

    // Then fetch from backend to get default and provider list
    fetch("/api/agentkit/agents/llm-providers")
      .then((res) => res.json())
      .then((data: { default: string; providers: ProviderInfo[] }) => {
        if (cancelled) return;
        
        setProviders(data.providers);
        
        // If no localStorage value, use backend default
        if (!stored) {
          const defaultProvider = data.default as AgentLlmProvider;
          if (defaultProvider === "groq" || defaultProvider === "openrouter" || defaultProvider === "near") {
            setProviderState(defaultProvider);
            localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, defaultProvider);
          }
        }
        
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          // Fallback to groq if fetch fails
          setProviders([
            { id: "groq", label: "Groq", configured: true },
            { id: "openrouter", label: "OpenRouter", configured: false },
            { id: "near", label: "NEAR AI Cloud", configured: false },
          ]);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const setProvider = (newProvider: AgentLlmProvider) => {
    setProviderState(newProvider);
    localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, newProvider);
  };

  return (
    <AgentLlmProviderContext.Provider value={{ provider, setProvider, providers, loading }}>
      {children}
    </AgentLlmProviderContext.Provider>
  );
}
