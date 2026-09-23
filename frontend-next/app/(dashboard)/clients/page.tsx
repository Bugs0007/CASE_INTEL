"use client";

import { useState } from "react";
import { Building2, FileDown, Loader2, Pencil, Plus, Trash2, User, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import {
  useClients,
  useCreateClient,
  useDeleteClient,
  useUpdateClient,
  useViewClientStatement,
} from "@/hooks/use-clients";
import { apiErrorDetail } from "@/lib/api/client";
import type { Client, ClientInput, ClientType } from "@/types";

const EMPTY: ClientInput = { name: "", client_type: "individual", gstin: "", email: "", phone: "", address: "", notes: "" };

/** Clients as billing entities: one per person or business you bill,
 * shared by all their cases. The type and GSTIN decide the tax line on
 * invoices (a business client's invoices say tax is payable on reverse
 * charge by the recipient; nothing is computed). */
export default function ClientsPage() {
  const [search, setSearch] = useState("");
  const { data: clients = [], isLoading } = useClients(search.trim() || undefined);
  const [editing, setEditing] = useState<Client | "new" | null>(null);
  const deleteClient = useDeleteClient();
  const viewStatement = useViewClientStatement();

  async function handleDelete(client: Client) {
    if (!confirm(`Delete ${client.name}? Their cases stay, just unlinked.`)) return;
    try {
      await deleteClient.mutateAsync(client.id);
      showToast.success("Client deleted");
    } catch (e) {
      showToast.error("Could not delete", apiErrorDetail(e, "Please try again."));
    }
  }

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[900px] mx-auto space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-page-title text-gray-900 mb-1.5">Clients</h1>
          <p className="text-sm text-gray-600">Who you bill. Link cases to a client from the case&apos;s Edit Details.</p>
        </div>
        <Button size="sm" onClick={() => setEditing("new")}>
          <Plus className="h-4 w-4" />
          New client
        </Button>
      </div>

      {editing !== null && (
        <ClientForm
          key={editing === "new" ? "new" : editing.id}
          client={editing === "new" ? null : editing}
          onDone={() => setEditing(null)}
        />
      )}

      <Input
        aria-label="Search clients"
        placeholder="Search by name"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-xs"
      />

      {isLoading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : clients.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-gray-500">
            No clients yet. Add one here, then link cases to it from each case&apos;s Edit Details.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {clients.map((client) => (
            <div key={client.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-surface px-4 py-3">
              {client.client_type === "business" ? (
                <Building2 className="h-5 w-5 text-gray-400" />
              ) : (
                <User className="h-5 w-5 text-gray-400" />
              )}
              <div className="flex-1 min-w-[200px]">
                <div className="font-medium text-gray-900">{client.name}</div>
                <div className="text-xs text-gray-500">
                  {client.client_type_display}
                  {client.gstin ? ` · GSTIN ${client.gstin}` : ""}
                  {client.email ? ` · ${client.email}` : ""} · {client.case_count} case
                  {client.case_count === 1 ? "" : "s"}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  viewStatement.mutate(client.id, {
                    onError: (e) => showToast.error("Could not open the statement", apiErrorDetail(e, "Please try again.")),
                  })
                }
              >
                <FileDown className="h-4 w-4" />
                Statement
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setEditing(client)} aria-label={`Edit ${client.name}`}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => handleDelete(client)} aria-label={`Delete ${client.name}`}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ClientForm({ client, onDone }: { client: Client | null; onDone: () => void }) {
  const [form, setForm] = useState<ClientInput>(
    client
      ? {
          name: client.name,
          client_type: client.client_type,
          gstin: client.gstin,
          email: client.email,
          phone: client.phone,
          address: client.address,
          notes: client.notes,
        }
      : EMPTY,
  );
  const create = useCreateClient();
  const update = useUpdateClient();
  const busy = create.isPending || update.isPending;

  function set<K extends keyof ClientInput>(key: K, value: ClientInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const data = { ...form, gstin: form.client_type === "business" ? form.gstin : "" };
    try {
      if (client) {
        await update.mutateAsync({ id: client.id, data });
        showToast.success("Client saved");
      } else {
        await create.mutateAsync(data);
        showToast.success("Client added");
      }
      onDone();
    } catch (err) {
      showToast.error("Could not save the client", apiErrorDetail(err, "Please check the details."));
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{client ? `Edit ${client.name}` : "New client"}</CardTitle>
        <button type="button" onClick={onDone} aria-label="Close" className="p-1 text-gray-400 hover:text-gray-600">
          <X className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3" noValidate>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="client-name" className="block text-sm font-medium text-gray-700 mb-1">
                Name <span className="text-status-alert">*</span>
              </label>
              <Input id="client-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
            </div>
            <div>
              <label htmlFor="client-type" className="block text-sm font-medium text-gray-700 mb-1">
                Type
              </label>
              <Select
                id="client-type"
                value={form.client_type}
                onChange={(e) => set("client_type", e.target.value as ClientType)}
              >
                <option value="individual">Individual</option>
                <option value="business">Business entity</option>
              </Select>
            </div>
          </div>
          {form.client_type === "business" && (
            <div>
              <label htmlFor="client-gstin" className="block text-sm font-medium text-gray-700 mb-1">
                GSTIN (optional)
              </label>
              <Input
                id="client-gstin"
                value={form.gstin}
                maxLength={15}
                onChange={(e) => set("gstin", e.target.value.toUpperCase())}
                placeholder="e.g. 36ABCDE1234F1Z5"
              />
              <p className="mt-1 text-xs text-gray-500">
                Printed on invoices with &ldquo;Tax payable on reverse charge basis by recipient&rdquo;.
                No GST is calculated.
              </p>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="client-email" className="block text-sm font-medium text-gray-700 mb-1">
                Billing email
              </label>
              <Input id="client-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
            </div>
            <div>
              <label htmlFor="client-phone" className="block text-sm font-medium text-gray-700 mb-1">
                Phone
              </label>
              <Input id="client-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
            </div>
          </div>
          <div>
            <label htmlFor="client-address" className="block text-sm font-medium text-gray-700 mb-1">
              Address
            </label>
            <Textarea id="client-address" rows={3} value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !form.name.trim()}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {client ? "Save" : "Add client"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
