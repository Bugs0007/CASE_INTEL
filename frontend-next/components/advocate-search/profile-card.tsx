"use client";

import { useState } from "react";
import { AlertTriangle, Pencil, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateProfile, useNameAction, useUpdateProfile } from "@/hooks/use-advocate-search-v2";
import { nameTokens } from "@/lib/advocate-search-results";
import type { AdvocateSearchProfile } from "@/types";
import { apiErrorText } from "./errors";
import { NameFormChips, NotMeChips } from "./name-form-chips";
import { Eyebrow, MatchChip, Notice, Panel } from "./ui";

const BAR_CODE_RE = /^[A-Za-z]{2,3}\/\d+\/\d{4}$/;

/** Up to four example rows for "How each row will be labelled", built from the
 * profile's own names: a spelling with an initial, one without, and two that are
 * rejected. */
function labelExamples(profile: AdvocateSearchProfile) {
  const rows: { name: string; note?: string; status: "matched" | "check" | "excluded"; label?: string }[] = [];
  const strong = profile.name_forms.find((f) => nameTokens(f).length >= 2);
  const single = profile.name_forms.find((f) => nameTokens(f).length < 2);
  if (strong) rows.push({ name: strong, status: "matched" });
  if (single) rows.push({ name: single, note: "(no initial)", status: "check", label: "Check name, you decide" });
  for (const name of profile.excluded_names.slice(0, strong && single ? 2 : 3)) rows.push({ name, status: "excluded" });
  return rows;
}

/** Who to search: the advocate's bar number, the spellings they appear under,
 * the ones that are not them, what will go to eCourts, and how rows will be
 * labelled. Everything shown comes from the server's profile (the queries from the
 * same function the search uses). */
export function AdvocateProfileCard({ profile }: { profile: AdvocateSearchProfile }) {
  const update = useUpdateProfile();
  const nameAction = useNameAction(null);
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(profile.display_name);
  const [barCode, setBarCode] = useState(profile.bar_codes[0] ?? "");
  const [formError, setFormError] = useState("");

  const failure = update.error ?? nameAction.error;
  const busy = update.isPending || nameAction.isPending;
  const patch = (body: Parameters<typeof update.mutate>[0]["body"]) => update.mutate({ id: profile.id, body });

  const save = () => {
    const code = barCode.trim().toUpperCase();
    if (code && !BAR_CODE_RE.test(code)) {
      setFormError("A bar number looks like STATE/NUMBER/YEAR, for example TS/1234/2009.");
      return;
    }
    setFormError("");
    update.mutate(
      { id: profile.id, body: { display_name: displayName.trim() || profile.display_name, bar_codes: code ? [code] : [] } },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <Panel
      title="Who to search"
      icon={<User className="h-[17px] w-[17px]" />}
      sub={`Advocate profile: ${profile.display_name}`}
      label="Who to search"
      className="h-full"
      bodyClassName="gap-3 overflow-y-auto"
      action={
        <Button variant="secondary" size="sm" onClick={() => setEditing((v) => !v)} aria-expanded={editing}>
          <Pencil className="h-3 w-3" />
          Edit profile
        </Button>
      }
    >
      {editing && (
        <div className="grid gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 sm:grid-cols-2">
          <label className="text-xs text-gray-600">
            Full name
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="mt-1" />
          </label>
          <label className="text-xs text-gray-600">
            Bar enrolment number
            <Input value={barCode} onChange={(e) => setBarCode(e.target.value)} placeholder="TS/1234/2009" className="mt-1 font-mono" />
          </label>
          {formError && <p className="text-xs text-status-alert sm:col-span-2">{formError}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <Button size="sm" onClick={save} disabled={update.isPending}>
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div>
        <Eyebrow>Bar enrolment number (exact, fastest)</Eyebrow>
        {profile.bar_codes.length > 0 ? (
          <div className="flex h-9 items-center gap-2 rounded-md border border-gray-300 bg-surface px-3 font-mono text-sm">
            <span className="flex-1 truncate">{profile.bar_codes.join(", ")}</span>
            <span className="rounded-full bg-status-ok-soft px-2 py-0.5 font-sans text-[11px] font-semibold text-status-ok">Exact match</span>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex h-9 w-full items-center rounded-md border border-dashed border-gray-400 px-3 text-left text-sm text-gray-600 hover:bg-gray-50"
          >
            Add your bar enrolment number
          </button>
        )}
        <p className="mt-1 text-xs text-gray-500">Used first on courts that support it. Nothing else shows up in results.</p>
      </div>

      <div>
        <Eyebrow>Names I appear under (we only keep results that match one of these)</Eyebrow>
        <NameFormChips
          forms={profile.name_forms}
          suggestions={profile.suggestions}
          busy={busy}
          onRemove={(name) => patch({ name_forms: profile.name_forms.filter((f) => f !== name) })}
          onAdd={(name) => nameAction.mutate({ profileId: profile.id, name, action: "add" })}
        />
      </div>

      <div>
        <Eyebrow>Not me (rejected from every search)</Eyebrow>
        <NotMeChips
          names={profile.excluded_names}
          busy={busy}
          onRemove={(name) => patch({ excluded_names: profile.excluded_names.filter((n) => n !== name) })}
        />
      </div>

      <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 text-[13px] leading-relaxed" data-testid="what-goes-to-ecourts">
        <b className="font-semibold">What goes to eCourts:</b>{" "}
        {profile.query_count === 0 ? (
          "nothing yet. Add a name form of three or more letters."
        ) : (
          <>
            {profile.query_count} short {profile.query_count === 1 ? "query" : "queries"},{" "}
            {profile.queries.map((q, i) => (
              <span key={q}>
                {i > 0 && (i === profile.queries.length - 1 ? " and " : ", ")}
                <b className="font-semibold">{q}</b>
              </span>
            ))}
            . Shorter queries catch every form of your name; the rest is filtered here, so you don&apos;t scroll through other{" "}
            {profile.queries[0]}s.
          </>
        )}
      </div>
      {profile.query_warning && (
        <Notice tone="warn">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{profile.query_warning}</span>
        </Notice>
      )}

      <div>
        <Eyebrow>How each row will be labelled</Eyebrow>
        <dl className="grid grid-cols-[minmax(0,132px)_1fr] items-center gap-x-3 gap-y-1.5 text-[13px]">
          {labelExamples(profile).map((row) => (
            <div key={row.name} className="contents">
              <dt className="truncate">
                <b className="font-semibold">{row.name}</b> {row.note && <span className="text-gray-500">{row.note}</span>}
              </dt>
              <dd>
                <MatchChip status={row.status} label={row.label} />
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <Notice className="[@media(max-height:800px)]:hidden">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          Court sites list the same advocate in many spellings. Add every spelling you have seen, and use Not me on a row to reject
          that name for good.
        </span>
      </Notice>
      {failure && <p className="text-xs text-status-alert">{apiErrorText(failure, "Could not save that change.")}</p>}
    </Panel>
  );
}

/** Shown until the advocate has a search profile: the minimum to start one. */
export function CreateProfileCard() {
  const create = useCreateProfile();
  const [displayName, setDisplayName] = useState("");
  const [barCode, setBarCode] = useState("");
  const [error, setError] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const code = barCode.trim().toUpperCase();
    if (!displayName.trim()) return setError("Enter your name as you would write it.");
    if (code && !BAR_CODE_RE.test(code)) return setError("A bar number looks like STATE/NUMBER/YEAR, for example TS/1234/2009.");
    setError("");
    const parts = displayName.trim().split(/\s+/);
    create.mutate(
      {
        display_name: displayName.trim(),
        bar_codes: code ? [code] : [],
        // The full name is the first spelling; the card suggests the usual variants.
        name_forms: parts.length > 1 ? [parts[0]] : parts,
      },
      { onError: (err) => setError(apiErrorText(err, "Could not create the profile.")) },
    );
  };

  return (
    <Panel title="Who to search" icon={<User className="h-[17px] w-[17px]" />} sub="Set up once" label="Who to search" className="h-full">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm text-gray-600">
          Court sites list an advocate under many spellings. Tell us who you are once; you can add spellings and reject other advocates
          afterwards.
        </p>
        <label className="text-xs text-gray-600">
          Your full name
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name as on the Bar roll" className="mt-1" />
        </label>
        <label className="text-xs text-gray-600">
          Bar enrolment number <span className="text-gray-400">(optional, exact and fastest)</span>
          <Input value={barCode} onChange={(e) => setBarCode(e.target.value)} placeholder="TS/1234/2009" className="mt-1 font-mono" />
        </label>
        {error && <p className="text-xs text-status-alert">{error}</p>}
        <Button type="submit" disabled={create.isPending} className="self-start">
          Create profile
        </Button>
      </form>
    </Panel>
  );
}
