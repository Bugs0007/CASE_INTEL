import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { ErrorBoundary } from "@/components/error-boundary";
import { AuthGuard } from "@/components/auth-guard";
import { DialogProvider } from "@/providers/dialog-provider";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <DialogProvider>
        <div className="flex h-screen bg-gray-50">
          {/* Sidebar */}
          <Sidebar />

          {/* Main Content */}
          <div className="flex-1 flex flex-col ml-64">
            <Header />
            <main className="flex-1 overflow-y-auto">
              <ErrorBoundary>{children}</ErrorBoundary>
            </main>
          </div>
        </div>
      </DialogProvider>
    </AuthGuard>
  );
}
