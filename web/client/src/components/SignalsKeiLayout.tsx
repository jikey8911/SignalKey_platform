import React, { useState } from 'react';
import { useAuth } from '@/_core/hooks/useAuth';
import { useTrading } from '@/contexts/TradingContext';
import { Button } from '@/components/ui/button';
import { Menu, X, LogOut, Settings } from 'lucide-react';
import { Link } from 'wouter';

interface SignalsKeiLayoutProps {
  children: React.ReactNode;
  currentPage: string;
}

export function SignalsKeiLayout({ children, currentPage }: SignalsKeiLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { logout } = useAuth();
  const { demoMode, setDemoMode } = useTrading();

  const navItems = [
    { label: 'Dashboard', href: '/', icon: '📊' },
    { label: 'Señales', href: '/signals', icon: '📡' },
    { label: 'Trades', href: '/trades', icon: '💱' },
    { label: 'Backtesting', href: '/backtest', icon: '📈' },
    { label: 'Configuración', href: '/settings', icon: '⚙️' },
  ];

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? 'w-64' : 'w-20'
          } bg-card border-r border-border transition-all duration-300 flex flex-col`}
      >
        {/* Logo */}
        <div className="p-4 border-b border-border flex items-center justify-between">
          {sidebarOpen && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-bold">
                K
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-sm">Signals</span>
                <span className="text-xs text-primary">Kei</span>
              </div>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 hover:bg-muted rounded"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {/* Demo Mode Toggle */}
        <div className="p-4 border-b border-border">
          <div
            className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all ${demoMode
              ? 'bg-yellow-100 text-yellow-800'
              : 'bg-red-100 text-red-800'
              }`}
          >
            {sidebarOpen ? (
              <>
                <div className="mb-2">{demoMode ? '🧪 DEMO' : '⚠️ REAL'}</div>
                <button
                  onClick={() => setDemoMode(!demoMode)}
                  className="text-xs underline hover:opacity-80"
                >
                  Cambiar modo
                </button>
              </>
            ) : (
              <div className="text-center">{demoMode ? '🧪' : '⚠️'}</div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${currentPage === item.href
              ? 'bg-primary text-primary-foreground'
              : 'text-foreground hover:bg-muted'
              }`}>
              <span className="text-xl">{item.icon}</span>
              {sidebarOpen && <span className="text-sm">{item.label}</span>}
            </Link>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-border space-y-2">
          <button
            onClick={() => logout()}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted transition-colors"
          >
            <LogOut size={18} />
            {sidebarOpen && <span>Salir</span>}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-card border-b border-border px-6 py-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-foreground">
            {navItems.find((item) => item.href === currentPage)?.label || 'SignalsKei'}
          </h1>
          <div className="flex items-center gap-4">
            <div
              className={`px-4 py-2 rounded-lg font-semibold text-sm ${demoMode
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-red-100 text-red-800'
                }`}
            >
              {demoMode ? '🧪 Modo Demo' : '⚠️ Modo Real'}
            </div>
            <Link href="/settings" className="p-2 hover:bg-muted rounded-lg transition-colors">
              <Settings size={20} />
            </Link>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          <div className="p-6">{children}</div>
        </div>
      </main>
    </div>
  );
}
