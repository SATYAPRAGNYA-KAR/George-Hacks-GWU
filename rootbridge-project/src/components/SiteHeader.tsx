import { Link } from "@tanstack/react-router";
import { Sprout } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link to="/" className="flex items-center gap-2 font-semibold text-foreground">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-md text-primary-foreground"
            style={{ background: "var(--gradient-hero)" }}
          >
            <Sprout className="h-4 w-4" />
          </span>
          <span>RootBridge</span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link
            to="/"
            activeOptions={{ exact: true }}
            activeProps={{ className: "bg-secondary text-foreground" }}
            className="rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground"
          >
            Overview
          </Link>
          <Link
            to="/alerts"
            activeProps={{ className: "bg-secondary text-foreground" }}
            className="rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground"
          >
            Alerts
          </Link>
          <Link
            to="/risk"
            activeProps={{ className: "bg-secondary text-foreground" }}
            className="rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground"
          >
            Risk
          </Link>
        </nav>
      </div>
    </header>
  );
}
