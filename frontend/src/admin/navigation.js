import {
  BarChart3,
  BookOpen,
  FolderTree,
  GraduationCap,
  Handshake,
  LayoutDashboard,
  LayoutTemplate,
  Link2,
  Mail,
  Megaphone,
  Menu,
  Package,
  PenSquare,
  ScrollText,
  Search,
  Settings,
  ShoppingBag,
  Tags,
  UserRound,
  Users,
  Crown,
  KeyRound,
  Images,
  KanbanSquare,
  Rocket,
  Signpost,
} from "lucide-react";
import {
  ARTICLE_ACCESS,
  REDIRECT_READ,
  ROLE_READ,
  SEO_READ,
  SETTINGS_ACCESS,
  TAXONOMY_READ,
} from "./permissions";

/**
 * Sidebar sections. Items are shown only when the user holds `permission`, or at
 * least one permission of `anyOf`.
 */
export const adminSections = [
  {
    title: "Overview",
    items: [
      {
        label: "Dashboard",
        to: "/admin",
        icon: LayoutDashboard,
        permission: "dashboard.view",
        end: true,
      },
    ],
  },
  {
    title: "Content",
    items: [
      { label: "Articles", to: "/admin/articles", icon: PenSquare, anyOf: ARTICLE_ACCESS },
      { label: "Topics", to: "/admin/topics", icon: FolderTree, anyOf: TAXONOMY_READ },
      { label: "Tags", to: "/admin/tags", icon: Tags, anyOf: TAXONOMY_READ },
      { label: "Authors", to: "/admin/authors", icon: UserRound, anyOf: TAXONOMY_READ },
      { label: "Media Library", to: "/admin/media", icon: Images, permission: "media.view" },
      {
        label: "Editorial Workflow",
        to: "/admin/workflow",
        icon: KanbanSquare,
        anyOf: ARTICLE_ACCESS,
      },
    ],
  },
  {
    title: "Website",
    items: [
      { label: "Pages", to: "/admin/pages", icon: LayoutTemplate, permission: "pages.view" },
      { label: "Navigation", to: "/admin/navigation", icon: Menu, permission: "navigation.manage" },
      { label: "SEO", to: "/admin/seo", icon: Search, anyOf: SEO_READ },
      { label: "Redirects", to: "/admin/redirects", icon: Signpost, anyOf: REDIRECT_READ },
      { label: "Settings", to: "/admin/settings", icon: Settings, anyOf: SETTINGS_ACCESS },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users", to: "/admin/users", icon: Users, permission: "users.view" },
      {
        label: "Roles & Permissions",
        to: "/admin/roles",
        icon: KeyRound,
        anyOf: ROLE_READ,
      },
      {
        label: "Publishing Jobs",
        to: "/admin/publishing",
        icon: Rocket,
        permission: "publishing.view",
      },
      { label: "Audit log", to: "/admin/audit-log", icon: ScrollText, permission: "audit.view" },
    ],
  },
];

/** Business modules scheduled for later batches. Displayed as "Planned", never as links. */
export const plannedModules = [
  { label: "Digital products", icon: Package },
  { label: "Orders", icon: ShoppingBag },
  { label: "Customers", icon: Users },
  { label: "Newsletter", icon: Mail },
  { label: "Partnerships", icon: Handshake },
  { label: "Advertising", icon: Megaphone },
  { label: "Affiliates", icon: Link2 },
  { label: "Courses", icon: GraduationCap },
  { label: "Memberships", icon: Crown },
  { label: "Analytics", icon: BarChart3 },
  { label: "eBooks & licensing", icon: BookOpen },
];
