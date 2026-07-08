"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FileText,
  Search,
  UserPlus,
  MessageSquare,
  Upload,
  FolderPlus,
} from "lucide-react";
import { useRouter } from "next/navigation";

interface QuickActionsProps {
  onCreateCase?: () => void;
  onUploadDocument?: () => void;
}

export function QuickActions({
  onCreateCase,
  onUploadDocument,
}: QuickActionsProps) {
  const router = useRouter();

  const actions = [
    {
      title: "Create New Case",
      description: "Start a new legal case",
      icon: FolderPlus,
      color: "bg-blue-500 hover:bg-blue-600",
      onClick: onCreateCase || (() => router.push("/cases")),
    },
    {
      title: "Upload Document",
      description: "Add documents to a case",
      icon: Upload,
      color: "bg-green-500 hover:bg-green-600",
      onClick: onUploadDocument || (() => router.push("/documents")),
    },
    {
      title: "Research Case Law",
      description: "Search legal precedents",
      icon: Search,
      color: "bg-purple-500 hover:bg-purple-600",
      onClick: () => router.push("/cases"),
    },
    {
      title: "Ask AI Assistant",
      description: "Get AI-powered insights",
      icon: MessageSquare,
      color: "bg-orange-500 hover:bg-orange-600",
      onClick: () => router.push("/cases"),
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
                onClick={action.onClick}
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
