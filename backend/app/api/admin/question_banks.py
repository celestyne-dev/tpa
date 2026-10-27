"""Admin API for reusable question banks (/api/v1/admin/question-banks…, Batch 09.2
phase 2).

Every resource requires ``question_banks.view``; changes also need
``question_banks.manage`` (checked in the service), and only that permission sees answer
keys and explanations.
"""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...services.courses import question_banks as banks
from ...utils.errors import ValidationError
from ...utils.responses import success

VIEW = require_permission(P.QUESTION_BANKS_VIEW)


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _args() -> dict:
    return {k: v for k, v in request.args.items() if len(v) <= 120}


class QuestionBankListResource(Resource):
    @VIEW
    def get(self):
        items, meta = banks.list_banks(current_user, _args())
        return success(items, meta)

    @VIEW
    def post(self):
        bank = banks.create_bank(_body(), current_user)
        db.session.commit()
        return success(banks.bank_detail(bank, current_user), status=201)


class QuestionBankResource(Resource):
    @VIEW
    def get(self, bank_id: str):
        return success(banks.bank_detail(banks.get_bank(bank_id), current_user))

    @VIEW
    def patch(self, bank_id: str):
        bank = banks.update_bank(banks.get_bank(bank_id), _body(), current_user)
        db.session.commit()
        return success(banks.bank_detail(bank, current_user))

    @VIEW
    def delete(self, bank_id: str):
        banks.delete_bank(banks.get_bank(bank_id), current_user)
        db.session.commit()
        return success({"deleted": True})


class BankQuestionListResource(Resource):
    @VIEW
    def get(self, bank_id: str):
        items, meta = banks.list_questions(banks.get_bank(bank_id), current_user, _args())
        return success(items, meta)

    @VIEW
    def post(self, bank_id: str):
        question = banks.save_bank_question(banks.get_bank(bank_id), _body(), current_user)
        db.session.commit()
        return success(banks.bank_question_dict(question, with_key=True), status=201)


class BankQuestionResource(Resource):
    @VIEW
    def patch(self, bank_id: str, question_id: str):
        bank = banks.get_bank(bank_id)
        question = banks.save_bank_question(
            bank, _body(), current_user, banks.get_bank_question(bank, question_id)
        )
        db.session.commit()
        return success(banks.bank_question_dict(question, with_key=True))

    @VIEW
    def delete(self, bank_id: str, question_id: str):
        bank = banks.get_bank(bank_id)
        banks.delete_bank_question(bank, banks.get_bank_question(bank, question_id), current_user)
        db.session.commit()
        return success({"deleted": True})


QUESTION_BANK_ROUTES = [
    (QuestionBankListResource, "/admin/question-banks"),
    (QuestionBankResource, "/admin/question-banks/<string:bank_id>"),
    (BankQuestionListResource, "/admin/question-banks/<string:bank_id>/questions"),
    (
        BankQuestionResource,
        "/admin/question-banks/<string:bank_id>/questions/<string:question_id>",
    ),
]
