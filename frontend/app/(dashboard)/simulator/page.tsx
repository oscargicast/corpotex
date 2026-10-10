"use client";

import { Suspense } from "react";
import { RoleGate } from "@/components/require-auth";
import { Simulator } from "@/components/simulator/simulator";

export default function SimulatorPage() {
  return (
    <RoleGate roles={["manager"]}>
      <Suspense>
        <Simulator />
      </Suspense>
    </RoleGate>
  );
}
