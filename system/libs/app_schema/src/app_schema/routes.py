"""How a route reads its JSON body and answers JSON, checked against the app's route table.

``parse_request_body`` validates the body with the model the table names for
the route and ``model_response`` answers the model the table names, so the
OpenAPI document and the running routes cannot disagree: a route that parses
or answers something the table does not say fails its first request with
``RouteModelsMismatchError``, a programming error, not a 400. An
``ErrorResponse`` is allowed on every route, since every operation's default
response is one.
"""

from typing import TypeVar

from app_manifest.manifest import describe_validation_error
from flask import Response, current_app, jsonify, request
from pydantic import BaseModel, ValidationError

from app_schema.api_schema import (
    EXTENSION_KEY,
    ErrorResponse,
    RouteModels,
    RouteTable,
    flask_rule_to_openapi_path,
)
from app_schema.errors import InvalidRequestBodyError, RouteModelsMismatchError

_RequestModel = TypeVar("_RequestModel", bound=BaseModel)


def registered_route_table() -> RouteTable | None:
    """The route table ``register_api_schema_route`` kept on the current app, or None when it registered none."""
    return current_app.extensions.get(EXTENSION_KEY)


def _current_route_key() -> tuple[str, str]:
    assert request.url_rule is not None, "no route matched this request"
    return request.method, flask_rule_to_openapi_path(request.url_rule.rule)


def _route_models_or_raise() -> RouteModels | None:
    """The current route's ``RouteModels``; None when the app keeps no table; a route the table leaves out or
    declares schemaless is a mismatch."""
    table = registered_route_table()
    if table is None:
        return None
    key = _current_route_key()
    entry = table.get(key)
    if not isinstance(entry, RouteModels):
        raise RouteModelsMismatchError(
            f"{key[0]} {key[1]} exchanges JSON but the route table "
            + ("declares it schemaless" if entry is not None else "does not list it")
        )
    return entry


def parse_request_body(model: type[_RequestModel]) -> _RequestModel:
    """The current request's body as ``model``, which the route table must name as the route's request model.

    A body that is not a JSON object or not the model's shape raises
    ``InvalidRequestBodyError``, answered as a 400 by the handler
    ``register_api_schema_route`` installed.
    """
    entry = _route_models_or_raise()
    if entry is not None and not _is_parse_named(entry, model):
        method, path = _current_route_key()
        raise RouteModelsMismatchError(
            f"{method} {path} parses its body as {model.__name__}, but the route table names "
            f"{entry.request_model.__name__ if entry.request_model is not None else 'no request model'}"
        )
    # force=True: a script and curl alike may post without a JSON content type.
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        raise InvalidRequestBodyError("the request body must be a JSON object")
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise InvalidRequestBodyError(describe_validation_error(e)) from e


def _is_answer_named(entry: RouteModels, model: type[BaseModel], status: int) -> bool:
    if entry.response_model is model and entry.success_status == status:
        return True
    return any(
        alternate.model is model and alternate.status == status
        for alternate in entry.alternate_responses
    )


def _is_parse_named(entry: RouteModels, model: type[BaseModel]) -> bool:
    return entry.request_model is model and not entry.is_body_parsed_by_view


def model_response(model: BaseModel, status: int = 200) -> Response:
    """``model`` as the JSON answer under ``status``; the route table must name that model and status for the route.

    An ``ErrorResponse`` needs no entry: it is every operation's default response.
    """
    if not isinstance(model, ErrorResponse):
        entry = _route_models_or_raise()
        if entry is not None and not _is_answer_named(entry, type(model), status):
            method, path = _current_route_key()
            raise RouteModelsMismatchError(
                f"{method} {path} answers {type(model).__name__} under {status}, which the route table does not name"
            )
    response = jsonify(model.model_dump(mode="json"))
    response.status_code = status
    return response


def error_response(detail: str, status: int) -> Response:
    """A refusal or a failure as the ``ErrorResponse`` every route answers them with."""
    return model_response(ErrorResponse(detail=detail), status)
