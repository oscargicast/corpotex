import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager"]}>
      <Placeholder title="Conexión con Claude" phase="F2" />
    </RoleGate>
  );
}
