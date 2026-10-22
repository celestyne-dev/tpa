import {
  BarChart3,
  BookOpen,
  FileText,
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
} from "lucide-react";

/** Sidebar sections. Items are shown only when the user holds the permission. */
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
      { label: "Articles", to: "/admin/articles", icon: PenSquare, permission: "content.read" },
      { label: "Topics", to: "/admin/topics", icon: FolderTree, permission: "content.read" },
      { label: "Tags", to: "/admin/tags", icon: Tags, permission: "content.read" },
      { label: "Authors", to: "/admin/authors", icon: UserRound, permission: "content.read" },
    ],
  },
  {
    title: "Website",
    items: [
      { label: "Pages", to: "/admin/pages", icon: LayoutTemplate, permission: "pages.read" },
      { label: "Navigation", to: "/admin/navigation", icon: Menu, permission: "navigation.manage" },
      { label: "Settings", to: "/admin/settings", icon: Settings, permission: "settings.manage" },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users", to: "/admin/users", icon: Users, permission: "users.manage" },
      { label: "Audit log", to: "/admin/audit-log", icon: ScrollText, permission: "audit.read" },
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
  { label: "SEO tools", icon: Search },
  { label: "Media library", icon: BookOpen },
  { label: "Licensing", icon: FileText },
];
