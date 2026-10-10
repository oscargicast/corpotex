import { AssistantChat } from "@/components/assistant/chat";

// Full screen on a phone (bottom tab); on desktop the same chat lives in the side panel.
export default function AssistantPage() {
  return (
    <section className="-mx-4 -mb-24 -mt-4 flex h-[calc(100dvh-3.5rem-4rem)] flex-col md:-mx-6 md:-mb-8 md:h-[calc(100dvh-3.5rem)]">
      <h1 className="sr-only">Asistente</h1>
      <AssistantChat />
    </section>
  );
}
