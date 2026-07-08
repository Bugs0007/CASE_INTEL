import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { CheckCircle, XCircle, RefreshCw } from "lucide-react";
import type { GmailStatus } from "@/types";
import { formatDateTime } from "@/lib/utils";

interface GmailStatusCardProps {
  status: GmailStatus;
  isLoading?: boolean;
}

export function GmailStatusCard({ status, isLoading }: GmailStatusCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Gmail Connection</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-gray-500">
            Loading status...
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Gmail Connection</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Connection Status */}
          <div className="flex items-center gap-3">
            {status.is_connected ? (
              <>
                <div className="flex items-center justify-center w-10 h-10 bg-green-100 rounded-full">
                  <CheckCircle className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <div className="font-medium text-gray-900">Connected</div>
                  <div className="text-sm text-gray-500">
                    {status.email_address}
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-center w-10 h-10 bg-red-100 rounded-full">
                  <XCircle className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <div className="font-medium text-gray-900">Disconnected</div>
                  <div className="text-sm text-gray-500">
                    Connect your Gmail account to sync emails
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Stats */}
          {status.is_connected && (
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
              <div>
                <div className="text-sm text-gray-500">Total Synced</div>
                <div className="text-2xl font-bold text-gray-900">
                  {status.total_emails_synced}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Last Sync</div>
                <div className="text-sm font-medium text-gray-900">
                  {status.last_sync_time
                    ? formatDateTime(status.last_sync_time, "MMM d, h:mm a")
                    : "Never"}
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
