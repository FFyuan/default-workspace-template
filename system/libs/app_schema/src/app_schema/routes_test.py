import pytest
from flask import Flask, Response
from pydantic import BaseModel

from app_schema.api_schema import (
    AlternateResponse,
    RouteModels,
    SchemalessRoute,
    register_api_schema_route,
)
from app_schema.errors import RouteModelsMismatchError
from app_schema.routes import error_response, model_response, parse_request_body


class Greeting(BaseModel):
    name: str


class Greeted(BaseModel):
    text: str


class Queued(BaseModel):
    position: int


def _greeter(route_table: dict) -> Flask:
    app = Flask("greeter", static_folder=None)
    app.config["PROPAGATE_EXCEPTIONS"] = True

    @app.post("/greet")
    def greet() -> Response:
        """Greet by name."""
        body = parse_request_body(Greeting)
        if body.name == "later":
            return model_response(Queued(position=3), 202)
        if body.name == "nobody":
            return error_response("nobody to greet", 404)
        return model_response(Greeted(text=f"hello {body.name}"))

    @app.get("/page")
    def page() -> Response:
        """A page that wrongly answers a model."""
        return model_response(Greeted(text="page"))

    register_api_schema_route(
        app,
        "/api/schema",
        title="Greeter",
        description="Greets.",
        route_table=route_table,
    )
    return app


_TABLE = {
    ("POST", "/greet"): RouteModels(
        request_model=Greeting,
        response_model=Greeted,
        alternate_responses=(AlternateResponse(status=202, model=Queued),),
    ),
    ("GET", "/page"): SchemalessRoute(reason="a page"),
}


def test_a_route_parses_and_answers_the_models_its_table_names() -> None:
    client = _greeter(_TABLE).test_client()

    assert client.post("/greet", json={"name": "Kim"}).get_json() == {
        "text": "hello Kim"
    }
    queued = client.post("/greet", json={"name": "later"})
    assert (queued.status_code, queued.get_json()) == (202, {"position": 3})
    refused = client.post("/greet", json={"name": "nobody"})
    assert (refused.status_code, refused.get_json()) == (
        404,
        {"detail": "nobody to greet"},
    )


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ("[1, 2]", "the request body must be a JSON object"),
        ('{"title": "x"}', "field 'name': Field required"),
    ],
)
def test_a_body_off_the_model_is_a_400_naming_the_problem(
    body: str, detail: str
) -> None:
    client = _greeter(_TABLE).test_client()

    response = client.post("/greet", data=body, content_type="application/json")

    assert (response.status_code, response.get_json()) == (400, {"detail": detail})


def test_a_parse_the_table_does_not_name_fails_the_request() -> None:
    table = {
        **_TABLE,
        ("POST", "/greet"): RouteModels(request_model=Greeted, response_model=Greeted),
    }
    client = _greeter(table).test_client()

    with pytest.raises(
        RouteModelsMismatchError,
        match="parses its body as Greeting, but the route table names Greeted",
    ):
        client.post("/greet", json={"name": "Kim"})


def test_an_answer_the_table_does_not_name_fails_the_request() -> None:
    table = {
        **_TABLE,
        ("POST", "/greet"): RouteModels(request_model=Greeting, response_model=Greeted),
    }
    client = _greeter(table).test_client()

    with pytest.raises(RouteModelsMismatchError, match="answers Queued under 202"):
        client.post("/greet", json={"name": "later"})


def test_a_schemaless_route_may_not_answer_a_model() -> None:
    client = _greeter(_TABLE).test_client()

    with pytest.raises(RouteModelsMismatchError, match="declares it schemaless"):
        client.get("/page")


def test_a_route_the_table_leaves_out_may_not_answer_a_model() -> None:
    client = _greeter(
        {key: entry for key, entry in _TABLE.items() if key[1] != "/page"}
    ).test_client()

    with pytest.raises(RouteModelsMismatchError, match="does not list it"):
        client.get("/page")
