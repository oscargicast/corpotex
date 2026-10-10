import { RequireAuth } from "@/components/require-auth";
import { Shell } from "@/components/shell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <Shell>{children}</Shell>
    </RequireAuth>
  );
}
