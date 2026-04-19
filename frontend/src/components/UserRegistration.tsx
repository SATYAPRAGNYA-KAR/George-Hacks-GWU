import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { US_STATES } from "@/data/states";
import { registerUser, type RegisterUserRequest, type RegisteredUser } from "@/lib/api";
import { toast } from "sonner";
import { UserPlus, CheckCircle2 } from "lucide-react";

const ROLES = [
  { value: "public",      label: "General public" },
  { value: "community",   label: "Community member" },
  { value: "responder",   label: "Food bank / NGO responder" },
  { value: "coordinator", label: "Local coordinator" },
  { value: "government",  label: "Government / agency" },
  { value: "admin",       label: "Admin" },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (user: RegisteredUser) => void;
}

export const UserRegistrationModal = ({ open, onOpenChange, onSuccess }: Props) => {
  const [email,    setEmail]    = useState("");
  const [name,     setName]     = useState("");
  const [role,     setRole]     = useState("public");
  const [state,    setState]    = useState("IA");
  const [county,   setCounty]   = useState("");
  const [org,      setOrg]      = useState("");
  const [phone,    setPhone]    = useState("");
  const [success,  setSuccess]  = useState<RegisteredUser | null>(null);

  const mutation = useMutation({
    mutationFn: (req: RegisterUserRequest) => registerUser(req),
    onSuccess: (res) => {
      setSuccess(res.user);
      toast.success(`Welcome, ${res.user.name}! Your account is set up.`);
      onSuccess?.(res.user);
      // Store email in localStorage so we can pre-fill on next visit
      localStorage.setItem("rootbridge_user_email", res.user.email);
    },
    onError: (err: Error) => {
      if (err.message.includes("409")) {
        toast.error("This email is already registered. Try signing in instead.");
      } else {
        toast.error(`Registration failed: ${err.message}`);
      }
    },
  });

  const handleSubmit = () => {
    if (!email.trim() || !name.trim()) {
      toast.error("Name and email are required.");
      return;
    }
    mutation.mutate({
      email: email.trim(),
      name: name.trim(),
      role: role as RegisterUserRequest["role"],
      state_abbr: state,
      county_fips: county || undefined,
      org_name: org || undefined,
      phone: phone || undefined,
    });
  };

  const reset = () => {
    setEmail(""); setName(""); setRole("public"); setState("IA");
    setCounty(""); setOrg(""); setPhone(""); setSuccess(null);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Join FoodReady
          </DialogTitle>
          <DialogDescription>
            Get alerts, submit ground-truth signals, and help coordinate food access for your community.
          </DialogDescription>
        </DialogHeader>

        {success ? (
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <CheckCircle2 className="h-12 w-12 text-emerald-500" />
            <div>
              <p className="text-lg font-semibold">Welcome, {success.name}!</p>
              <p className="text-sm text-muted-foreground mt-1">
                You're registered as <strong>{success.role}</strong> in{" "}
                <strong>{success.state_abbr}</strong>.
              </p>
              {success.alerts_opt_in && (
                <p className="text-xs text-muted-foreground mt-2">
                  ✓ You'll receive food security alerts for your area.
                </p>
              )}
            </div>
            <Button onClick={() => onOpenChange(false)}>Start using FoodReady</Button>
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
                <Label className="text-xs">Email address *</Label>
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
                    {ROLES.map((r) => (
                      <SelectItem key={r.value} value={r.value} className="text-sm">{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">State</Label>
                <Select value={state} onValueChange={setState}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-60">
                    {US_STATES.map((s) => (
                      <SelectItem key={s.abbr} value={s.abbr} className="text-sm">{s.abbr} — {s.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {(role === "responder" || role === "coordinator" || role === "government") && (
              <div className="space-y-1.5">
                <Label className="text-xs">Organization name</Label>
                <Input value={org} onChange={(e) => setOrg(e.target.value)}
                  placeholder="e.g. Food Bank of Iowa" className="h-8 text-sm" />
              </div>
            )}

            <div className="space-y-1.5">
              <Label className="text-xs">Phone (optional — for SMS alerts)</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 555 000 0000" className="h-8 text-sm" />
            </div>

            <Button
              onClick={handleSubmit}
              disabled={mutation.isPending}
              className="w-full"
            >
              {mutation.isPending ? "Creating account…" : "Create account"}
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              Already registered?{" "}
              <button className="underline hover:text-foreground"
                onClick={() => toast.info("Sign-in coming soon — use your registered email to access features.")}>
                Sign in
              </button>
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

/** Small button that opens the registration modal — drop into TopNav or any page */
export const RegisterButton = () => {
  const [open, setOpen] = useState(false);
  const savedEmail = typeof localStorage !== "undefined"
    ? localStorage.getItem("rootbridge_user_email")
    : null;

  if (savedEmail) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
        <CheckCircle2 className="h-3 w-3" />
        {savedEmail.split("@")[0]}
      </span>
    );
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} className="h-8 text-xs gap-1.5">
        <UserPlus className="h-3.5 w-3.5" /> Join
      </Button>
      <UserRegistrationModal open={open} onOpenChange={setOpen} />
    </>
  );
};