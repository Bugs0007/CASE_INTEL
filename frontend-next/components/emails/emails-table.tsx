import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Mail, Link as LinkIcon, Sparkles } from "lucide-react";
import { formatDateTime } from "@/lib/utils";
import type { Email } from "@/types";

interface EmailsTableProps {
  emails: Email[];
  isLoading?: boolean;
  onLinkEmail: (emailId: number, caseId: number) => void;
}

export function EmailsTable({ emails, isLoading, onLinkEmail }: EmailsTableProps) {
  const [linkingEmailId, setLinkingEmailId] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="p-12 text-center text-gray-500">
          Loading emails...
        </div>
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="p-12 text-center">
          <div className="text-6xl mb-4">📧</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            No emails found
          </h3>
          <p className="text-gray-500">
            Sync your Gmail account to see emails here.
          </p>
        </div>
      </div>
    );
  }

  const getStatusBadge = (email: Email) => {
    if (email.linked_case) {
      return (
        <div className="flex items-center gap-1 text-xs px-2 py-1 bg-green-100 text-green-800 rounded-md font-medium">
          <LinkIcon className="h-3 w-3" />
          Linked
        </div>
      );
    }

    if (email.suggested_case_id) {
      return (
        <div className="flex items-center gap-1 text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded-md font-medium">
          <Sparkles className="h-3 w-3" />
          Suggestion
        </div>
      );
    }

    return (
      <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-md font-medium">
        Unlinked
      </span>
    );
  };

  const handleLink = (emailId: number) => {
    // For now, just show a simple prompt
    // In a real app, this would open a dialog to select a case
    const caseId = prompt("Enter case ID to link:");
    if (caseId) {
      onLinkEmail(emailId, Number(caseId));
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Subject
              </th>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                From
              </th>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Date
              </th>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Case
              </th>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="py-3 px-6 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {emails.map((email) => (
              <tr
                key={email.id}
                className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
              >
                {/* Subject */}
                <td className="py-4 px-6">
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-gray-400 flex-shrink-0" />
                    <div className="font-medium text-gray-900 truncate max-w-md">
                      {email.subject}
                    </div>
                  </div>
                </td>

                {/* From */}
                <td className="py-4 px-6">
                  <div className="text-sm text-gray-700">
                    {email.sender_name || email.sender_email}
                  </div>
                  <div className="text-xs text-gray-500">
                    {email.sender_email}
                  </div>
                </td>

                {/* Date */}
                <td className="py-4 px-6 text-sm text-gray-600">
                  {formatDateTime(email.received_date, "MMM d, yyyy")}
                </td>

                {/* Case */}
                <td className="py-4 px-6">
                  {email.linked_case ? (
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {email.linked_case.case_number}
                      </div>
                      <div className="text-xs text-gray-500 truncate max-w-xs">
                        {email.linked_case.title}
                      </div>
                    </div>
                  ) : email.suggested_case_id ? (
                    <div className="text-sm text-blue-600">
                      Suggested: Case #{email.suggested_case_id}
                    </div>
                  ) : (
                    <span className="text-sm text-gray-400">None</span>
                  )}
                </td>

                {/* Status */}
                <td className="py-4 px-6">{getStatusBadge(email)}</td>

                {/* Actions */}
                <td className="py-4 px-6">
                  {!email.linked_case && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleLink(email.id)}
                    >
                      <LinkIcon className="h-4 w-4" />
                      Link to Case
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
