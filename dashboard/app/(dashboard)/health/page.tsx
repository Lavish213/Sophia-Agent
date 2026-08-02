import WorkerHealth from "@/components/WorkerHealth";
import HealthStatus from "@/components/HealthStatus";

export default function HealthPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">System health</h1>
        <p className="text-white/50">
          Whether Bob, the dialer, and discovery are actually running. A worker that dies quietly
          costs a day of calls before anyone notices.
        </p>
      </div>

      <WorkerHealth />

      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Providers</h2>
        <HealthStatus />
      </section>
    </div>
  );
}
