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
  Zap,
  Menu,
  X
} from "lucide-react";
import { useEffect, useState } from "react";
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

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location]);

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
      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={
          "border-r border-white/5 bg-slate-900/60 backdrop-blur-3xl flex flex-col z-50 transition-all " +
          (sidebarCollapsed ? "w-20" : "w-64") +
          " md:static fixed inset-y-0 left-0 " +
          (mobileMenuOpen ? "translate-x-0" : "-translate-x-full") +
          " md:translate-x-0"
        }
      >
        <div className="p-6 flex items-center gap-4 border-b border-white/5">
          <div className="h-10 w-10 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Zap className="w-6 h-6 text-white fill-current" />
          </div>
          {!sidebarCollapsed && (
            <span className="font-black text-xl tracking-tighter text-white">SIGNALKEY</span>
          )}
          <button
            onClick={() => setSidebarCollapsed((v) => !v)}
            className="ml-auto hidden md:inline-flex text-slate-400 hover:text-white"
            title="Colapsar"
          >
            <PanelLeft className="w-5 h-5" />
          </button>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="ml-auto md:hidden text-slate-400 hover:text-white"
            title="Cerrar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 space-y-2 mt-4 overflow-y-auto">
          {menuItems.map((item) => {
            const isActive = location === item.path;
            return (
              <button
                key={item.path}
                onClick={() => {
                  setLocation(item.path);
                  setActiveTab(item.path);
                }}
                className={`w-full flex items-center gap-4 px-4 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${
                  isActive
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                    : 'text-slate-500 hover:bg-white/5'
                }`}
              >
                <item.icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-slate-500'}`} />
                {!sidebarCollapsed && item.label}
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
            {!sidebarCollapsed && (
              <div className="overflow-hidden">
                <p className="text-xs font-bold text-white truncate">{user.name}</p>
                <p className="text-[10px] text-slate-500 truncate">{user.role || 'Trader'}</p>
              </div>
            )}
            <button onClick={logout} className="ml-auto text-slate-500 hover:text-red-400" title="Salir">
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
        {/* Mobile top bar */}
        <div className="sticky top-0 z-30 flex items-center gap-3 px-4 py-3 border-b border-white/5 bg-slate-950/60 backdrop-blur md:hidden">
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="text-slate-200"
            title="Menú"
          >
            <Menu className="w-6 h-6" />
          </button>
          <div className="font-bold text-white truncate">SIGNALKEY</div>
          <div className="ml-auto">
            <Badge variant={socketData.isConnected ? 'success' : 'destructive'} className="py-1">
              {socketData.isConnected ? 'ONLINE' : 'OFF'}
            </Badge>
          </div>
        </div>

        {children}
      </main>
    </div>
  );
}

