"use client";

import { useState } from "react";
import { GmailStatusCard } from "@/components/emails/gmail-status";
import { SyncConfigCard } from "@/components/emails/sync-config";
import { EmailsTable } from "@/components/emails/emails-table";
import { useGmailStatus, useSyncEmails } from "@/hooks/use-gmail";
import { useEmails, useLinkEmail } from "@/hooks/use-emails";
import type { SyncConfig } from "@/types";

export default function EmailsPage() {
  const { data: gmailStatus, isLoading: statusLoading } = useGmailStatus();
  const { data: emails = [], isLoading: emailsLoading } = useEmails();
  const syncEmails = useSyncEmails();
  const linkEmail = useLinkEmail();

  const handleSync = async (config: SyncConfig) => {
    try {
      await syncEmails.mutateAsync(config);
      // Success feedback would go here
    } catch (error) {
      console.error("Failed to sync emails:", error);
    }
  };

  const handleLinkEmail = async (emailId: number, caseId: number) => {
    try {
      await linkEmail.mutateAsync({ emailId, caseId });
      // Success feedback would go here
    } catch (error) {
      console.error("Failed to link email:", error);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Email Integration</h1>
        <p className="text-gray-600 mt-1">
          Sync and manage emails from your Gmail account
        </p>
      </div>

      {/* Top Section: Gmail Status + Sync Config */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <GmailStatusCard
          status={
            gmailStatus || {
              is_connected: false,
              email_address: "",
              total_emails_synced: 0,
              last_sync_time: null,
            }
          }
          isLoading={statusLoading}
        />
        <SyncConfigCard onSync={handleSync} isSyncing={syncEmails.isPending} />
      </div>

      {/* Emails Table */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Recent Emails
        </h2>
        <EmailsTable
          emails={emails}
          isLoading={emailsLoading}
          onLinkEmail={handleLinkEmail}
        />
      </div>

      {/* Results Count */}
      {!emailsLoading && emails.length > 0 && (
        <div className="text-center text-sm text-gray-500">
          Showing {emails.length} {emails.length === 1 ? "email" : "emails"}
        </div>
      )}
    </div>
  );
}
