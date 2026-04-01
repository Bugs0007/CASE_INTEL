# CASE INTEL Frontend - Complete Implementation Plan

## Plan: Complete CASE INTEL Frontend Implementation

Polish and finalize the existing CASE INTEL application by implementing missing UI components, connecting real API endpoints, and addressing critical gaps. The core screens are built; focus is on missing dependencies, API integration, and production readiness.

---

## Steps

### Phase 1: Critical Missing Components

1. **Create Textarea component** in `components/ui/textarea.tsx` - required by chat-panel.tsx, implement with forwardRef, className merging, and proper sizing
2. **Build Create Case Dialog** in `components/cases/create-case-dialog.tsx` - modal form with case_number, title, client_name, opposing_party, case_type, priority, filing_date fields; wire to Quick Actions and "New Case" button
3. **Build Document Upload Dialog** in `components/documents/upload-document-dialog.tsx` - file picker with drag-drop, case selector, document type dropdown, file size validation; connect to "Upload Document" button

### Phase 2: API Integration (_depends on Phase 1_)

4. **Replace chat simulation** in `lib/api/chat.ts` - connect to real backend endpoint, handle streaming responses if supported, implement proper error handling with retry logic
5. **Complete email sync API** in `lib/api/gmail.ts` - wire sync button to actual backend, add progress tracking, handle OAuth flow for Gmail connection if needed (_parallel with step 4_)
6. **Implement document processing API** in `lib/api/documents.ts` - connect Process button to backend, add real-time status updates, handle failed processing states (_parallel with steps 4-5_)

### Phase 3: User Feedback & Polish (_depends on Phase 2_)

7. **Add toast notification system** - install sonner or react-hot-toast, create `components/ui/toast.tsx`, integrate success/error feedback for all mutations (case creation, document upload, email sync, chat errors)
8. **Implement loading states** - add skeleton screens for all data fetches (currently partial), ensure consistent loading UX across all pages (_parallel with step 7_)
9. **Add error boundaries** - create `components/error-boundary.tsx`, wrap page layouts, display user-friendly error messages with retry options (_parallel with steps 7-8_)

### Phase 4: Authentication & Security (_depends on Phase 3_)

10. **Implement authentication system** - choose auth provider (NextAuth.js, Clerk, or custom), protect all dashboard routes, add login/logout pages, replace mock "Advocate" user in sidebar with real user data
11. **Add role-based access control** - define user roles (lawyer, paralegal, admin), restrict document deletion/case creation based on roles, update UI to hide unauthorized actions
12. **Secure API endpoints** - add authentication headers to all API calls in `lib/api/client.ts`, handle 401 responses with redirect to login

### Phase 5: Production Readiness (_depends on Phase 4_)

13. **Environment configuration** - document required .env.local variables (API_BASE_URL, GMAIL_CLIENT_ID, AUTH_SECRET), create .env.example template
14. **Error handling audit** - ensure all React Query hooks have onError callbacks, add fallback UI for network failures, implement retry logic for transient errors
15. **Accessibility audit** - add ARIA labels to interactive elements, ensure keyboard navigation works, test with screen reader, add focus indicators
16. **Performance optimization** - implement React.lazy for heavy components (chat panel, document table), add image optimization, enable Next.js production mode testing

---

## Relevant Files

- `components/ui/textarea.tsx` — create new component (currently missing, needed by chat-panel.tsx)
- `components/cases/create-case-dialog.tsx` — new dialog for case creation
- `components/documents/upload-document-dialog.tsx` — new dialog for document uploads
- `lib/api/chat.ts` — replace 2-second simulation with real API integration
- `lib/api/gmail.ts` — complete sync endpoint implementation
- `lib/api/documents.ts` — add document processing API calls
- `lib/api/client.ts` — add authentication headers and error interceptors
- `components/chat/chat-panel.tsx` — uses Textarea component
- `app/(dashboard)/page.tsx` — connect Quick Actions to dialogs
- `app/(dashboard)/cases/page.tsx` — connect "New Case" button to dialog
- `app/(dashboard)/documents/page.tsx` — connect "Upload Document" button to dialog
- `components/layout/sidebar.tsx` — replace mock user with authenticated user data
- `.env.example` — document all required environment variables

---

## Verification

1. **Run development server** with `npm run dev` - confirm no TypeScript errors, no missing module errors for Textarea
2. **Test Create Case flow** - fill form with all required fields, submit, verify case appears in /cases list
3. **Test Document Upload** - select file, choose case, submit, verify document appears in /documents table with pending status
4. **Test Chat with real API** - send message in case detail page, verify real backend response (not 2-second simulation), check citation rendering
5. **Test Email Sync** - click sync button, verify loading state, check synced emails appear in table
6. **Test authentication flow** - logout, verify redirect to login, login with valid credentials, verify access to dashboard
7. **Accessibility check** - tab through all interactive elements, verify focus indicators, test with NVDA/VoiceOver
8. **Production build test** - run `npm run build` and `npm start`, verify no errors, test all core flows

---

## Decisions

- **Build on existing implementation** (70-80% complete) - all screens are functional, modular architecture is solid
- **Focus on filling gaps** rather than refactoring - component structure is production-ready
- **Prioritize missing UI components first** (Phase 1) before API work to unblock development
- **Authentication is critical** for production (Phase 4) but can be developed in parallel after core features work
- **Scope includes**: missing components, API integration, auth, production polish
- **Scope excludes**: analytics/reporting, calendar view, notification center (nice-to-have features)

---

## Total: 16 implementation tasks across 5 phases
