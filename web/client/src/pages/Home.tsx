import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/_core/hooks/useAuth";
import { Loader2, CheckCircle, XCircle, AlertCircle, Play } from "lucide-react";
import { CONFIG } from "@/config";

// Types
type Status = "pending" | "loading" | "success" | "error";

interface ServiceStatus {
  name: string;
  status: Status;
  message?: string;
  details?: string;
}

export default function Home() {
  const { isAuthenticated, loading, user } = useAuth();
  const [, setLocation] = useLocation();
  const [init, setInit] = useState(false);

  const [aiStatus, setAiStatus] = useState<ServiceStatus>({ name: "AI Engine", status: "pending" });
  const [cexStatus, setCexStatus] = useState<ServiceStatus>({ name: "Exchange Connection", status: "pending" });
  const [telegramStatus, setTelegramStatus] = useState<ServiceStatus>({ name: "Telegram Bot", status: "pending" });

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      setLocation("/login");
    } else if (isAuthenticated && !init) {
      setInit(true);
      checkSystemStatus();
    }
  }, [isAuthenticated, loading, setLocation, init]);

  const checkSystemStatus = async () => {
    // 1. Get Config
    try {
      const configRes = await fetch(`${CONFIG.API_BASE_URL}/config/`);
      const configData = await configRes.json();
      const config = configData.config || {};
      const userId = user?.openId || config.userId;

      // 2. Check AI
      setAiStatus(prev => ({ ...prev, status: "loading", message: "Verificando..." }));
      const aiProvider = config.aiProvider || "gemini";
      try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/config/test-ai`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: aiProvider })
        });
        const data = await res.json();
        if (data.status === 'success') {
          setAiStatus({ name: `AI (${aiProvider})`, status: "success", message: "Conectado" });
        } else {
          setAiStatus({ name: `AI (${aiProvider})`, status: "error", message: data.message });
        }
      } catch (e: any) {
        setAiStatus({ name: `AI (${aiProvider})`, status: "error", message: e.message });
      }

      // 3. Check CEX
      setCexStatus(prev => ({ ...prev, status: "loading", message: "Verificando..." }));
      const exchanges = config.exchanges || [];
      const activeExchange = exchanges.find((e: any) => e.isActive) || exchanges[0];

      if (activeExchange) {
        try {
          const res = await fetch(`${CONFIG.API_BASE_URL}/config/test-exchange`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exchangeId: activeExchange.exchangeId })
          });
          const data = await res.json();
          if (data.status === 'success') {
            setCexStatus({ name: `Exchange (${activeExchange.exchangeId})`, status: "success", message: "Conectado" });
          } else {
            setCexStatus({ name: `Exchange (${activeExchange.exchangeId})`, status: "error", message: data.message });
          }
        } catch (e: any) {
          setCexStatus({ name: `Exchange (${activeExchange.exchangeId})`, status: "error", message: e.message });
        }
      } else {
        setCexStatus({ name: "Exchange", status: "error", message: "No configurado" });
      }

      // 4. Check Telegram
      setTelegramStatus(prev => ({ ...prev, status: "loading", message: "Verificando..." }));
      try {
        if (userId) {
          const res = await fetch(`${CONFIG.API_BASE_URL}/telegram/status/${userId}`);
          const data = await res.json();
          if (data.connected) {
            setTelegramStatus({ name: "Telegram Bot", status: "success", message: `Conectado (${data.phone_number || ''})` });
          } else {
            setTelegramStatus({ name: "Telegram Bot", status: "error", message: "No Conectado" });
          }
        } else {
          setTelegramStatus({ name: "Telegram Bot", status: "error", message: "User ID no disponible" });
        }

      } catch (e: any) {
        setTelegramStatus({ name: "Telegram Bot", status: "error", message: e.message });
      }

    } catch (e) {
      console.error("Failed to load config", e);
    }
  };

  const StatusIcon = ({ status }: { status: Status }) => {
    switch (status) {
      case "loading": return <Loader2 className="h-5 w-5 animate-spin text-blue-500" />;
      case "success": return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "error": return <XCircle className="h-5 w-5 text-red-500" />;
      default: return <div className="h-5 w-5 rounded-full border-2 border-gray-300" />;
    }
  };

  const StatusRow = ({ item }: { item: ServiceStatus }) => (
    <div className="flex items-center justify-between p-4 bg-white rounded-lg border shadow-sm">
      <div className="flex items-center gap-3">
        <StatusIcon status={item.status} />
        <div>
          <p className="font-medium text-gray-900">{item.name}</p>
          <p className="text-sm text-gray-500">{item.message || (item.status === 'pending' ? 'Pendiente' : '')}</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">SignaalKei Boot</h1>
          <p className="text-muted-foreground">Verificando servicios del sistema...</p>
        </div>

        <div className="space-y-3">
          <StatusRow item={aiStatus} />
          <StatusRow item={cexStatus} />
          <StatusRow item={telegramStatus} />
        </div>

        <button
          onClick={() => setLocation("/dashboard")}
          className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 rounded-md font-medium transition-colors"
        >
          <span>Continuar al Dashboard</span>
          <Play className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
