"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import IncidentDrawer from "@/components/incident-drawer";
import { Marker } from "@/components/ui";

type Toast = { message: string; incidentId?: string };
type App = { toast: (message: string, incidentId?: string) => void; openIncident: (id: string) => void };

const AppContext = createContext<App>({ toast: () => undefined, openIncident: () => undefined });

export function useApp() {
  return useContext(AppContext);
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const showToast = useCallback((message: string, id?: string) => {
    clearTimeout(timer.current);
    setToast({ message, incidentId: id });
    timer.current = setTimeout(() => setToast(null), 4500);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const value = useMemo(() => ({ toast: showToast, openIncident: setIncidentId }), [showToast]);

  return (
    <AppContext.Provider value={value}>
      {children}
      {incidentId ? <IncidentDrawer id={incidentId} onClose={() => setIncidentId(null)} onOpen={setIncidentId} toast={showToast} /> : null}
      <div aria-live="polite" className="fixed bottom-6 right-6 z-30">
        {toast ? (
          <div className="flex items-center gap-3.5 rounded-[10px] border-l-[3px] border-brand-500 bg-ink py-3.5 pl-4 pr-4 text-fog-100 shadow-[0_14px_40px_rgba(20,22,25,.35)] motion-safe:animate-slide-in">
            <Marker className="h-2 w-2 bg-brand-400" />
            <span className="text-[13.5px]">{toast.message}</span>
            {toast.incidentId ? (
              <button
                className="p-0 text-[13px] font-semibold text-brand-300 hover:text-white"
                onClick={() => {
                  setIncidentId(toast.incidentId || null);
                  setToast(null);
                }}
              >
                Review →
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </AppContext.Provider>
  );
}
