from otel_canary import matrix
from otel_canary.adapters import ADAPTERS

OTEL_RELEASES = ["1.43.0", "1.44.0", "1.44.1", "1.45.0", "1.46.0rc1", "1.9.0"]


def test_picks_latest_and_the_last_patch_of_the_previous_minor():
    assert matrix.otel_versions(OTEL_RELEASES) == {"previous": "1.44.1", "latest": "1.45.0"}


def test_ignores_pre_releases():
    assert matrix.latest_final(["0.62.3", "0.63.0.dev1", "0.63.0rc1"]) == "0.62.3"


def test_plans_one_cell_per_adapter_transport_and_label():
    sdk_versions = {name: "1.0.0" for name in ADAPTERS}
    cells = matrix.plan(otel={"previous": "1.44.0", "latest": "1.45.0"}, sdk_versions=sdk_versions)

    expected = sum(len(spec.transports) for spec in ADAPTERS.values()) * len(matrix.LABELS)
    assert len(cells) == expected
    assert len({cell["id"] for cell in cells}) == expected
    phoenix_grpc_latest = next(cell for cell in cells if cell["id"] == "phoenix-grpc-latest")
    assert phoenix_grpc_latest == {
        "id": "phoenix-grpc-latest",
        "adapter": "phoenix",
        "sdk": "arize-phoenix-otel==1.0.0",
        "otel": "1.45.0",
        "label": "latest",
        "transport": "grpc",
    }
