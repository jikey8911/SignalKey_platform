import { useAuth } from "@/_core/hooks/useAuth";
import { Badge } from "@/components/ui/badge";
import { useSocketContext } from "@/contexts/SocketContext";
import {
  BrainCircuit,
  Cpu,
  LayoutDashboard,
  LogOut,
  PanelLeft,
  Settings,
  Users,
  Zap
} from "lucide-react";
import { useState } from "react";
import { useLocation } from "wouter";
import { DashboardLayoutSkeleton } from './DashboardLayoutSkeleton';
import { Button } from "./ui/button";

const menuItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: Users, label: "Signals", path: "/signals" },
  { icon: PanelLeft, label: "Trades", path: "/trades" },
  { icon: Cpu, label: "Bots", path: "/bots" },
  { icon: Zap, label: "Telegram", path: "/telegram-console" },
  { icon: BrainCircuit, label: "Backtest", path: "/backtest" },
  { icon: BrainCircuit, label: "Training", path: "/training" },
  { icon: Settings, label: "Settings", path: "/settings" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const [location, setLocation] = useLocation();
  const socketData = useSocketContext();
  const [activeTab, setActiveTab] = useState(location);

  if (loading) {
    return <DashboardLayoutSkeleton />
  }

  if (!user) {
    // Redirigir o mostrar login (simplificado)
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-white">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">Acceso Restringido</h1>
          <Button onClick={() => window.location.href = '/login'}>Iniciar Sesión</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 font-sans overflow-hidden">
      {/* Sidebar Glassmorphism */}
      <aside className="w-64 border-r border-white/5 bg-slate-900/60 backdrop-blur-3xl flex flex-col z-30 transition-all">
        <div className="p-8 flex items-center gap-4">
          <div className="h-10 w-10 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Zap className="w-6 h-6 text-white fill-current" />
          </div>
          <span className="font-black text-xl tracking-tighter text-white">SIGNALKEY</span>
        </div>

        <nav className="flex-1 px-4 space-y-2 mt-6 overflow-y-auto">
          {menuItems.map((item) => {
            const isActive = location === item.path;
            return (
              <button
                key={item.path}
                onClick={() => {
                  setLocation(item.path);
                  setActiveTab(item.path);
                }}
                className={`w-full flex items-center gap-4 px-5 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${isActive ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'text-slate-500 hover:bg-white/5'}`}
              >
                <item.icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-slate-500'}`} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="p-6 border-t border-white/5 space-y-4">
          {/* User Info Mini */}
          <div className="flex items-center gap-3 px-2">
            <div className="h-8 w-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-white border border-white/10">
              {user.name?.charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-xs font-bold text-white truncate">{user.name}</p>
              <p className="text-[10px] text-slate-500 truncate">{user.role || 'Trader'}</p>
            </div>
            <button onClick={logout} className="ml-auto text-slate-500 hover:text-red-400">
              <LogOut className="w-4 h-4" />
            </button>
          </div>

          <Badge variant={socketData.isConnected ? 'success' : 'destructive'} className="w-full justify-center py-1">
            {socketData.isConnected ? 'SYSTEM ONLINE' : 'DISCONNECTED'}
          </Badge>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-blue-900/10 via-slate-950 to-slate-950 p-0">
        {children}
      </main>
    </div>
  );
}

