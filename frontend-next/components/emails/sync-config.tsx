import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RefreshCw } from "lucide-react";
import type { SyncConfig } from "@/types";

interface SyncConfigCardProps {
  onSync: (config: SyncConfig) => void;
  isSyncing?: boolean;
}

export function SyncConfigCard({ onSync, isSyncing }: SyncConfigCardProps) {
  const [config, setConfig] = useState<SyncConfig>({
    start_date: "",
    end_date: "",
    keywords: "",
    labels: "",
  });

  const handleSync = () => {
    onSync(config);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sync Configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          {/* Date Range */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Start Date
            </label>
            <Input
              type="date"
              value={config.start_date}
              onChange={(e) =>
                setConfig({ ...config, start_date: e.target.value })
              }
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              End Date
            </label>
            <Input
              type="date"
              value={config.end_date}
              onChange={(e) =>
                setConfig({ ...config, end_date: e.target.value })
              }
            />
          </div>
        </div>

        {/* Keywords */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Keywords (comma-separated)
          </label>
          <Input
            placeholder="e.g., lawsuit, settlement, deposition"
            value={config.keywords}
            onChange={(e) => setConfig({ ...config, keywords: e.target.value })}
          />
        </div>

        {/* Labels */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Labels (comma-separated)
          </label>
          <Input
            placeholder="e.g., Legal, Clients, Important"
            value={config.labels}
            onChange={(e) => setConfig({ ...config, labels: e.target.value })}
          />
        </div>

        {/* Sync Button */}
        <Button
          variant="primary"
          className="w-full"
          onClick={handleSync}
          disabled={isSyncing}
        >
          <RefreshCw className={`h-4 w-4 ${isSyncing ? "animate-spin" : ""}`} />
          {isSyncing ? "Syncing..." : "Sync Emails"}
        </Button>
      </CardContent>
    </Card>
  );
}
