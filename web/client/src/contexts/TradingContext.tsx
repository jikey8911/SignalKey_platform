import React, { createContext, useContext, useState } from 'react';

interface TradingContextType {
  demoMode: boolean;
  setDemoMode: (value: boolean) => void;
  isConnected: boolean;
  setIsConnected: (value: boolean) => void;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [demoMode, setDemoMode] = useState(true);
  const [isConnected, setIsConnected] = useState(false);

  return (
    <TradingContext.Provider value={{ demoMode, setDemoMode, isConnected, setIsConnected }}>
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
