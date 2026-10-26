import { BookHeart, CircleHelp, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { AgentPanel } from "../components/AgentPanel";
import { AckGuide } from "../components/donations";
import { FinanceTerms } from "../components/studio";
import { Card, PageHeader } from "../components/ui";
import { MissionCriteria, OutreachRestriction } from "./PlaceholderPages";

const ALL_AGENTS = ["orchestrator", "mission_discovery", "fundraising_events", "financial_analysis", "donations_compliance",
  "partnerships_outreach", "event_intelligence"];

/** How SAM SPACE works. Kept here so the working pages stay focused on getting things done. */
export default function HelpPage() {
  return (
    <>
      <PageHeader eyebrow="Help" title="How SAM SPACE works" />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Card title="The basics" icon={<CircleHelp size={16} aria-hidden="true" />}>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-ink/90">
              <li>You ask for something: plan an event, find a cause, review finances or donations.</li>
              <li>The <b className="text-plum">Orchestrator</b> splits the work and hands each part to a specialist agent. You can watch every step live.</li>
              <li>Each specialist reports back with its findings, sources, assumptions, risks, and money considerations. The Orchestrator checks them against budgets and past lessons, asks for one revision if something conflicts, and prepares drafts when an opportunity looks promising.</li>
              <li>You review the results and decide. <b className="text-plum">Nothing is ever sent, booked, paid, or donated by SAM SPACE.</b> Drafts are copied and sent by a person.</li>
            </ol>
            <p className="mt-3 text-sm text-muted">Every step, tool call, token, and cost is in <Link to="/activity" className="text-royal underline">Agent Activity</Link>.
              Limits, permissions, and safety test results are in <Link to="/safety" className="text-royal underline">Analytics &amp; Safety</Link>.</p>
          </Card>
          <Card title="What the agents know about us" icon={<BookHeart size={16} aria-hidden="true" />}>
            <p className="text-sm text-ink/90">
              The <Link to="/settings/knowledge" className="text-royal underline">Foundation Knowledge Base</Link> holds what the board has recorded
              about the foundation: its signature events, vendors, the organizations it already knows, its community, and how it
              introduces itself. Each agent reads only the few facts its task needs, says which ones it relied on, and treats
              anything not verified as reported or approximate. Past costs are never treated as money available today.
            </p>
          </Card>
          <AgentPanel agents={ALL_AGENTS} upcoming={[]} title="The seven agents and their tools" />
        </div>
        <div className="min-w-0 space-y-5">
          <MissionCriteria />
          <OutreachRestriction />
          <AckGuide />
          <Card title="Money terms" icon={<ShieldCheck size={16} aria-hidden="true" />}><FinanceTerms /></Card>
        </div>
      </div>
    </>
  );
}
