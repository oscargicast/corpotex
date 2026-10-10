import { Placeholder } from "@/components/placeholder";
import { RoleGate } from "@/components/require-auth";

export default function Page() {
  return (
    <RoleGate roles={["manager"]}>
      <Placeholder title="Estilo del Gerente" phase="F3" />
    </RoleGate>
  );
}
