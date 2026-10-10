import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager"]}>
      <Placeholder title="Onboarding" phase="F3" />
    </RoleGate>
  );
}
