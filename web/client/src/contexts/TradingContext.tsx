import React, { createContext, useContext, useState } from 'react';

interface Bot {
    id: string;
    symbol: string;
    timeframe: string;
    [key: string]: any;
}

interface TradingContextType {
  demoMode: boolean;
  setDemoMode: (value: boolean) => void;
  isConnected: boolean;
  setIsConnected: (value: boolean) => void;
  selectedBot: Bot | null;
  setSelectedBot: (bot: Bot | null) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [demoMode, setDemoMode] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null);

  return (
    <TradingContext.Provider value={{ demoMode, setDemoMode, isConnected, setIsConnected, selectedBot, setSelectedBot }}>
      {children}
    </TradingContext.Provider>
  );
}

export function useTrading() {
  const context = useContext(TradingContext);
  if (!context) {
    throw new Error('useTrading must be used within TradingProvider');
  }
  return context;
}
