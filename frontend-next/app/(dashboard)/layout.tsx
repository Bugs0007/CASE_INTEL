import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { MobileNav } from "@/components/layout/mobile-nav";
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
        <div className="flex h-screen bg-page">
          {/* Sidebar -- desktop only; MobileNav below replaces it on phones/tablets */}
          <Sidebar />

          {/* Main Content -- min-w-0 on both levels below is load-bearing:
              without it, a horizontally-scrollable descendant deep inside a
              page (e.g. the Cases status-tab pills) still reports its
              un-shrunk content width upward through this flex-column chain,
              stretching the whole app shell wider than the viewport instead
              of staying contained to its own overflow-x-auto scrollbar. */}
          <div className="flex-1 flex flex-col lg:ml-60 min-w-0">
            <Header />
            <main className="flex-1 min-h-0 min-w-0 overflow-y-auto pb-16 lg:pb-0">
              <ErrorBoundary>{children}</ErrorBoundary>
            </main>
          </div>

          <MobileNav />
        </div>
      </DialogProvider>
    </AuthGuard>
  );
}
