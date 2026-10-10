import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager"]}>
      <Placeholder title="Proveedores y talleres" phase="F2" />
    </RoleGate>
  );
}
