import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Butterfly } from "./butterflies/Butterfly";
import { ButterflyProvider } from "./butterflies/ButterflyProvider";
import { Layout } from "./components/Layout";
import ActivityPage from "./pages/ActivityPage";
import DonationsPage from "./pages/DonationsPage";
import EventStudioPage from "./pages/EventStudioPage";
import FinancePage from "./pages/FinancePage";
import LegacyEventPage from "./pages/LegacyEventPage";
import LegacyPage from "./pages/LegacyPage";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import PacketPage from "./pages/PacketPage";
import PartnershipPacketPage from "./pages/PartnershipPacketPage";
import RunPage from "./pages/RunPage";
import { MissionDiscoveryPage, PartnershipsPage } from "./pages/PlaceholderPages";
import SafetyPage from "./pages/SafetyPage";
import SettingsPage from "./pages/SettingsPage";

function Splash() {
  return (
    <div className="app-backdrop grid min-h-screen place-items-center" role="status" aria-label="Loading SAM SPACE">
      <div className="flex flex-col items-center gap-3">
        <Butterfly size={56} motion="still" />
        <span className="wordmark text-xl text-plum">SAM SPACE</span>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Splash />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function Shell() {
  const { user, loading } = useAuth();
  if (loading) return <Splash />;
  return (
    <ButterflyProvider enabled={user?.settings.animations_enabled ?? true}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<OverviewPage />} />
          <Route path="mission" element={<MissionDiscoveryPage />} />
          <Route path="events" element={<EventStudioPage />} />
          <Route path="events/packets/:id" element={<PacketPage />} />
          <Route path="partnerships/packets/:id" element={<PartnershipPacketPage />} />
          <Route path="finance" element={<FinancePage />} />
          <Route path="donations" element={<DonationsPage />} />
          <Route path="partnerships" element={<PartnershipsPage />} />
          <Route path="legacy" element={<LegacyPage />} />
          <Route path="legacy/:id" element={<LegacyEventPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="activity/runs/:id" element={<RunPage />} />
          <Route path="safety" element={<SafetyPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ButterflyProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
