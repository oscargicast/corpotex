import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Placeholder title="Rutas" phase="F3" />
    </RoleGate>
  );
}
