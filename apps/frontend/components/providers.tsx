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
      {/* On a phone the toast spans the width just above the tab bar. */}
      <div aria-live="polite" className="fixed inset-x-4 bottom-[calc(76px+env(safe-area-inset-bottom))] z-30 md:inset-x-auto md:bottom-6 md:right-6">
        {/* A new alert, the only toast that carries an incident to review, is red with a blinking dot so it stands out from routine confirmations. */}
        {toast ? (
          <div className={`flex items-center gap-3.5 rounded-[10px] py-3.5 pl-4 pr-4 motion-safe:animate-slide-in ${toast.incidentId ? "bg-danger-600 text-white shadow-[0_14px_40px_rgba(179,18,47,.4)]" : "border-l-[3px] border-brand-500 bg-ink text-fog-100 shadow-[0_14px_40px_rgba(10,21,37,.35)]"}`}>
            <Marker className={toast.incidentId ? "h-2 w-2 bg-white motion-safe:animate-rec" : "h-2 w-2 bg-brand-400"} />
            <span className="min-w-0 flex-1 text-[13.5px]">{toast.message}</span>
            {toast.incidentId ? (
              <button
                className="whitespace-nowrap rounded-md bg-white/15 px-2.5 py-1 text-[13px] font-semibold text-white hover:bg-white/25"
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
