import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import NotFound from "./pages/NotFound.tsx";
import NationalDashboard from "./pages/NationalDashboard";
import StateDashboard from "./pages/StateDashboard";
import Community from "./pages/Community";
import Responder from "./pages/Responder";
import Transparency from "./pages/Transparency";
import Simulator from "./pages/Simulator";
import Sources from "./pages/Sources";
import Admin from "./pages/Admin";

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, color: "red", fontFamily: "monospace" }}>
          <h2 style={{ fontSize: 18, fontWeight: "bold" }}>Render error</h2>
          <pre style={{ marginTop: 8, whiteSpace: "pre-wrap", fontSize: 12 }}>
            {(this.state.error as Error).message}
            {"\n\n"}
            {(this.state.error as Error).stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/dashboard" element={<NationalDashboard />} />
            <Route path="/state/:stateAbbr" element={<StateDashboard />} />
            <Route path="/community" element={<Community />} />
            <Route path="/responder" element={<Responder />} />
            <Route path="/transparency" element={<Transparency />} />
            <Route path="/simulator" element={<Simulator />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;