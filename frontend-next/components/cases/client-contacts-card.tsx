"use client";

import { Pencil, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ExpandableCard } from "@/components/ui/expandable-card";
import { matchesQuery, previewContacts, sortContacts } from "@/lib/case-previews";
import type { ClientContact } from "@/types";

interface ClientContactsCardProps {
  contacts: ClientContact[];
  /** Contacts are added and edited in Edit Details. */
  onEditDetails: () => void;
}

/** The people on this case: the primary contact and the billing contact
 * first, the rest in the expanded view. */
export function ClientContactsCard({ contacts, onEditDetails }: ClientContactsCardProps) {
  const previewed = previewContacts(contacts);

  return (
    <ExpandableCard
      title="Client contacts"
      icon={<Users className="h-4 w-4" />}
      count={contacts.length}
      actions={
        <Button variant="secondary" size="sm" onClick={onEditDetails}>
          <Pencil className="h-3.5 w-3.5" />
          {contacts.length === 0 ? "Add" : "Edit"}
        </Button>
      }
      viewAll={{ total: contacts.length, shown: previewed.length }}
      expandable={contacts.length > previewed.length}
    >
      {({ expanded, query }) => {
        if (contacts.length === 0) {
          return <p className="text-sm text-gray-500">No contacts on this case yet.</p>;
        }
        const visible = expanded
          ? sortContacts(contacts).filter((c) => matchesQuery(query, c.name, c.email, c.phone, c.role))
          : previewed;
        if (visible.length === 0) {
          return <p className="text-sm text-gray-500">No contacts match.</p>;
        }
        return (
          <ul className="space-y-2.5">
            {visible.map((contact) => (
              <li key={contact.id} className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">{contact.name}</span>
                  <span className="text-xs capitalize text-gray-400">{contact.role}</span>
                  {contact.is_billing_contact && (
                    <span className="ci-chip ci-chip--none">Billing</span>
                  )}
                </div>
                {(contact.email || contact.phone) && (
                  <div className="truncate text-xs text-gray-500">
                    {[contact.email, contact.phone].filter(Boolean).join(" · ")}
                  </div>
                )}
              </li>
            ))}
          </ul>
        );
      }}
    </ExpandableCard>
  );
}
