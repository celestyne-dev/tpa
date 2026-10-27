"""Admin API for products, files, categories, collections, orders, refunds, customers,
entitlements, downloads, revenue reports and payment settings.

Each resource checks its permission with a decorator; services re-check the
specific permission for each field or action (e.g. prices need
``products.manage_prices`` even inside a product update).
"""

from __future__ import annotations

from flask import Response, current_app, request
from flask_jwt_extended import current_user
from flask_restful import Resource
from sqlalchemy import select

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import PaymentEvent, ProductCategory, ProductCollection
from ...payments import config as payment_config
from ...services import audit_service
from ...services.commerce import (
    catalogue,
    customers,
    order_admin,
    payments,
    premium_files,
    product_admin,
    product_files,
)
from ...services.commerce import entitlements as ent_service
from ...services.commerce.checkout import cancel_unpaid
from ...utils.errors import NotFoundError, ValidationError
from ...utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _page_args() -> dict:
    def to_int(name, default, low, high):
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValidationError(details={name: ["Must be a number."]}) from None
        return max(low, min(high, value))

    args = {
        k: v for k, v in request.args.items() if k not in ("page", "page_size") and len(v) <= 120
    }
    args["page"] = to_int("page", 1, 1, 10000)
    args["page_size"] = to_int("page_size", 25, 1, 100)
    for key in ("customer_id", "product_id"):
        if key in args:
            try:
                args[key] = int(args[key])
            except ValueError:
                raise ValidationError(details={key: ["Must be a number."]}) from None
    return args


def _csv(body: str, filename: str) -> Response:
    response = Response(body, mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---- products ---------------------------------------------------------------------------


class ProductListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self):
        args = {
            k: request.args.get(k) for k in ("status", "type", "q", "issues", "group", "access")
        }
        items = product_admin.list_products({k: v for k, v in args.items() if v})
        return success(items, {"total": len(items), "can": product_admin.can(current_user)})

    @require_permission(P.PRODUCTS_CREATE)
    def post(self):
        product = product_admin.create(_body(), current_user)
        db.session.commit()
        return success(product_admin.detail(product, current_user), status=201)


class ProductOptionsResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self):
        return success(product_admin.options())


class ProductResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, product_id: int):
        return success(product_admin.detail(product_admin.get_product(product_id), current_user))

    @require_any_permission(P.PRODUCTS_EDIT, P.PRODUCTS_PUBLISH, P.PRODUCTS_MANAGE_PRICES)
    def patch(self, product_id: int):
        product = product_admin.update(product_admin.get_product(product_id), _body(), current_user)
        db.session.commit()
        return success(product_admin.detail(product, current_user))


def _action(permission: P, func_name: str):
    class _ActionResource(Resource):
        @require_permission(permission)
        def post(self, product_id: int):
            product = getattr(product_admin, func_name)(
                product_admin.get_product(product_id), current_user
            )
            db.session.commit()
            return success(product_admin.detail(product, current_user))

    _ActionResource.__name__ = f"Product{func_name.title().replace('_', '')}Resource"
    return _ActionResource


ProductPublishResource = _action(P.PRODUCTS_PUBLISH, "publish")
ProductUnpublishResource = _action(P.PRODUCTS_PUBLISH, "unpublish")
ProductArchiveResource = _action(P.PRODUCTS_ARCHIVE, "archive")
ProductRestoreResource = _action(P.PRODUCTS_ARCHIVE, "restore")
ProductDiscardResource = _action(P.PRODUCTS_EDIT, "discard_changes")


class ProductDuplicateResource(Resource):
    @require_permission(P.PRODUCTS_CREATE)
    def post(self, product_id: int):
        copy = product_admin.duplicate(product_admin.get_product(product_id), current_user)
        db.session.commit()
        return success(product_admin.detail(copy, current_user), status=201)


class ProductPreviewResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, product_id: int):
        product = product_admin.get_product(product_id)
        data = catalogue.public_product(product, detail=True, preview=True)
        data["related"] = []
        return success(data)


class ProductRevisionListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, product_id: int):
        return success(product_admin.revisions(product_admin.get_product(product_id)))


class ProductRevisionRestoreResource(Resource):
    @require_permission(P.PRODUCTS_EDIT)
    def post(self, product_id: int, revision_id: int):
        product = product_admin.restore_revision(
            product_admin.get_product(product_id), revision_id, current_user
        )
        db.session.commit()
        return success(product_admin.detail(product, current_user))


class ProductPriceListResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_PRICES)
    def post(self, product_id: int):
        product = product_admin.get_product(product_id)
        product_admin.set_price(product, _body(), current_user)
        db.session.commit()
        return success(product_admin.detail(product, current_user), status=201)


class ProductPriceResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_PRICES)
    def delete(self, product_id: int, price_id: int):
        product = product_admin.get_product(product_id)
        product_admin.delete_price(product, price_id, current_user)
        db.session.commit()
        return success(product_admin.detail(product, current_user))


class ProductBundleItemsResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_BUNDLES)
    def put(self, product_id: int):
        product = product_admin.set_bundle_items(
            product_admin.get_product(product_id), _body().get("product_ids"), current_user
        )
        db.session.commit()
        return success(product_admin.detail(product, current_user))


class ProductFileListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, product_id: int):
        product = product_admin.get_product(product_id)
        return success(
            {
                "files": [product_files.file_dict(f) for f in product.files],
                "scanner_configured": product_files.scanner_configured(),
                "max_mb": current_app.config["PRODUCT_FILE_MAX_MB"],
            }
        )

    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def post(self, product_id: int):
        product = product_admin.get_product(product_id)
        file = product_files.upload(
            product,
            request.files.get("file"),
            current_user,
            title=request.form.get("title"),
            description=request.form.get("description"),
            notes=request.form.get("notes"),
        )
        db.session.commit()
        return success(product_files.file_dict(file), status=201)


class ProductFileResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def patch(self, product_id: int, file_id: int):
        product = product_admin.get_product(product_id)
        file = product_files.update_file(
            product, product_files.get_file(product, file_id), _body(), current_user
        )
        db.session.commit()
        return success(product_files.file_dict(file))


class ProductFileVersionListResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def post(self, product_id: int, file_id: int):
        product = product_admin.get_product(product_id)
        file = product_files.upload(
            product,
            request.files.get("file"),
            current_user,
            title=None,
            description=None,
            file=product_files.get_file(product, file_id),
            notes=request.form.get("notes"),
        )
        db.session.commit()
        return success(product_files.file_dict(file), status=201)


class ProductFileDownloadResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def get(self, product_id: int, file_id: int, version_id: int):
        product = product_admin.get_product(product_id)
        return product_files.stream_version_for_admin(
            product, product_files.get_file(product, file_id), version_id, current_user
        )


# ---- categories and collections ---------------------------------------------------------


class ProductCategoryListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self):
        return success([product_admin.category_dict(c) for c in product_admin._all_categories()])

    @require_permission(P.PRODUCTS_EDIT)
    def post(self):
        category = product_admin.save_category(_body(), current_user)
        db.session.commit()
        return success(product_admin.category_dict(category), status=201)


def _category(category_id: int) -> ProductCategory:
    category = db.session.get(ProductCategory, category_id)
    if category is None:
        raise NotFoundError("Category not found.")
    return category


class ProductCategoryResource(Resource):
    @require_permission(P.PRODUCTS_EDIT)
    def patch(self, category_id: int):
        category = product_admin.save_category(_body(), current_user, _category(category_id))
        db.session.commit()
        return success(product_admin.category_dict(category))

    @require_permission(P.PRODUCTS_EDIT)
    def delete(self, category_id: int):
        product_admin.delete_category(_category(category_id), current_user)
        db.session.commit()
        return success({"deleted": True})


def _collection(collection_id: int) -> ProductCollection:
    collection = db.session.get(ProductCollection, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


class ProductCollectionListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self):
        rows = db.session.scalars(
            select(ProductCollection).order_by(ProductCollection.sort_order, ProductCollection.name)
        )
        return success([product_admin.collection_dict(c) for c in rows])

    @require_permission(P.PRODUCTS_EDIT)
    def post(self):
        collection = product_admin.save_collection(_body(), current_user)
        db.session.commit()
        return success(product_admin.collection_dict(collection), status=201)


class ProductCollectionResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, collection_id: int):
        return success(product_admin.collection_dict(_collection(collection_id)))

    @require_permission(P.PRODUCTS_EDIT)
    def patch(self, collection_id: int):
        collection = product_admin.save_collection(
            _body(), current_user, _collection(collection_id)
        )
        db.session.commit()
        return success(product_admin.collection_dict(collection))

    @require_permission(P.PRODUCTS_EDIT)
    def delete(self, collection_id: int):
        product_admin.delete_collection(_collection(collection_id), current_user)
        db.session.commit()
        return success({"deleted": True})


# ---- orders and refunds -----------------------------------------------------------------


class OrderListResource(Resource):
    @require_permission(P.ORDERS_VIEW)
    def get(self):
        items, total = order_admin.list_orders(_page_args())
        return success(items, {"total": total})


class OrderExportResource(Resource):
    @require_permission(P.ORDERS_EXPORT)
    def get(self):
        body = order_admin.export_orders_csv(_page_args())
        audit_service.record("orders.exported", "order", actor=current_user)
        db.session.commit()
        return _csv(body, "orders.csv")


class OrderResource(Resource):
    @require_permission(P.ORDERS_VIEW)
    def get(self, order_id: int):
        return success(order_admin.order_detail(order_admin.get_order(order_id), current_user))


class OrderVerifyResource(Resource):
    @require_permission(P.ORDERS_MANAGE)
    def post(self, order_id: int):
        order = order_admin.get_order(order_id)
        outcome = payments.verify_order(order, "staff")
        audit_service.record(
            "order.payment_rechecked",
            "order",
            order.id,
            actor=current_user,
            details={"outcome": outcome},
        )
        db.session.commit()
        return success({"outcome": outcome, "order": order_admin.order_detail(order, current_user)})


class OrderCancelResource(Resource):
    @require_permission(P.ORDERS_MANAGE)
    def post(self, order_id: int):
        order = cancel_unpaid(order_admin.get_order(order_id), "staff", current_user)
        db.session.commit()
        return success(order_admin.order_detail(order, current_user))


class OrderReceiptResource(Resource):
    @require_permission(P.ORDERS_MANAGE)
    def post(self, order_id: int):
        order = order_admin.get_order(order_id)
        status = payments.resend_receipt(order, current_user)
        db.session.commit()
        return success({"delivery": status})


class OrderNoteResource(Resource):
    @require_permission(P.ORDERS_MANAGE)
    def post(self, order_id: int):
        order = order_admin.add_note(
            order_admin.get_order(order_id), _body().get("note"), current_user
        )
        db.session.commit()
        return success(order_admin.order_detail(order, current_user))


class OrderRefundListResource(Resource):
    @require_permission(P.REFUNDS_ISSUE)
    def post(self, order_id: int):
        order = order_admin.get_order(order_id)
        refund = payments.request_refund(order, _body(), current_user)
        db.session.commit()
        return success(
            {
                "refund": payments.refund_dict(refund),
                "order": order_admin.order_detail(order, current_user),
            },
            status=201,
        )


class OrderRefundActionResource(Resource):
    @require_permission(P.REFUNDS_ISSUE)
    def post(self, order_id: int, refund_id: int, action: str):
        order = order_admin.get_order(order_id)
        refund = payments.get_refund(order, refund_id)
        if action == "complete":
            payments.complete_manual_refund(refund, _body(), current_user)
        elif action == "check":
            payments.check_refund(refund, current_user)
        elif action == "cancel":
            payments.reject_refund(refund, str(_body().get("reason") or ""), current_user)
        else:
            raise NotFoundError()
        db.session.commit()
        db.session.refresh(order)
        return success(
            {
                "refund": payments.refund_dict(refund),
                "order": order_admin.order_detail(order, current_user),
            }
        )


# ---- customers, entitlements and downloads ----------------------------------------------


class CustomerListResource(Resource):
    @require_permission(P.CUSTOMERS_VIEW)
    def get(self):
        items, total = order_admin.list_customers(_page_args())
        return success(items, {"total": total})


class CustomerResource(Resource):
    @require_permission(P.CUSTOMERS_VIEW)
    def get(self, customer_id: int):
        return success(
            order_admin.customer_detail(order_admin.get_customer(customer_id), current_user)
        )

    @require_any_permission(P.CUSTOMERS_SUPPORT, P.CUSTOMERS_MANAGE)
    def patch(self, customer_id: int):
        customer = order_admin.update_customer(
            order_admin.get_customer(customer_id), _body(), current_user
        )
        db.session.commit()
        return success(order_admin.customer_detail(customer, current_user))


class CustomerSupportActionResource(Resource):
    @require_permission(P.CUSTOMERS_SUPPORT)
    def post(self, customer_id: int, action: str):
        customer = order_admin.get_customer(customer_id)
        if customer.status != "active":
            raise ValidationError(details={"status": ["The account is not active."]})
        if action == "resend-verification":
            status = customers.send_verification(customer)
        elif action == "password-reset":
            status = customers.send_password_reset(customer, reason="staff")
        else:
            raise NotFoundError()
        audit_service.record(
            f"customer.{action.replace('-', '_')}_sent",
            "customer",
            customer.id,
            actor=current_user,
            details={"delivery": status},
        )
        db.session.commit()
        return success({"delivery": status})


class CustomerAnonymiseResource(Resource):
    @require_permission(P.CUSTOMERS_MANAGE)
    def post(self, customer_id: int):
        customer = order_admin.get_customer(customer_id)
        if _body().get("confirm") is not True:
            raise ValidationError(details={"confirm": ["Confirm the deletion."]})
        if customer.status == "deleted":
            raise ValidationError(details={"status": ["Already deleted."]})
        customers.anonymise(customer, current_user)
        db.session.commit()
        return success(order_admin.customer_detail(customer, current_user))


class CustomerEntitlementResource(Resource):
    @require_permission(P.ENTITLEMENTS_MANAGE)
    def post(self, customer_id: int):
        customer = order_admin.get_customer(customer_id)
        data = _body()
        product = product_admin.get_product(
            data.get("product_id") if isinstance(data.get("product_id"), int) else 0
        )
        if customer.status != "active":
            raise ValidationError(details={"customer": ["The account is not active."]})
        entitlement = ent_service.grant_manual(
            customer, product, str(data.get("reason") or "").strip(), current_user
        )
        db.session.commit()
        return success(ent_service.entitlement_dict(entitlement), status=201)


class EntitlementListResource(Resource):
    @require_permission(P.ENTITLEMENTS_VIEW)
    def get(self):
        items, total = ent_service.list_entitlements(_page_args())
        return success(items, {"total": total})


class EntitlementActionResource(Resource):
    @require_permission(P.ENTITLEMENTS_MANAGE)
    def post(self, entitlement_id: int, action: str):
        entitlement = ent_service.get_entitlement(entitlement_id)
        reason = str(_body().get("reason") or "").strip()
        if not reason:
            raise ValidationError(details={"reason": ["Give a reason."]})
        if action == "revoke":
            ent_service.revoke(entitlement, reason, current_user)
        elif action == "restore":
            ent_service.restore(entitlement, reason, current_user)
        else:
            raise NotFoundError()
        db.session.commit()
        return success(ent_service.entitlement_dict(entitlement))


class DownloadSummaryResource(Resource):
    @require_permission(P.DOWNLOADS_AUDIT)
    def get(self):
        raw = request.args.get("days", "30")
        days = int(raw) if raw.isdigit() else 30
        return success(order_admin.download_summary(max(1, min(days, 365))))


# ---- premium file library (media library "Premium files") -------------------------------


class PremiumFileListResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self):
        items, summary = premium_files.list_files(dict(request.args))
        return success(items, {"total": len(items), "summary": summary})


class PremiumFileResource(Resource):
    @require_permission(P.PRODUCTS_VIEW)
    def get(self, file_id: int):
        return success(premium_files.file_detail(premium_files.get_file(file_id)))

    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def delete(self, file_id: int):
        keys = premium_files.delete_file(premium_files.get_file(file_id), current_user)
        db.session.commit()
        premium_files.remove_stored(keys)  # only after the records are gone
        return success({"deleted": True})


class PremiumFileVersionResource(Resource):
    @require_permission(P.PRODUCTS_MANAGE_FILES)
    def delete(self, file_id: int, version_id: int):
        file = premium_files.get_file(file_id)
        key = premium_files.delete_version(file, version_id, current_user)
        db.session.commit()
        premium_files.remove_stored([key])
        return success(premium_files.file_detail(premium_files.get_file(file_id)))


class DownloadListResource(Resource):
    @require_permission(P.DOWNLOADS_AUDIT)
    def get(self):
        items, total = order_admin.list_downloads(_page_args())
        return success(items, {"total": total})


# ---- reports and payment settings -------------------------------------------------------


class RevenueReportResource(Resource):
    @require_permission(P.FINANCE_VIEW)
    def get(self):
        return success(order_admin.revenue_report(dict(request.args)))


class RevenueExportResource(Resource):
    @require_permission(P.FINANCE_EXPORT)
    def get(self):
        body = order_admin.export_revenue_csv(dict(request.args))
        audit_service.record("finance.report_exported", "finance", actor=current_user)
        db.session.commit()
        return _csv(body, "revenue.csv")


class PaymentSettingsResource(Resource):
    @require_permission(P.PAYMENTS_CONFIGURE)
    def get(self):
        settings = payment_config.get_settings()
        return success(
            {
                "settings": {k.removeprefix("payments."): v for k, v in settings.items()},
                "provider": payment_config.provider_status(),
                "effective_mode": payment_config.effective_mode(),
                "readiness": payment_config.readiness(),
                "attestations": payment_config.LIVE_ATTESTATIONS,
                "checkout_currencies": payment_config.checkout_currencies(),
            }
        )

    @require_permission(P.PAYMENTS_CONFIGURE)
    def patch(self):
        result = payment_config.update_settings(_body(), current_user)
        db.session.commit()
        return success(result)


class PaymentAttestationResource(Resource):
    @require_permission(P.PAYMENTS_CONFIGURE)
    def put(self):
        result = payment_config.update_attestation(_body(), current_user)
        db.session.commit()
        return success(result)


class PaymentEventListResource(Resource):
    @require_permission(P.PAYMENTS_VIEW_EVENTS)
    def get(self):
        args = _page_args()
        stmt = select(PaymentEvent)
        if args.get("status"):
            stmt = stmt.where(PaymentEvent.status == args["status"])
        rows = db.session.scalars(
            stmt.order_by(PaymentEvent.received_at.desc())
            .offset((args["page"] - 1) * args["page_size"])
            .limit(args["page_size"])
        )
        return success([payments.event_dict(e) for e in rows])


class PaymentEventReprocessResource(Resource):
    @require_permission(P.ORDERS_MANAGE)
    def post(self, event_id: int):
        event = db.session.get(PaymentEvent, event_id)
        if event is None:
            raise NotFoundError("Event not found.")
        if event.status not in ("error", "deferred"):
            raise ValidationError(
                details={"status": ["Only failed or deferred events can be re-processed."]}
            )
        audit_service.record("payment.event_reprocessed", "payments", event.id, actor=current_user)
        db.session.commit()
        result = payments.process_event(event)
        return success(result)


COMMERCE_ROUTES = [
    (ProductListResource, "/admin/products"),
    (ProductOptionsResource, "/admin/products/options"),
    (ProductResource, "/admin/products/<int:product_id>"),
    (ProductPublishResource, "/admin/products/<int:product_id>/publish"),
    (ProductUnpublishResource, "/admin/products/<int:product_id>/unpublish"),
    (ProductArchiveResource, "/admin/products/<int:product_id>/archive"),
    (ProductRestoreResource, "/admin/products/<int:product_id>/restore"),
    (ProductDiscardResource, "/admin/products/<int:product_id>/discard"),
    (ProductDuplicateResource, "/admin/products/<int:product_id>/duplicate"),
    (ProductPreviewResource, "/admin/products/<int:product_id>/preview"),
    (ProductRevisionListResource, "/admin/products/<int:product_id>/revisions"),
    (
        ProductRevisionRestoreResource,
        "/admin/products/<int:product_id>/revisions/<int:revision_id>/restore",
    ),
    (ProductPriceListResource, "/admin/products/<int:product_id>/prices"),
    (ProductPriceResource, "/admin/products/<int:product_id>/prices/<int:price_id>"),
    (ProductBundleItemsResource, "/admin/products/<int:product_id>/bundle-items"),
    (ProductFileListResource, "/admin/products/<int:product_id>/files"),
    (ProductFileResource, "/admin/products/<int:product_id>/files/<int:file_id>"),
    (
        ProductFileVersionListResource,
        "/admin/products/<int:product_id>/files/<int:file_id>/versions",
    ),
    (
        ProductFileDownloadResource,
        "/admin/products/<int:product_id>/files/<int:file_id>/versions/<int:version_id>/download",
    ),
    (ProductCategoryListResource, "/admin/product-categories"),
    (ProductCategoryResource, "/admin/product-categories/<int:category_id>"),
    (ProductCollectionListResource, "/admin/product-collections"),
    (ProductCollectionResource, "/admin/product-collections/<int:collection_id>"),
    (OrderListResource, "/admin/orders"),
    (OrderExportResource, "/admin/orders/export"),
    (OrderResource, "/admin/orders/<int:order_id>"),
    (OrderVerifyResource, "/admin/orders/<int:order_id>/verify"),
    (OrderCancelResource, "/admin/orders/<int:order_id>/cancel"),
    (OrderReceiptResource, "/admin/orders/<int:order_id>/resend-receipt"),
    (OrderNoteResource, "/admin/orders/<int:order_id>/notes"),
    (OrderRefundListResource, "/admin/orders/<int:order_id>/refunds"),
    (
        OrderRefundActionResource,
        "/admin/orders/<int:order_id>/refunds/<int:refund_id>/<string:action>",
    ),
    (CustomerListResource, "/admin/customers"),
    (CustomerResource, "/admin/customers/<int:customer_id>"),
    (CustomerSupportActionResource, "/admin/customers/<int:customer_id>/<string:action>"),
    (CustomerAnonymiseResource, "/admin/customers/<int:customer_id>/anonymise"),
    (CustomerEntitlementResource, "/admin/customers/<int:customer_id>/entitlements"),
    (EntitlementListResource, "/admin/entitlements"),
    (EntitlementActionResource, "/admin/entitlements/<int:entitlement_id>/<string:action>"),
    (DownloadListResource, "/admin/downloads"),
    (DownloadSummaryResource, "/admin/downloads/summary"),
    (PremiumFileListResource, "/admin/premium-files"),
    (PremiumFileResource, "/admin/premium-files/<int:file_id>"),
    (PremiumFileVersionResource, "/admin/premium-files/<int:file_id>/versions/<int:version_id>"),
    (RevenueReportResource, "/admin/reports/revenue"),
    (RevenueExportResource, "/admin/reports/revenue/export"),
    (PaymentSettingsResource, "/admin/payments/settings"),
    (PaymentAttestationResource, "/admin/payments/attestation"),
    (PaymentEventListResource, "/admin/payments/events"),
    (PaymentEventReprocessResource, "/admin/payments/events/<int:event_id>/reprocess"),
]
