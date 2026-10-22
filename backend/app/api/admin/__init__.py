"""Admin API (/api/v1/admin). Every resource enforces authentication and permissions."""

from . import auth, content, site

ADMIN_ROUTES = [
    (auth.LoginResource, "/admin/auth/login"),
    (auth.RefreshResource, "/admin/auth/refresh"),
    (auth.LogoutResource, "/admin/auth/logout"),
    (auth.MeResource, "/admin/auth/me"),
    (auth.ChangePasswordResource, "/admin/auth/change-password"),
    (site.DashboardResource, "/admin/dashboard"),
    (content.ArticleListResource, "/admin/articles"),
    (content.ArticleResource, "/admin/articles/<int:article_id>"),
    (content.ArticlePublishResource, "/admin/articles/<int:article_id>/publish"),
    (content.ArticleUnpublishResource, "/admin/articles/<int:article_id>/unpublish"),
    (content.ArticleArchiveResource, "/admin/articles/<int:article_id>/archive"),
    (content.ArticleRestoreResource, "/admin/articles/<int:article_id>/restore"),
    (content.ArticlePreviewResource, "/admin/articles/<int:article_id>/preview"),
    (content.TopicListResource, "/admin/topics"),
    (content.TopicResource, "/admin/topics/<int:item_id>"),
    (content.TopicReassignResource, "/admin/topics/<int:item_id>/reassign"),
    (content.AuthorListResource, "/admin/authors"),
    (content.AuthorResource, "/admin/authors/<int:item_id>"),
    (content.AuthorReassignResource, "/admin/authors/<int:item_id>/reassign"),
    (content.TagListResource, "/admin/tags"),
    (content.TagResource, "/admin/tags/<int:item_id>"),
    (content.MediaListResource, "/admin/media"),
    (content.PublishingStatusResource, "/admin/publishing/status"),
    (site.PageListResource, "/admin/pages"),
    (site.PageResource, "/admin/pages/<int:page_id>"),
    (site.PageSectionListResource, "/admin/pages/<int:page_id>/sections"),
    (site.PageSectionResource, "/admin/pages/<int:page_id>/sections/<int:section_id>"),
    (site.PageSectionOrderResource, "/admin/pages/<int:page_id>/sections/order"),
    (site.SectionTypesResource, "/admin/section-types"),
    (site.NavigationResource, "/admin/navigation"),
    (site.NavigationMenuResource, "/admin/navigation/<string:menu_key>"),
    (site.SettingsResource, "/admin/settings"),
    (site.UserListResource, "/admin/users"),
    (site.UserResource, "/admin/users/<int:user_id>"),
    (site.UserPasswordResource, "/admin/users/<int:user_id>/password"),
    (site.RoleListResource, "/admin/roles"),
    (site.AuditLogResource, "/admin/audit-log"),
]

# Endpoints reachable without an access token (they authenticate in other ways).
PUBLIC_ADMIN_PATHS = {"/admin/auth/login", "/admin/auth/refresh", "/admin/auth/logout"}
