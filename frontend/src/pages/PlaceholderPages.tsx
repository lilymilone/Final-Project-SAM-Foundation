import { AgentPanel } from "../components/AgentPanel";
import { DraftsPanel, FindingsPanel } from "../components/outputs";
import { RunLauncher } from "../components/RunLauncher";
import { PageHeader } from "../components/ui";

export function MissionDiscoveryPage() {
  return (
    <>
      <PageHeader eyebrow="Mission Discovery" title="Find the people already doing this work"
        subtitle="Mental-health and eating-disorder organizations, research initiatives, awareness events, and partners. Every link is checked, and every claim shows its source." />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <RunLauncher title="Research a question" intent="mission_discovery" mode="live" lockIntent
            examples={["Find eating disorder research initiatives and awareness events in New York or Connecticut we could support",
              "Which mental-health nonprofits run peer-support programs for college students in Connecticut?"]} />
          <FindingsPanel />
        </div>
        <AgentPanel agents={["mission_discovery"]} upcoming={[]} />
      </div>
    </>
  );
}

export function PartnershipsPage() {
  return (
    <>
      <PageHeader eyebrow="Partnerships & Outreach" title="Warm, thoughtful outreach, reviewed by you"
        subtitle="Sponsor research and personalized partnership and venue-inquiry drafts. A person always reviews and sends them outside SAM SPACE." />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <RunLauncher title="Find partners and draft outreach" intent="partnership_outreach" mode="live" lockIntent
            examples={["Find local wellness businesses in New Haven that sponsor mental-health causes and draft outreach",
              "Draft partnership inquiries to the opportunities we saved in Mission Discovery"]} />
          <DraftsPanel kind="outreach" title="Drafts awaiting review" />
        </div>
        <AgentPanel agents={["partnerships_outreach"]} upcoming={[]} />
      </div>
    </>
  );
}
