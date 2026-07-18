import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Collapsible } from "@/components/ui/collapsible";
import { formatRelativeTime, staggerDelay } from "@/lib/utils";
import type { RecentActivity as RecentActivityType } from "@/types";

interface RecentActivityProps {
  activities: RecentActivityType[];
}

export function RecentActivity({ activities }: RecentActivityProps) {
  const [sectionOpen, setSectionOpen] = useState(false);

  const getActivityIcon = (type: string | null) => {
    switch (type) {
      case "document_uploaded":
        return "📎";
      case "case_created":
        return "⚖️";
      case "hearing_scheduled":
        return "📅";
      case "conversation_started":
        return "💬";
      case "email_synced":
        return "📧";
      default:
        return "📝";
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Recent Activity</CardTitle>
        <CollapseToggle isOpen={sectionOpen} onToggle={() => setSectionOpen((v) => !v)} />
      </CardHeader>
      <Collapsible isOpen={sectionOpen}>
        <CardContent>
          {activities.length === 0 ? (
            <p className="text-gray-500 text-sm py-4">No recent activity</p>
          ) : (
            <div className="space-y-4">
              {activities.map((activity, i) => (
                <div
                  key={activity.id}
                  style={staggerDelay(i)}
                  className="flex items-start gap-4 animate-fade-up motion-reduce:animate-none"
                >
                  <div className="flex-shrink-0 w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center text-sm">
                    {getActivityIcon(activity.activity_type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 mb-1">
                      {activity.description || activity.activity_type}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span>{formatRelativeTime(activity.created_at)}</span>
                      {activity.case_id && (
                        <>
                          <span>•</span>
                          <Link
                            href={`/cases/${activity.case_id}`}
                            className="text-primary hover:text-primary-hover font-medium"
                          >
                            View Case
                          </Link>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Collapsible>
    </Card>
  );
}
