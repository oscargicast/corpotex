"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { RoleGate } from "@/components/require-auth";
import FleetView from "./fleet-view";
import SceneView from "./scene-view";

export default function RoutesPage() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Suspense>
        <Routes />
      </Suspense>
    </RoleGate>
  );
}

// The Redistribución card opens /routes?before=&after= (ADR 0024): that scene
// keeps its own view. Everything else is the fleet (ADR 0026).
function Routes() {
  const params = useSearchParams();
  return params.get("before") && params.get("after") ? <SceneView /> : <FleetView />;
}
