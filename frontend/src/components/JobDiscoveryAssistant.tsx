"use client";

import { FormEvent, useState } from "react";
import { api, type Job, type JobAssistantIntent, type JobAssistantMessage } from "@/lib/api";
import JobCard from "@/components/JobCard";

const EXAMPLES = [
  "Backend con Go, remoto desde Argentina y sin liderazgo de personas",
  "Mi primer rol en datos: manejo Python y SQL",
  "Producto técnico en startups, remoto worldwide",
];

interface Props {
  onAppliedChange: (jobId: string, applied: boolean) => void;
  onDismissedChange: (jobId: string, dismissed: boolean) => void;
}

export default function JobDiscoveryAssistant({ onAppliedChange, onDismissedChange }: Props) {
  const [messages, setMessages] = useState<JobAssistantMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [intent, setIntent] = useState<JobAssistantIntent | null>(null);
  const [matches, setMatches] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [monitoring, setMonitoring] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const send = async (event?: FormEvent, example?: string) => {
    event?.preventDefault();
    const content = (example ?? draft).trim();
    if (!content || loading) return;
    const next = [...messages, { role: "user" as const, content }].slice(-6);
    setMessages(next);
    setDraft("");
    setError("");
    setStatus("");
    setLoading(true);
    try {
      const response = await api.queryJobAssistant(next);
      setIntent(response.intent);
      setMatches(response.matches);
      setMessages([...next, { role: "assistant" as const, content: response.intent.reply }].slice(-6));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude interpretar la búsqueda.");
    } finally {
      setLoading(false);
    }
  };

  const monitor = async () => {
    if (!intent || !intent.job_title || intent.needs_clarification) return;
    setMonitoring(true);
    setError("");
    try {
      const response = await api.monitorAssistantSearch(intent);
      setStatus(response.triggered
        ? "Listo: activé el monitoreo y pedí una búsqueda nueva. Los resultados llegan en unos minutos."
        : "Guardé el monitoreo. La corrida no pudo iniciarse ahora; se ejecutará en la próxima ventana programada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude activar el monitoreo.");
    } finally {
      setMonitoring(false);
    }
  };

  return (
    <section className="discovery-hero" aria-labelledby="discovery-title">
      <div className="discovery-copy">
        <p className="eyebrow">Descubrimiento asistido</p>
        <h1 id="discovery-title">Encontremos la vacante<br />que estás buscando.</h1>
        <p>Describila con tus palabras. Voy a revisar tus coincidencias guardadas y preparar un monitoreo para que lo confirmes.</p>
      </div>
      <form onSubmit={send} className="discovery-composer">
        <label htmlFor="job-assistant-input" className="sr-only">Describí el trabajo que buscás</label>
        <textarea
          id="job-assistant-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ej. Backend con Go, remoto y sin management"
          rows={3}
          maxLength={1500}
        />
        <div className="discovery-composer-footer">
          <span>Enter para buscar · Shift + Enter para otra línea</span>
          <button type="submit" className="btn-primary" disabled={loading || !draft.trim()}>
            {loading ? "Pensando…" : "Buscar vacantes"}
          </button>
        </div>
      </form>
      <div className="discovery-examples" aria-label="Ejemplos de búsqueda">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" onClick={() => send(undefined, example)} disabled={loading}>
            {example}
          </button>
        ))}
      </div>

      {(messages.length > 0 || error || status) && (
        <div className="assistant-response" aria-live="polite">
          {messages.filter((message) => message.role === "assistant").slice(-1).map((message) => <p key={message.content}>{message.content}</p>)}
          {intent && !intent.needs_clarification && intent.job_title && (
            <div className="assistant-proposal">
              <span>Monitorear: <strong>{intent.job_title}</strong>{intent.location_filter ? ` · ${intent.location_filter}` : ""}</span>
              <button type="button" className="btn-ghost text-sm" onClick={monitor} disabled={monitoring}>
                {monitoring ? "Activando…" : "Monitorear esta búsqueda"}
              </button>
            </div>
          )}
          {error && <p className="text-sm text-red-500">{error}</p>}
          {status && <p className="text-sm text-emerald-700 dark:text-emerald-300">{status}</p>}
        </div>
      )}

      {intent && (
        <div className="assistant-matches">
          <div className="section-heading">
            <div><p className="eyebrow">Para vos</p><h2>Coincidencias guardadas</h2></div>
            <span>{matches.length} encontradas</span>
          </div>
          {matches.length === 0 ? (
            <p className="empty-discovery">Todavía no hay coincidencias guardadas. Podés activar el monitoreo para traer oportunidades nuevas.</p>
          ) : (
            <div className="space-y-3">
              {matches.map((job) => (
                <JobCard
                  key={job.job_id}
                  job={job}
                  onAppliedChange={(jobId, applied) => {
                    setMatches((current) => current.filter((item) => item.job_id !== jobId || !applied));
                    onAppliedChange(jobId, applied);
                  }}
                  onDismissedChange={(jobId, dismissed) => {
                    setMatches((current) => current.filter((item) => item.job_id !== jobId || !dismissed));
                    onDismissedChange(jobId, dismissed);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
