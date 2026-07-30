import SellForm from "@/components/SellForm";

export const metadata = {
  title: "Sell your house fast in San Joaquin County | San Joaquin House Buyers",
  description:
    "Get a no-obligation cash offer on your San Joaquin County property. No agents, no commissions, no repairs.",
};

export default function SellPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-3xl font-semibold">Get a cash offer on your house</h1>
      <p className="mt-3 text-white/60">
        We buy houses across San Joaquin County, as-is. No agents, no commissions, and no repairs on
        your end. Tell us about the property and we&apos;ll reach out with a no-obligation offer range.
      </p>

      <div className="mt-8">
        <SellForm />
      </div>

      <p className="mt-8 text-xs text-white/40">
        By submitting this form you agree to be contacted by phone, text, or email about your
        property. Message and data rates may apply. Reply STOP to any text to opt out.
      </p>
    </main>
  );
}
