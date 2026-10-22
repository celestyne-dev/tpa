import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, Route, Routes } from "react-router";
import { loadSession, selectAuth } from "@/store/slices/authSlice";
import { AdminLayout } from "./components/AdminLayout";
import { RequireAuth, RequirePermission } from "./components/Guards";
import { NotificationProvider } from "./components/Notifications";
import { AccountPage } from "./pages/AccountPage";
import { ArticleEditorPage } from "./pages/ArticleEditorPage";
import { ArticlesPage } from "./pages/ArticlesPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NavigationPage } from "./pages/NavigationPage";
import { PageEditorPage } from "./pages/PageEditorPage";
import { PagesPage } from "./pages/PagesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaxonomyPage } from "./pages/TaxonomyPage";
import { UsersPage } from "./pages/UsersPage";

const guarded = (permission, element) => (
  <RequirePermission permission={permission}>{element}</RequirePermission>
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
        <Route
          element={
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          }
        >
          <Route index element={guarded("dashboard.view", <DashboardPage />)} />
          <Route path="articles" element={guarded("content.read", <ArticlesPage />)} />
          <Route path="articles/new" element={guarded("content.write", <ArticleEditorPage />)} />
          <Route
            path="articles/:id/edit"
            element={guarded("content.read", <ArticleEditorPage />)}
          />
          <Route path="topics" element={guarded("content.read", <TaxonomyPage kind="topics" />)} />
          <Route path="tags" element={guarded("content.read", <TaxonomyPage kind="tags" />)} />
          <Route
            path="authors"
            element={guarded("content.read", <TaxonomyPage kind="authors" />)}
          />
          <Route path="pages" element={guarded("pages.read", <PagesPage />)} />
          <Route path="pages/:id" element={guarded("pages.read", <PageEditorPage />)} />
          <Route path="navigation" element={guarded("navigation.manage", <NavigationPage />)} />
          <Route path="settings" element={guarded("settings.manage", <SettingsPage />)} />
          <Route path="users" element={guarded("users.manage", <UsersPage />)} />
          <Route path="audit-log" element={guarded("audit.read", <AuditLogPage />)} />
          <Route path="account" element={<AccountPage />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Route>
      </Routes>
    </NotificationProvider>
  );
}
