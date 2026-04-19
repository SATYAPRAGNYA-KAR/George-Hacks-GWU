import { Link, NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/store/appStore";
import { Shield, Map, Users, FileText, Settings, Database, FlaskConical, BarChart3, Wifi, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { RegisterButton } from "@/components/UserRegistration";
import { fetchAllStatesFPI } from "@/lib/api";

const links = [
  { to: "/dashboard",   label: "National",    icon: Map },
  { to: "/community",   label: "Community",   icon: Users },
  { to: "/responder",   label: "Responder",   icon: Shield },
  { to: "/transparency",label: "Transparency",icon: FileText },
  { to: "/simulator",   label: "Simulator",   icon: FlaskConical },
  { to: "/sources",     label: "Data sources",icon: Database },
  { to: "/admin",       label: "Admin",       icon: Settings },
];

const LiveStatusDot = () => {
  const { isLoading, isError, data } = useQuery({
    queryKey: ["fpi-states-heartbeat"],
    queryFn: () => fetchAllStatesFPI(),
    staleTime: 10 * 60_000,
    retry: 0,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return null;

  if (!isError && data) {
    const liveCount = data.states.filter((s) => s.gemini_source === "gemini").length;
    return (
      <span className="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 sm:inline-flex dark:bg-emerald-950 dark:text-emerald-300">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
        {liveCount > 0 ? `Live · ${liveCount} states` : "Connected"}
      </span>
    );
  }

  return (
    <span className="hidden items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground sm:inline-flex">
      <WifiOff className="h-2.5 w-2.5" />
      Baseline
    </span>
  );
};

export const TopNav = () => {
  const role    = useAppStore((s) => s.role);
  const setRole = useAppStore((s) => s.setRole);

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="container flex h-14 items-center gap-2">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-gradient-hero text-primary-foreground shadow-glow">
            <BarChart3 className="h-4 w-4" />
          </span>
          <span className="text-base">FoodReady</span>
          <span className="hidden text-[10px] font-semibold uppercase tracking-wider text-muted-foreground sm:inline">
            US · All 50 States
          </span>
        </Link>

        <nav className="ml-4 hidden flex-1 items-center gap-0.5 lg:flex">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-accent text-accent-foreground",
                )
              }
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <LiveStatusDot />
          <RegisterButton />
          <span className="hidden text-xs text-muted-foreground sm:inline">Role</span>
          <Select value={role} onValueChange={(v) => setRole(v as any)}>
            <SelectTrigger className="h-8 w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="public">Public</SelectItem>
              <SelectItem value="community">Community</SelectItem>
              <SelectItem value="responder">Responder</SelectItem>
              <SelectItem value="coordinator">Coordinator</SelectItem>
              <SelectItem value="government">Government</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="container flex items-center gap-1 overflow-x-auto pb-2 lg:hidden">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent",
                isActive && "bg-accent text-accent-foreground",
              )
            }
          >
            <Icon className="h-3 w-3" />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
};