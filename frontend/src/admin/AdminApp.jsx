import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, Route, Routes } from "react-router";
import { loadSession, selectAuth } from "@/store/slices/authSlice";
import { AdminIndex } from "./components/AdminIndex";
import { AdminLayout } from "./components/AdminLayout";
import { RequireAuth, RequirePermission } from "./components/Guards";
import { NotificationProvider } from "./components/Notifications";
import { AccountPage } from "./pages/AccountPage";
import { ActivatePage } from "./pages/ActivatePage";
import { ArticleEditorPage } from "./pages/ArticleEditorPage";
import { ArticlesPage } from "./pages/ArticlesPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { NavigationPage } from "./pages/NavigationPage";
import { PageEditorPage } from "./pages/PageEditorPage";
import { PagesPage } from "./pages/PagesPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { RoleEditorPage } from "./pages/RoleEditorPage";
import { RolesPage } from "./pages/RolesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaxonomyPage } from "./pages/TaxonomyPage";
import { UsersPage } from "./pages/UsersPage";
import { ARTICLE_ACCESS, ROLE_READ, SETTINGS_ACCESS, TAXONOMY_READ } from "./permissions";

/** `rule` is one permission key or a list of alternatives (any one suffices). */
const guarded = (rule, element) =>
  Array.isArray(rule) ? (
    <RequirePermission anyOf={rule}>{element}</RequirePermission>
  ) : (
    <RequirePermission permission={rule}>{element}</RequirePermission>
  );

/** Admin area (/admin/*). Hiding UI is a convenience; Flask authorises every request. */
export default function AdminApp() {
  const dispatch = useDispatch();
  const { status } = useSelector(selectAuth);

  useEffect(() => {
    if (status === "idle") dispatch(loadSession());
  }, [status, dispatch]);

  return (
    <NotificationProvider>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="activate" element={<ActivatePage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route
          element={
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          }
        >
          <Route index element={<AdminIndex />} />
          <Route path="articles" element={guarded(ARTICLE_ACCESS, <ArticlesPage />)} />
          <Route path="articles/new" element={guarded("articles.create", <ArticleEditorPage />)} />
          <Route
            path="articles/:id/edit"
            element={guarded(ARTICLE_ACCESS, <ArticleEditorPage />)}
          />
          <Route path="topics" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="topics" />)} />
          <Route path="tags" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="tags" />)} />
          <Route path="authors" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="authors" />)} />
          <Route path="pages" element={guarded("pages.view", <PagesPage />)} />
          <Route path="pages/:id" element={guarded("pages.view", <PageEditorPage />)} />
          <Route path="navigation" element={guarded("navigation.manage", <NavigationPage />)} />
          <Route path="settings" element={guarded(SETTINGS_ACCESS, <SettingsPage />)} />
          <Route path="users" element={guarded("users.view", <UsersPage />)} />
          <Route path="roles" element={guarded(ROLE_READ, <RolesPage />)} />
          <Route path="roles/new" element={guarded("roles.manage", <RoleEditorPage />)} />
          <Route path="roles/:id" element={guarded(ROLE_READ, <RoleEditorPage />)} />
          <Route path="audit-log" element={guarded("audit.view", <AuditLogPage />)} />
          <Route path="account" element={<AccountPage />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Route>
      </Routes>
    </NotificationProvider>
  );
}
