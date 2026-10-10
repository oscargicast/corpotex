import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager"]}>
      <Placeholder title="Simulador" phase="F3" />
    </RoleGate>
  );
}
