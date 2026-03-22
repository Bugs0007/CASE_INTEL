import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Search, UserPlus, MessageSquare } from "lucide-react";

export function QuickActions() {
  const actions = [
    {
      title: "Create New Brief",
      description: "Start a new legal brief",
      icon: FileText,
      color: "bg-blue-500 hover:bg-blue-600",
    },
    {
      title: "Research Case Law",
      description: "Search legal precedents",
      icon: Search,
      color: "bg-green-500 hover:bg-green-600",
    },
    {
      title: "Add New Client",
      description: "Register a new client",
      icon: UserPlus,
      color: "bg-purple-500 hover:bg-purple-600",
    },
    {
      title: "Ask AI Assistant",
      description: "Get AI-powered insights",
      icon: MessageSquare,
      color: "bg-orange-500 hover:bg-orange-600",
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <Button
                key={action.title}
                variant="ghost"
                className="h-auto p-4 flex-col items-start gap-2 text-left hover:bg-gray-50"
                onClick={() => {
                  // TODO: Implement action handlers
                }}
              >
                <div className={`p-2 rounded-lg text-white ${action.color}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-medium text-gray-900">
                    {action.title}
                  </div>
                  <div className="text-xs text-gray-500">
                    {action.description}
                  </div>
                </div>
              </Button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
