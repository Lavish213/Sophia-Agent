"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/leads", label: "Leads" },
  { href: "/calls", label: "Calls" },
  { href: "/properties", label: "Properties" },
  { href: "/discovered", label: "Discovered" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <nav className="flex items-center justify-between border-b border-white/10 px-6 py-4">
      <div className="flex items-center gap-6">
        <span className="font-semibold text-white">Sophia Agent</span>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={
              pathname === link.href
                ? "text-white"
                : "text-white/50 hover:text-white/80"
            }
          >
            {link.label}
          </Link>
        ))}
      </div>
      <button onClick={handleSignOut} className="text-sm text-white/50 hover:text-white/80">
        Sign out
      </button>
    </nav>
  );
}
