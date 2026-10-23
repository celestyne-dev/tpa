import { Workflow } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BlockEditor } from "../../components/BlockEditor";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { SelectField, TextField } from "../../components/Fields";
import { EMAIL_BLOCKS, PREFERENCES } from "../../components/newsletterLabels";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

const STATUS = { draft: "Draft", active: "Active", paused: "Paused" };

function describeDelay(minutes) {
  if (!minutes) return "immediately";
  if (minutes % 1440 === 0) return `after ${minutes / 1440} day${minutes === 1440 ? "" : "s"}`;
  if (minutes % 60 === 0) return `after ${minutes / 60} hour${minutes === 60 ? "" : "s"}`;
  return `after ${minutes} minutes`;
}

export function AutomationsPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.emailAutomations.list(), []);
  return (
    <>
      <AdminPageHeader
        title="Automations"
        description="Simple, reliable email sequences. Starters are drafts until you review their emails and activate them."
        breadcrumbs={[{ label: "Automations" }]}
      />
      {error ? (
        <ErrorState title="We couldn't load automations" onRetry={reload} />
      ) : (
        <>
          {(data ?? []).length === 0 && !loading && can("email_automations.manage") && (
            <Button
              className="mb-4"
              onClick={async () => {
                await api.emailTemplates.addStarters();
                reload();
              }}
            >
              Add the starter automations
            </Button>
          )}
          <DataTable
            caption="Automations"
            rows={data}
            loading={loading}
            empty={{ icon: Workflow, title: "No automations yet" }}
            columns={[
              {
                key: "name",
                header: "Automation",
                render: (a) => (
                  <div>
                    <Link
                      to={`/admin/email-automations/${a.id}`}
                      className="font-medium hover:underline"
                    >
                      {a.name}
                    </Link>
                    <p className="text-xs text-muted">{a.trigger_label}</p>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (a) => <StatusBadge status={STATUS[a.status]} />,
              },
              { key: "steps", header: "Emails", render: (a) => a.step_count },
              {
                key: "enrolled",
                header: "Enrolments",
                render: (a) =>
                  Object.entries(a.enrollments)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(" · ") || "None yet",
              },
            ]}
          />
        </>
      )}
    </>
  );
}

export function AutomationDetailPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const { data, error, reload, setData } = useAdminQuery(() => api.emailAutomations.get(id), [id]);
  if (error) return <ErrorState title="We couldn't load this automation" onRetry={reload} />;
  if (!data) return <p className="text-muted">Loading…</p>;
  return <AutomationEditor key={`${data.id}:${data.updated_at}`} data={data} setData={setData} />;
}

function AutomationEditor({ data, setData }) {
  const id = data.id;
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const segments = useAdminQuery(() => api.segments.list(), []);
  const [steps, setSteps] = useState(() => data.steps.map((s) => ({ ...s })));
  const [saveError, setSaveError] = useState(null);
  const manage = can("email_automations.manage");
  const locked = data.status === "active";
  const update = async (body) => {
    setSaveError(null);
    try {
      setData((await api.emailAutomations.update(id, body)).data);
      notify("Saved.");
    } catch (err) {
      setSaveError(err);
      notify(err.message, "error");
    }
  };
  const saveSteps = async () => {
    setSaveError(null);
    try {
      const res = await api.emailAutomations.replaceSteps(
        id,
        steps.map(({ delay_minutes, subject, preheader, blocks }) => ({
          delay_minutes,
          subject,
          preheader,
          blocks,
        })),
      );
      setData(res.data);
      notify("Emails saved.");
    } catch (err) {
      setSaveError(err);
    }
  };
  return (
    <>
      <AdminPageHeader
        title={data.name}
        description={`${data.trigger_label} · ${STATUS[data.status]}`}
        breadcrumbs={[
          { label: "Automations", to: "/admin/email-automations" },
          { label: data.name },
        ]}
        actions={
          manage && (
            <div className="flex gap-2">
              {data.status !== "active" ? (
                <Button onClick={() => update({ status: "active" })}>Activate</Button>
              ) : (
                <Button variant="outline" onClick={() => update({ status: "paused" })}>
                  Pause
                </Button>
              )}
            </div>
          )
        }
      />
      {saveError && (
        <div role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-900">
          {saveError.message}{" "}
          {fieldError(saveError, "status") || fieldError(saveError, "steps") || ""}
        </div>
      )}
      <p className="mb-6 max-w-3xl text-sm text-muted">{data.description}</p>
      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <section className="space-y-4" aria-labelledby="steps-h">
          <h2 id="steps-h" className="text-lg font-medium">
            Emails in order
          </h2>
          {locked && (
            <p className="rounded-xl bg-gold-100 p-3 text-sm">
              Pause the automation to edit its emails.
            </p>
          )}
          {steps.map((step, i) => (
            <fieldset
              key={i}
              disabled={!manage || locked}
              className="space-y-3 rounded-2xl bg-white p-5 shadow-sm"
            >
              <legend className="text-sm font-semibold">
                Email {i + 1} · sent {describeDelay(step.delay_minutes)}{" "}
                {i === 0 ? "after the trigger" : "after the previous email"}
              </legend>
              <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
                <TextField
                  label="Subject"
                  value={step.subject}
                  onChange={(e) =>
                    setSteps(steps.map((s, j) => (j === i ? { ...s, subject: e.target.value } : s)))
                  }
                />
                <TextField
                  label="Delay (hours)"
                  type="number"
                  min={0}
                  value={Math.round(step.delay_minutes / 60)}
                  onChange={(e) =>
                    setSteps(
                      steps.map((s, j) =>
                        j === i ? { ...s, delay_minutes: Number(e.target.value) * 60 } : s,
                      ),
                    )
                  }
                />
              </div>
              <TextField
                label="Preheader"
                value={step.preheader}
                onChange={(e) =>
                  setSteps(steps.map((s, j) => (j === i ? { ...s, preheader: e.target.value } : s)))
                }
              />
              <BlockEditor
                legend="Email content"
                allowed={EMAIL_BLOCKS}
                blocks={step.blocks}
                onChange={(blocks) =>
                  setSteps(steps.map((s, j) => (j === i ? { ...s, blocks } : s)))
                }
              />
              {steps.length > 1 && (
                <Button variant="ghost" onClick={() => setSteps(steps.filter((_, j) => j !== i))}>
                  Remove this email
                </Button>
              )}
            </fieldset>
          ))}
          {manage && !locked && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() =>
                  setSteps([
                    ...steps,
                    { delay_minutes: 1440, subject: "", preheader: "", blocks: [] },
                  ])
                }
              >
                Add an email
              </Button>
              <Button onClick={saveSteps}>Save emails</Button>
            </div>
          )}
        </section>
        <aside className="space-y-4">
          <section className="space-y-3 rounded-2xl bg-white p-5 shadow-sm">
            <h2 className="font-medium">Audience and exit rules</h2>
            <SelectField
              label="Segment"
              disabled={!manage}
              value={data.segment_id ? String(data.segment_id) : ""}
              onChange={(e) =>
                update({ segment_id: e.target.value ? Number(e.target.value) : null })
              }
              options={[
                { value: "", label: "All confirmed subscribers" },
                ...(segments.data ?? []).map((s) => ({ value: String(s.id), label: s.name })),
              ]}
            />
            <SelectField
              label="Only subscribers who chose"
              disabled={!manage || data.trigger === "product_published"}
              value={data.required_preference}
              onChange={(e) => update({ required_preference: e.target.value })}
              options={[
                { value: "", label: "Any preference" },
                ...Object.entries(PREFERENCES).map(([value, label]) => ({ value, label })),
              ]}
            />
            {data.trigger === "inactive" && (
              <TextField
                label="Inactive for (days)"
                type="number"
                disabled={!manage}
                defaultValue={data.settings.inactive_days ?? 180}
                onBlur={(e) =>
                  update({ settings: { ...data.settings, inactive_days: Number(e.target.value) } })
                }
              />
            )}
            <TextField
              label="Exit when tagged (tag slug, optional)"
              disabled={!manage}
              defaultValue={data.settings.exit_tag ?? ""}
              onBlur={(e) =>
                update({ settings: { ...data.settings, exit_tag: e.target.value || undefined } })
              }
            />
            <p className="text-xs text-muted">
              Everyone leaves a sequence immediately when they unsubscribe, bounce, complain or
              remove the required preference. Nobody is enrolled twice for the same trigger.
            </p>
          </section>
          <section className="space-y-2 rounded-2xl bg-white p-5 shadow-sm">
            <h2 className="font-medium">Sending history</h2>
            <p className="text-sm">
              {Object.entries(data.messages)
                .map(([k, v]) => `${v} ${k}`)
                .join(" · ") || "No emails sent yet."}
            </p>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-xs">
              {data.recent_enrollments.map((e) => (
                <li key={e.id}>
                  {e.email} · {e.status}
                  {e.exit_reason && ` (${e.exit_reason})`} · {formatDateTime(e.enrolled_at)}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </>
  );
}
