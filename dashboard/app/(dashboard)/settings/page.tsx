import HealthStatus from "@/components/HealthStatus";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">System health</h2>
        <HealthStatus />
      </section>
    </div>
  );
}
