import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: number | string;
  icon: LucideIcon;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  gradient?: string;
}

export function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  gradient,
}: StatCardProps) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-6">
        <div
          className={cn(
            "rounded-xl p-4 flex items-start justify-between text-white",
            gradient || "bg-gradient-to-r from-blue-500 to-blue-600",
          )}
        >
          <div>
            <div className="text-2xl font-bold mb-1">{value}</div>
            <div className="text-sm opacity-90">{title}</div>
            {trend && (
              <div className="flex items-center gap-1 mt-2">
                <span className="text-xs">
                  {trend.isPositive ? "↗" : "↘"} {trend.value}%
                </span>
              </div>
            )}
          </div>
          <div className="opacity-80">
            <Icon className="h-8 w-8" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface StatCardsProps {
  stats: {
    active_cases: number;
    total_documents: number;
    email_threads: number;
    documents_by_status: Record<string, number>;
  };
}

export function StatCards({ stats }: StatCardsProps) {
  const pendingQuestions = 8; // Placeholder, calculate from conversations

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <StatCard
        title="Active Cases"
        value={stats.active_cases}
        icon={() => <span className="text-2xl">⚖️</span>}
        gradient="bg-gradient-to-r from-blue-500 to-blue-600"
        trend={{ value: 12, isPositive: true }}
      />
      <StatCard
        title="Documents"
        value={stats.total_documents}
        icon={() => <span className="text-2xl">📄</span>}
        gradient="bg-gradient-to-r from-green-500 to-green-600"
        trend={{ value: 8, isPositive: true }}
      />
      <StatCard
        title="Pending Questions"
        value={pendingQuestions}
        icon={() => <span className="text-2xl">❓</span>}
        gradient="bg-gradient-to-r from-purple-500 to-purple-600"
      />
      <StatCard
        title="Recent Emails"
        value={stats.email_threads}
        icon={() => <span className="text-2xl">📧</span>}
        gradient="bg-gradient-to-r from-orange-500 to-orange-600"
        trend={{ value: 5, isPositive: true }}
      />
    </div>
  );
}
