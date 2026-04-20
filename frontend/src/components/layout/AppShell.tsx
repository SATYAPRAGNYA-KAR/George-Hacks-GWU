import { TopNav } from "./TopNav";
import { ReactNode } from "react";

export const AppShell = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen bg-gradient-subtle">
    <TopNav />
    <main className="container py-6 animate-fade-in">{children}</main>
    <footer className="border-t bg-card/50 mt-12">
      <div className="container flex flex-col gap-2 py-6 text-xs text-muted-foreground sm:flex-row sm:justify-between">
        <p>FoodReady · Anticipatory food access platform · MVP demo</p>
        <p>
          Data shown is a mix of <span className="font-semibold text-foreground">mock</span> signals and modelled scores.
        </p>
      </div>
    </footer>
  </div>
);
