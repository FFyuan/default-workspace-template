"""What an app's own tests assert about the document it serves (``app_schema.api_schema``)."""

from pathlib import Path

from app_manifest.manifest import load_manifest
from flask.testing import FlaskClient
from openapi_spec_validator import validate

from app_schema.api_schema import API_SCHEMA_ENDPOINT, flask_rule_to_openapi_path


def assert_api_schema_describes_app(client: FlaskClient, manifest_path: Path) -> None:
    """The app answers its manifest's ``api_schema_path`` with a valid document that covers every route.

    The document's title and description are the manifest's ``display_name``
    and ``description``, and every rule of the app's url map except the static
    route and the schema route itself appears among its paths.
    """
    manifest = load_manifest(manifest_path)
    assert manifest.api_schema_path is not None, (
        f"{manifest_path} declares no api_schema_path"
    )
    assert manifest.description is not None, f"{manifest_path} declares no description"
    response = client.get(str(manifest.api_schema_path))
    assert response.status_code == 200, response.data
    document = response.get_json()
    assert isinstance(document, dict)
    validate(document)
    assert document["info"]["title"] == manifest.display_name
    assert document["info"]["description"] == manifest.description
    expected_paths = {
        flask_rule_to_openapi_path(rule.rule)
        for rule in client.application.url_map.iter_rules()
        if rule.endpoint != "static" and rule.endpoint.rsplit(".", 1)[-1] != API_SCHEMA_ENDPOINT
    }
    assert set(document["paths"]) == expected_paths
