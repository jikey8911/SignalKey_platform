import { Switch, Route } from "wouter";
import { Toaster } from "@/components/ui/sonner";
import NotFound from "@/pages/NotFound";
import Home from "@/pages/Home";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Signals from "@/pages/Signals";
import Trades from "@/pages/Trades";
import TelegramConsole from "@/pages/TelegramConsole";
import Backtest from "@/pages/Backtest";
import Training from "@/pages/Training";
import Settings from "@/pages/Settings";
import Bots from "@/pages/Bots"; // Importación sp4
import DashboardLayout from "@/components/DashboardLayout";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SocketProvider } from "@/contexts/SocketContext";
import { TradingProvider } from "@/contexts/TradingContext";
import { BacktestProvider } from "@/contexts/BacktestContext";
import ErrorBoundary from "@/components/ErrorBoundary";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/login" component={Login} />

      {/* Rutas protegidas por el Layout del Dashboard */}
      <Route path="/dashboard">
        <DashboardLayout><Dashboard /></DashboardLayout>
      </Route>
      <Route path="/signals">
        <DashboardLayout><Signals /></DashboardLayout>
      </Route>
      <Route path="/trades">
        <DashboardLayout><Trades /></DashboardLayout>
      </Route>
      <Route path="/bots">
        <DashboardLayout><Bots /></DashboardLayout>
      </Route>
      <Route path="/telegram-console">
        <DashboardLayout><TelegramConsole /></DashboardLayout>
      </Route>
      <Route path="/backtest">
        <DashboardLayout><Backtest /></DashboardLayout>
      </Route>
      <Route path="/training">
        <DashboardLayout><Training /></DashboardLayout>
      </Route>
      <Route path="/settings">
        <DashboardLayout><Settings /></DashboardLayout>
      </Route>

      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <SocketProvider>
          <BacktestProvider>
            <TradingProvider>
              <Router />
              <Toaster position="top-right" />
            </TradingProvider>
          </BacktestProvider>
        </SocketProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
