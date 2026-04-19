import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Activity, AlertTriangle, BarChart3, Database, FileText, Map, Shield, Sparkles, Users } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";

const Section = ({ children, className = "" }: any) => (
  <section className={`container py-12 sm:py-16 ${className}`}>{children}</section>
);

const Landing = () => {
  return (
    <div className="min-h-screen bg-background">
      <TopNav />

      {/* Hero */}
      <header className="relative overflow-hidden bg-gradient-hero text-primary-foreground">
        <div className="absolute inset-0 opacity-20" style={{
          backgroundImage: "radial-gradient(circle at 20% 30%, hsl(188 70% 70%) 0, transparent 40%), radial-gradient(circle at 80% 70%, hsl(168 55% 60%) 0, transparent 40%)",
        }} />
        <div className="container relative py-20 sm:py-28">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium backdrop-blur">
              <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-white" />
              U.S.-wide anticipatory food access platform
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
              Act <span className="italic text-primary-glow">before</span> a disaster<br />becomes a food shortage.
            </h1>
            <p className="mt-5 max-w-2xl text-base text-primary-foreground/85 sm:text-lg">
              FoodReady gives governments, food banks, and communities a single, county-level view of food access
              risk across the United States — combining disaster signals, vulnerability data, supply capacity, and
              responder readiness into one Food Access Risk Score.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button asChild size="lg" className="bg-white text-primary hover:bg-white/90">
                <Link to="/dashboard">View national dashboard</Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="border-white/30 bg-white/5 text-white hover:bg-white/15">
                <Link to="/community">Submit community request</Link>
              </Button>
              <Button asChild size="lg" variant="ghost" className="text-white hover:bg-white/10">
                <Link to="/responder">Responder portal →</Link>
              </Button>
            </div>
            <p className="mt-5 text-xs text-primary-foreground/70">
              Iowa is the seeded pilot/demo state. Architecture supports all 50 U.S. states + counties.
            </p>
          </div>
        </div>
      </header>

      {/* Four sides */}
      <Section>
        <h2 className="text-2xl font-bold sm:text-3xl">One platform, four sides</h2>
        <p className="mt-2 max-w-2xl text-muted-foreground">FoodReady serves four audiences with role-appropriate views and tools.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[
            { icon: BarChart3, title: "Government & coordinators", body: "National, state, and county dashboards with rankings, alerts, and trigger logs.", to: "/dashboard" },
            { icon: Users, title: "Community", body: "Anonymous request portal, price reports, and reference-number status checking.", to: "/community" },
            { icon: Shield, title: "Responders", body: "Live request feed, capacity declarations, claim/resolve workflow, impact log.", to: "/responder" },
            { icon: FileText, title: "Public observers", body: "Read-only transparency page with methodology, scores, and CSV export.", to: "/transparency" },
          ].map((x) => (
            <Card key={x.title} className="group relative overflow-hidden transition-shadow hover:shadow-elevated">
              <CardContent className="p-5">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-hero text-primary-foreground"><x.icon className="h-5 w-5" /></div>
                <h3 className="mt-4 font-semibold">{x.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{x.body}</p>
                <Link to={x.to} className="mt-3 inline-block text-xs font-semibold text-primary hover:underline">Open →</Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      {/* How it works */}
      <Section className="border-y bg-card/50">
        <h2 className="text-2xl font-bold sm:text-3xl">How it works</h2>
        <div className="mt-8 grid gap-6 md:grid-cols-3">
          {[
            { n: "1", t: "Aggregate signals", b: "Disaster alerts, vulnerability data, market prices, pantry density, and responder capacity feed into the model — county by county." },
            { n: "2", t: "Score & trigger", b: "Each county gets a 0–100 Food Access Risk Score. When the score crosses a threshold, the matching response action is triggered." },
            { n: "3", t: "Coordinate response", b: "Responders see live requests and recommended actions. Coordinators see escalation paths. The public sees what was done." },
          ].map((s) => (
            <div key={s.n} className="rounded-xl border bg-card p-5 shadow-smooth">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-primary text-primary-foreground font-mono text-sm">{s.n}</div>
              <h3 className="mt-3 font-semibold">{s.t}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{s.b}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Trigger ladder */}
      <Section>
        <h2 className="text-2xl font-bold sm:text-3xl">Pre-agreed trigger actions</h2>
        <p className="mt-2 max-w-2xl text-muted-foreground">When risk scores cross thresholds, the platform recommends the matching action — published in advance, not improvised in a crisis.</p>
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            { range: "0–39", label: "Prepared", color: "var(--risk-prepared)", body: "Routine monitoring." },
            { range: "40–59", label: "Watch", color: "var(--risk-watch)", body: "Alert lead, monitor daily." },
            { range: "60–74", label: "Warning", color: "var(--risk-warning)", body: "Pre-position stocks." },
            { range: "75–89", label: "Action", color: "var(--risk-action)", body: "Deploy responders, vouchers." },
            { range: "90–100", label: "Critical", color: "var(--risk-critical)", body: "Escalate to state coord." },
          ].map((t) => (
            <div key={t.label} className="rounded-xl border bg-card p-4 shadow-smooth">
              <div className="text-xs font-mono text-muted-foreground">{t.range}</div>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: `hsl(${t.color})` }} />
                <span className="font-semibold">{t.label}</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{t.body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Data sources */}
      <Section className="border-y bg-card/50">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold sm:text-3xl">Data sources</h2>
            <p className="mt-2 text-muted-foreground">All sources are listed publicly. MVP uses mocked signals; the schema and adapters are ready for live feeds.</p>
          </div>
          <Button asChild variant="outline"><Link to="/sources"><Database className="mr-1.5 h-4 w-4" />View registry</Link></Button>
        </div>
        <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {["NOAA / NWS alerts", "FEMA disaster declarations", "USDA food access", "County food insecurity (Map the Meal Gap)", "Social Vulnerability Index (CDC)", "Community price reports", "Responder capacity declarations", "Road disruption feeds", "NDVI / vegetation anomalies"].map((s) => (
            <div key={s} className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm">
              <Activity className="h-3.5 w-3.5 text-primary" /> {s}
            </div>
          ))}
        </div>
      </Section>

      {/* Footer */}
      <footer className="bg-card">
        <div className="container flex flex-col gap-3 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>FoodReady — Anticipatory food access & disaster coordination · MVP demo build.</p>
          <div className="flex gap-4">
            <Link to="/transparency" className="hover:text-foreground">Transparency</Link>
            <Link to="/sources" className="hover:text-foreground">Data sources</Link>
            <Link to="/admin" className="hover:text-foreground">Admin</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Landing;
