import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { US_STATES } from "@/data/states";
import { registerUser, fetchUser, type RegisterUserRequest, type RegisteredUser } from "@/lib/api";
import { toast } from "sonner";
import { UserPlus, CheckCircle2, LogOut, ChevronDown, User, Loader2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Session helpers — stored in localStorage
// ---------------------------------------------------------------------------
const SESSION_KEY = "rootbridge_user_email";

function getSessionEmail(): string | null {
  try { return localStorage.getItem(SESSION_KEY); } catch { return null; }
}
function setSessionEmail(email: string) {
  try { localStorage.setItem(SESSION_KEY, email); } catch {}
}
function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch {}
}

const ROLES = [
  { value: "public",      label: "General public" },
  { value: "community",   label: "Community member" },
  { value: "responder",   label: "Food bank / NGO responder" },
  { value: "coordinator", label: "Local coordinator" },
  { value: "government",  label: "Government / agency" },
  { value: "admin",       label: "Admin" },
];

// ---------------------------------------------------------------------------
// Registration modal
// ---------------------------------------------------------------------------
interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (user: RegisteredUser) => void;
  initialTab?: "register" | "login";
}

export const UserRegistrationModal = ({ open, onOpenChange, onSuccess, initialTab = "register" }: ModalProps) => {
  const [tab,    setTab]    = useState<"register" | "login">(initialTab);
  const [email,  setEmail]  = useState("");
  const [name,   setName]   = useState("");
  const [role,   setRole]   = useState("public");
  const [state,  setState]  = useState("IA");
  const [org,    setOrg]    = useState("");
  const [phone,  setPhone]  = useState("");
  const [success, setSuccess] = useState<RegisteredUser | null>(null);

  // Login: look up existing user
  const [loginEmail, setLoginEmail] = useState("");
  const [loginTriggered, setLoginTriggered] = useState(false);

  const { data: loginUser, isLoading: loginLoading, isError: loginError } = useQuery({
    queryKey: ["user-login", loginEmail],
    queryFn:  () => fetchUser(loginEmail),
    enabled:  loginTriggered && loginEmail.includes("@"),
    retry: 0,
  });

  const handleLogin = () => {
    if (!loginEmail.includes("@")) { toast.error("Enter a valid email."); return; }
    setLoginTriggered(true);
  };

  // If login query succeeded
  if (loginUser && loginTriggered) {
    setSessionEmail(loginUser.email);
    onSuccess?.(loginUser);
    setLoginTriggered(false);
    onOpenChange(false);
    toast.success(`Welcome back, ${loginUser.name}!`);
  }

  const registerMutation = useMutation({
    mutationFn: (req: RegisterUserRequest) => registerUser(req),
    onSuccess: (res) => {
      setSuccess(res.user);
      setSessionEmail(res.user.email);
      toast.success(`Welcome, ${res.user.name}!`);
      onSuccess?.(res.user);
    },
    onError: (err: Error) => {
      if (err.message.includes("409")) {
        toast.error("Email already registered — use Sign in instead.");
        setTab("login");
      } else {
        toast.error(`Registration failed: ${err.message}`);
      }
    },
  });

  const handleRegister = () => {
    if (!email.trim() || !name.trim()) { toast.error("Name and email are required."); return; }
    registerMutation.mutate({
      email: email.trim(), name: name.trim(),
      role: role as RegisterUserRequest["role"],
      state_abbr: state,
      org_name: org || undefined,
      phone: phone || undefined,
    });
  };

  const reset = () => {
    setEmail(""); setName(""); setRole("public"); setState("IA"); setOrg(""); setPhone("");
    setSuccess(null); setLoginEmail(""); setLoginTriggered(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            {tab === "register" ? "Join FoodReady" : "Sign in"}
          </DialogTitle>
          <DialogDescription>
            {tab === "register"
              ? "Get alerts, submit requests, and coordinate food access for your community."
              : "Sign in with your registered email to access your account."}
          </DialogDescription>
        </DialogHeader>

        {/* Tab toggle */}
        <div className="flex gap-2 border-b pb-3">
          <Button size="sm" variant={tab === "register" ? "secondary" : "ghost"}
            onClick={() => setTab("register")} className="h-7 text-xs">Create account</Button>
          <Button size="sm" variant={tab === "login" ? "secondary" : "ghost"}
            onClick={() => setTab("login")} className="h-7 text-xs">Sign in</Button>
        </div>

        {success ? (
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <CheckCircle2 className="h-12 w-12 text-emerald-500" />
            <div>
              <p className="text-lg font-semibold">Welcome, {success.name}!</p>
              <p className="text-sm text-muted-foreground mt-1">
                Registered as <strong>{success.role}</strong> in <strong>{success.state_abbr}</strong>.
              </p>
            </div>
            <Button onClick={() => onOpenChange(false)}>Start using FoodReady</Button>
          </div>
        ) : tab === "login" ? (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Email address</Label>
              <Input value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="jane@example.com" type="email" className="h-8 text-sm"
                onKeyDown={(e) => e.key === "Enter" && handleLogin()} />
            </div>
            {loginTriggered && loginError && (
              <p className="text-xs text-red-600">No account found for that email. Try creating one.</p>
            )}
            <Button onClick={handleLogin} disabled={loginLoading} className="w-full gap-2">
              {loginLoading && <Loader2 className="h-4 w-4 animate-spin" />}
              Sign in
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Don't have an account?{" "}
              <button className="underline hover:text-foreground" onClick={() => setTab("register")}>Create one</button>
            </p>
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Full name *</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Smith" className="h-8 text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Email *</Label>
                <Input value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="jane@example.com" type="email" className="h-8 text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Role</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => <SelectItem key={r.value} value={r.value} className="text-sm">{r.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">State</Label>
                <Select value={state} onValueChange={setState}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-60">
                    {US_STATES.map((s) => <SelectItem key={s.abbr} value={s.abbr} className="text-sm">{s.abbr} — {s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {["responder", "coordinator", "government"].includes(role) && (
              <div className="space-y-1.5">
                <Label className="text-xs">Organization name</Label>
                <Input value={org} onChange={(e) => setOrg(e.target.value)} className="h-8 text-sm" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">Phone (optional — for SMS alerts)</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 555 000 0000" className="h-8 text-sm" />
            </div>
            <Button onClick={handleRegister} disabled={registerMutation.isPending} className="w-full gap-2">
              {registerMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create account
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Already have an account?{" "}
              <button className="underline hover:text-foreground" onClick={() => setTab("login")}>Sign in</button>
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

// ---------------------------------------------------------------------------
// Register/Login button for TopNav — shows dropdown with logout when logged in
// ---------------------------------------------------------------------------
export const RegisterButton = () => {
  const [open, setOpen] = useState(false);
  const [tab, setTab]   = useState<"register" | "login">("register");
  const [, forceUpdate] = useState(0);

  const savedEmail = getSessionEmail();

  const handleLogout = () => {
    clearSession();
    forceUpdate((n) => n + 1);
    toast.success("Logged out successfully.");
  };

  if (savedEmail) {
    const username = savedEmail.split("@")[0];
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5">
            <User className="h-3.5 w-3.5" />
            {username}
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[160px]">
          <div className="px-2 py-1.5 text-xs text-muted-foreground truncate">{savedEmail}</div>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-xs" onClick={() => { setTab("login"); setOpen(true); }}>
            <User className="mr-2 h-3.5 w-3.5" /> Switch account
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-xs text-red-600 focus:text-red-600" onClick={handleLogout}>
            <LogOut className="mr-2 h-3.5 w-3.5" /> Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => { setTab("register"); setOpen(true); }} className="h-8 text-xs gap-1.5">
        <UserPlus className="h-3.5 w-3.5" /> Join
      </Button>
      <Button size="sm" variant="ghost" onClick={() => { setTab("login"); setOpen(true); }} className="h-8 text-xs">
        Sign in
      </Button>
      <UserRegistrationModal open={open} onOpenChange={setOpen} initialTab={tab}
        onSuccess={() => forceUpdate((n) => n + 1)} />
    </>
  );
};