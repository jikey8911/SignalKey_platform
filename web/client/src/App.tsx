import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { TradingProvider } from "./contexts/TradingContext";
import Dashboard from "./pages/Dashboard";
import Signals from "./pages/Signals";
import Trades from "./pages/Trades";
import Backtest from "./pages/Backtest";
import Settings from "./pages/Settings";
import TelegramConsole from "./pages/TelegramConsole";
import Home from "./pages/Home";
import Login from "./pages/Login";

function Router() {
  return (
    <Switch>
      <Route path={"/"} component={Dashboard} />
      <Route path={"/signals"} component={Signals} />
      <Route path={"/trades"} component={Trades} />
      <Route path={"/backtest"} component={Backtest} />
      <Route path={"/telegram-console"} component={TelegramConsole} />
      <Route path={"/settings"} component={Settings} />
      <Route path={"/login"} component={Login} />
      <Route path={"/404"} component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

// NOTE: About Theme
// - First choose a default theme according to your design style (dark or light bg), than change color palette in index.css
//   to keep consistent foreground/background color across components
// - If you want to make theme switchable, pass `switchable` ThemeProvider and use `useTheme` hook

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <TradingProvider>
          <TooltipProvider>
            <Toaster />
            <Router />
          </TooltipProvider>
        </TradingProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
