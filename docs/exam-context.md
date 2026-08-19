# Exam Feature — Project Context

> Reference for any task touching the **paper exam** feature (the `Exams` page,
> `ExamView`, exam backend). Read this before exploring. Last updated 2026-07-25.
>
> **Scope:** *paper* exams (`examify` frontend + `examify-backend`). *Online*
> exams (`onlineExam*`, `OnlineExam*`) are a parallel subsystem — same patterns,
> separate files/services — and are not detailed here.

---

## 1. What an "exam" is

A **paper exam** is a generated, printable test: a title, sections, each section
holding paper questions (`PaperQuestion`), plus rendered HTML pages and a PDF.
It is created from an **exam template** (`ExamTemplate` → `SectionTemplate`s with
constraints) either by the constraint-satisfaction generator or by manual
section-building in the exam builder.

Lifecycle states (the `status` field): `"draft"` → `"generated"`.

Approval is **orthogonal** to lifecycle: a boolean `approved` flag toggled by an
academic user. It does not (currently) lock the exam or gate downloads — it is a
simple on/off indicator.

---

## 2. Data model

### Backend — `examify-backend/src/models/server/exam.ts`

```ts
type ExamStatus = "draft" | "generated";

interface Exam {
  id: string;
  title: string;
  description?: string;
  subjectId: string;
  organisationId: string;
  tags?: string[];
  sections: Section[];              // light metadata only (see Storage split)
  pdfLink?: string;                 // private Storage path to the PDF
  examTemplateId?: string;
  initialPageOffset?: number;
  finalPageOffset?: number;
  initialQuestionNumberOffset?: number;
  createdAt: Timestamp;
  createdBy: string;
  public?: boolean;
  projectId?: string;
  status?: ExamStatus;
  approved?: boolean;               // ← added 2026-07-25
}
```

- `ExamDatabaseModel` = `Exam` minus a few layout-only keys; this is the shape
  written to/read from Firestore and the type `updateExamMetadata` accepts.
- `ExamClient` (`models/client/examClient.ts`) is the projection sent to the FE
  by controllers — a slim version of the exam (no heavy HTML/solutions).

### Frontend — `examify/src/types/Exam.ts`

Mirrors the backend `Exam`. Note the FE `Exam` uses Firestore `Timestamp` for
`createdAt` and arrives serialized as `{ _seconds, _nanoseconds }` over the wire
— hooks rehydrate it (see `useExam` / `useExams` normalization).

Related types in the same file: `ExamTemplate`, `SectionTemplate`, `Section`,
`Constraint`, `PageMap`, `QuestionPage`. Question content uses `PaperQuestion`
from `types/Question.ts`.

---

## 3. Storage architecture (important, non-obvious)

The **full exam** (sections + question HTML, cover/final pages, solutions) lives
in **Firebase Storage**, NOT Firestore. Firestore holds only **metadata**
(`ExamDatabaseModel`). This split exists because the full object is large.

Consequences:
- `getExamById` (`examController`) reads Firestore metadata **and** downloads the
  Storage object to project a slim `sections` view (graceful: still returns
  metadata if Storage is unavailable).
- `getDraftForEdit` / `downloadExamFromStorage` return the full Storage object
  for the builder to resume.
- `updateExamMetadata(id, fields)` writes **Firestore only** + sets `updatedAt`.
  `updateExamInStorage(exam)` writes the **Storage object**.

Service layer (`examify-backend/src/services/examService.ts`) — key functions:

| Function | Purpose |
|---|---|
| `getExamById(id)` | Firestore metadata |
| `getExamsBySubjectId` / `getExamsByProjectId` | list |
| `createExam` / `createExamDraft` | write |
| `updateExamMetadata(id, fields)` | **Firestore** partial update (used by approve) |
| `updateExamInStorage(exam)` | **Storage** full-object update |
| `downloadExamFromStorage(id)` / `getDraftForEdit(id)` | read full object |
| `addPdfLink(id, link)` / `getExamPdfUrl(path)` | PDF link mgmt |
| `deleteExamById(id)` | delete |

---

## 4. Backend endpoints — `examify-backend/src/routes/examRoutes.ts`

All under `/api/exams`, all `authenticateJWT` + `authorizeRole(...)`.

| Method | Path | Controller | Role gate | Notes |
|---|---|---|---|---|
| GET | `/id/:id` | `getExamById` | student/teacher/org_admin | metadata + slim sections |
| GET | `/answer-sheet/:id` | `getAnswerSheet` | student/teacher/org_admin | auto-print HTML |
| GET | `/subjectId/:subjectId` | `getExamsBySubjectId` | … | list |
| GET | `/project/:projectId` | `getExamsByProjectId` | … | list |
| GET | `/pdf/:id` | `getExamPDF` | … | returns `{ pdfUrl }` |
| GET | `/preview/:id` | `getExamPreview` | … | JSON array of per-page HTML |
| GET | `/insights/:id` | `getExamInsights` | … | computed `ExamInsights` (readiness/coverage/difficulty/budget) |
| POST | `/draft` | `createExamDraft` | … | create draft (Storage+Firestore) |
| GET | `/draft/:id` | `getExamDraft` | … | resume draft |
| PUT | `/:id` | `updateExamDraft` | … | autosave |
| POST | `/finalize/:id` | `finalizeExamDraft` | … | draft→generated (pure status swap; no PDF/doc-service) (added 2026-07-26) |
| POST | `/generate` | `generateExam` | … | CSP generation |
| ~~POST~~ | ~~`/create`~~ | ~~`createExam`~~ | … | **DEPRECATED 2026-07-26** — route commented out; use `/draft` + `/finalize/:id` |
| ~~POST~~ | ~~`/confirm/:id`~~ | ~~`confirmExamGeneration`~~ | … | **DEPRECATED 2026-07-26** — similarity-confirm flow retired; route commented out |
| **PATCH** | **`/approve/:id`** | **`approveExam`** | **teacher/org_admin** | **toggle `approved` (added 2026-07-25)** |
| DELETE | `/id/:id` | `deleteExamById` | … | delete |
| PATCH | `/pdf-link/:id` | `addPDFLink` | system_admin | doc-service callback |
| GET | `/exam-generate/:id` | `getExamByIdForDocuservice` | system_admin | doc-service read |

> `authorizeRole` auto-admits `system_admin` regardless of the list
> (`middleware/auth.ts`). So `["teacher","organisation_admin"]` == FE
> `isAcademic` (teacher + org_admin + sys_admin) and correctly excludes
> `tech_support`.

### Adding an endpoint (strict layered architecture)

`Routes → Controllers → Services`, with `Validators` + `Permissions` on the side.
**Controllers hold ALL logic; services are Firestore/SQL only.** Order:
1. Model (`models/server/`) if new fields
2. Validator (`validators/`, Joi) for POST/PUT/PATCH
3. Permission (`permissions/`) for state changes
4. Service (DB op only) — often one already exists
5. Controller (validate → fetch → permission check → service → response)
6. Route (`routes/`) — import auto-picked up via `routes/index.ts`
7. Bump `package.json` version (minor for new feature)

There's a project skill for this: `add-endpoint` (`examify-backend/.claude/skills`).

---

## 5. Permissions — `examify-backend/src/permissions/examPermissions.ts`

- `canSeeExams(subject, req)` — subject access
- `canSeeSpecificExam(exam, req)` — subject access **and** (creator or public)
- `canDeleteExamById(exam, req)` — subject access; public → creator only
- `canCreateExam(subject, req)` — subject access
- `canEditExamDraft(exam, req)` — **draft only**, creator or sys-admin
- `canApproveExam(exam, req)` — subject access (`canAccessSubjectByIds`); route
  role-gate does the academic check

Helpers in `permissions/permissions.ts`: `canAccessSubjectByIds(subjectId,
organisationId, req)`, `isSameUser`, `isUserSysAdmin`, etc.

---

## 6. Frontend file map

**Pages** (`examify/src/app/routes/dashboard/`)
- `Exams.tsx` — list page. `useExams()`, renders `ExamCard`. Create → draft → edit.
- `ExamView.tsx` — detail page (`/:subjectId/exams/:examId`). Sidebar (facts,
  actions) + tabs (Preview / Insights / Activity / Discussion).
- `exam-view/` — `InsightsTab`, `ActivityTab`, `DiscussionTab`, `mockData`.

**Hooks** (`examify/src/hooks/`) — **plain `useState`/`useEffect`, NOT TanStack Query**
- `useExam(examId)` — GET `/exams/id/:id`; returns `{ exam, loading, error }`.
  Re-fetches only when `examId` changes → mutations must update local state.
- `useExams()` — GET `/exams/subjectId/:id`; returns `{ exams, loading, error,
  setExams, reload }`.
- `useExamTemplate`, `useExamTemplates`, `useUserProfile`, `useSubjects`.

> Contrast: questions use TanStack Query (`useQuestion`, `useQuestionMutations`).
> Exam hooks do **not** — so after an exam mutation, optimistically update local
> state (see ExamView approve) rather than relying on query invalidation.

**Services** (`examify/src/services/`)
- `examApprovals.ts` — `setExamApproval(examId, approved)` → PATCH `/exams/approve/:id`
- `examDrafts.ts` — `createExamDraft(...)`
- `axios.ts` — axios instance, base `VITE_BACKEND_URL/api`, JWT interceptors

**Components** (`examify/src/components/molecules/`)
- `ExamCard.tsx` — shared list card (also used by `ProjectExamList`). Shows a
  **Draft** badge (when `status === "draft"`) + **Approved** badge. The old
  Ready/Pending/Error chips (which tracked document-service PDF render state)
  were removed 2026-07-26 once server-side PDF generation was dropped; "View
  PDF" is now enabled only when `exam.pdfLink` exists.
- `ExamPreviewTab.tsx`, `ExamTemplateSelectDialog.tsx`, `A4Page`, `PDFRenderer`.

---

## 7. Key flows

**Create/edit (draft autosave):** `Exams.tsx` → `createExamDraft()` (POST
`/exams/draft`) → navigate to edit-exam. Builder autosaves via PUT `/:id`
(`updateExamDraft`). `/finalize/:id` flips draft→generated (a pure status swap;
no PDF/document-service); the old monolithic `/create` finalize (similarity
check + answer-template re-validation) is deprecated. See memory
`exam-draft-autosave` + `docs/plans/2026-07-24-exam-draft-autosave*.md`.

**Preview:** GET `/exams/preview/:id` → JSON array of per-page HTML (one doc/A4
page). Two-engine drift invariant vs document-service (see memory
`exam-html-preview-endpoint`).

**Insights:** GET `/exams/insights/:id` → computed `ExamInsights` payload
(readiness, tag coverage, difficulty, constraint budgets). The backend is now
the source of truth — `ExamView`'s `InsightsTab` fetches this instead of
recomputing client-side. The engine
(`services/external/examInsightService.ts`) is a faithful TS port of the FE
`features/exam-builder/insights/computeInsights.ts` (+ `evaluateConstraints`),
so the two are a **drift pair** — change one, mirror the other (same convention
as the HTML-preview engine). AI feedback (`AIFeedbackCard`) is still mock and
feeds on this same payload; student-performance insights are **deferred**
(paper exams have no attempt/result data). Controller mirrors `getExamPreview`
exactly (exam → subject → `canSeeSpecificExam` → `downloadExamFromStorage` →
compute → 200; 404 if no Storage object).

**Answer sheet:** GET `/exams/answer-sheet/:id` (auto-print HTML), or frontend
route `/answer-sheet/:id` (memory `view-answer-sheet-feature`).

**PDF:** GET `/exams/pdf/:id` → `{ pdfUrl }`. Generation is async via
document-service; `pdfLink` set via PATCH `/pdf-link/:id` (system_admin callback).

**Approve (canonical example, 2026-07-25):**
- FE: `ExamView` local `approved` synced from `exam.approved` via `useEffect`;
  toggle does optimistic update + `setExamApproval()`; spinner while pending;
  revert + toast on error. `ExamCard` shows Approved badge.
- BE: PATCH `/exams/approve/:id` `{ approved }` → `approveExam`: validate →
  `getExamById` → `canApproveExam` → `updateExamMetadata({ approved })` → 200.

---

## 8. Patterns to follow

- **Mirror the question-stage flow** for exam state toggles: backend
  `PATCH /questions/stage/:id` + `changeQuestionStage` (validate → fetch →
  `canAccessSubjectByIds` → update) is the template; the exam approve endpoint
  copies it 1:1.
- **Optimistic UI** because exam hooks aren't React Query: flip local state,
  call API, revert + toast on failure.
- **shadcn/ui + Tailwind tokens only** (never hardcode hex). Success states use
  `success` token: `border-success bg-success/10 text-success`.
- **Toasts** via `sonner` (`toast.success` / `toast.error`).

---

## 9. Conventions & gotchas

- **No test runner** — verify with lightweight commands (see below).
- **Frontend pre-commit runs the full build (~30–60s)** — use a **600s** timeout
  for `yarn build`.
- **Verify commands:**
  - Backend: `yarn --cwd examify-backend build` (runs `tsc`; no lint script)
  - Frontend: `yarn --cwd examify lint` then `yarn --cwd examify build`
    (`tsc -b && vite build`)
  - Note: `yarn lint` has ~59 *pre-existing* `no-explicit-any` errors in files
    unrelated to exams — check your own files are clean, don't try to fix the
    baseline.
- **Versioning:** bump backend `package.json` per feature (minor for new
  endpoint). FE has no version convention.
- **Brand:** customer-facing docs brand the product **"Papersetter"**; exclude
  `examify-tms` & `examify-nswselective` from customer docs.
- **cPanel/Passenger deploy** for backend (doc-root vs app-root, `.htaccess` in
  `public/`, Passenger startup must `export server` not `listen`) — see memory
  `examify-backend-cpanel-passenger-deploy`.

---

## 10. Known TODOs in `ExamView` (still mocked)

These action handlers in `ExamView.tsx` are **still mocks** (good next tasks):
- `handleRegenerate` — `// Mock: no regenerate endpoint yet.`
- `handleDelete` — `// Mock: no delete endpoint yet.` (the list page's delete is
  real via `DELETE /exams/id/:id`; ExamView's is not wired).

When wiring these, follow the **approve** pattern in §7.
