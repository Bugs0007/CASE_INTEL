"use client";

import { useState } from "react";
import { StatCards } from "@/components/dashboard/stat-cards";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { ActiveCases } from "@/components/dashboard/active-cases";
import { QuickActions } from "@/components/dashboard/quick-actions";
import { CreateCaseDialog } from "@/components/cases/create-case-dialog";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { useDashboard } from "@/hooks/use-dashboard";

export default function DashboardPage() {
  const { data: dashboardData, isLoading, error } = useDashboard();
  const [isCreateCaseOpen, setIsCreateCaseOpen] = useState(false);
  const [isUploadDocOpen, setIsUploadDocOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/3 mb-6"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 bg-gray-200 rounded-xl"></div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-96 bg-gray-200 rounded-xl"></div>
            <div className="h-96 bg-gray-200 rounded-xl"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="text-center py-12">
          <div className="text-red-500 text-lg font-medium mb-2">
            Failed to load dashboard
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  const currentHour = new Date().getHours();
  const greeting =
    currentHour < 12
      ? "Good Morning"
      : currentHour < 17
        ? "Good Afternoon"
        : "Good Evening";

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Welcome Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {greeting}, Advocate! 👋
        </h1>
        <p className="text-gray-600">
          Here's what's happening with your cases today.
        </p>
      </div>

      {/* Stats Cards */}
      {dashboardData && <StatCards stats={dashboardData.stats} />}

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <RecentActivity activities={dashboardData?.recent_activity || []} />
        <ActiveCases cases={dashboardData?.active_cases_summary || []} />
      </div>

      {/* Quick Actions */}
      <QuickActions
        onCreateCase={() => setIsCreateCaseOpen(true)}
        onUploadDocument={() => setIsUploadDocOpen(true)}
      />

      {/* Dialogs */}
      <CreateCaseDialog
        isOpen={isCreateCaseOpen}
        onClose={() => setIsCreateCaseOpen(false)}
      />
      <UploadDocumentDialog
        isOpen={isUploadDocOpen}
        onClose={() => setIsUploadDocOpen(false)}
      />
    </div>
  );
}
