import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ckjm_parser_reads_wmc_column():
    module = load_module(REPO_ROOT / "metrics/complexity/java/cc-ckjm/collect.py")
    raw = "com.example.A 4 1 0 2 3 1 1 1 2 0\ncom.example.B 6 1 0 1 2 1 0 1 1 0"
    assert module.parse_ckjm_wmc_values(raw) == [4.0, 6.0]


def test_ckjm_cc_proxy_from_csv(tmp_path):
    module = load_module(REPO_ROOT / "metrics/complexity/java/cc-ckjm/collect.py")
    csv_path = tmp_path / "class.csv"
    csv_path.write_text(
        "\n".join(
            [
                "class,type,package,wmc,nom",
                "A,A,com.example.core,10,2",
                "B,B,com.example.core,9,3",
                "CTest,CTest,com.example.core.test,100,1",
                "C,C,com.example.util,4,0",
                "D,D,com.example.util,8,4",
                "E,E,com.example.util,not-a-number,2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stats = module.compute_cc_proxy_from_ckjm(str(csv_path))
    # valid classes: A(5.0), B(3.0), D(2.0)
    assert stats["valid_classes"] == 3
    assert stats["cc_proxy_mean"] == 3.333333
    assert stats["cc_proxy_max"] == 5.0
    assert stats["cc_proxy_p95"] == 4.8


def test_ckjm_wmc_nom_totals_from_csv(tmp_path):
    module = load_module(REPO_ROOT / "metrics/complexity/java/cc-ckjm/collect.py")
    csv_path = tmp_path / "class.csv"
    csv_path.write_text(
        "\n".join(
            [
                "class,type,package,wmc,nom",
                "A,A,com.example.core,10,2",
                "B,B,com.example.core,9,3",
                "CTest,CTest,com.example.core.test,100,1",
                "C,C,com.example.util,4,0",
                "D,D,com.example.util,8,4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stats = module.compute_wmc_nom_totals_from_ckjm(str(csv_path))
    # valid non-test classes with NOM>0: A, B, D
    assert stats["wmc"] == 27.0
    assert stats["nom"] == 9.0
    assert stats["valid_classes"] == 3
    assert stats["skipped_nom_zero"] == 1


def test_jdepend_parser_extracts_package_stats():
    module = load_module(REPO_ROOT / "metrics/coupling/java/ce-ca-jdepend/collect.py")
    raw = """
    Package com.example.core
      Ca: 3
      Ce: 5
      A: 0.0 I: 0.625 D: 0.375
    Package com.example.util
      Ca: 1
      Ce: 1
      A: 0.0 I: 0.5 D: 0.5
    """
    parsed = module.parse_jdepend_text(raw)
    assert parsed["com.example.core"]["ca"] == 3
    assert parsed["com.example.core"]["ce"] == 5
    assert parsed["com.example.util"]["i"] == 0.5


def test_jdepend_parser_supports_textui_291_format():
    module = load_module(REPO_ROOT / "metrics/coupling/java/ce-ca-jdepend/collect.py")
    raw = """
    --------------------------------------------------
    - Package: com.acme.core
    --------------------------------------------------
      Ca: 1
      Ce: 2
      A: 0 I: 0.67 D: 0.33
    """
    parsed = module.parse_jdepend_text(raw)
    assert parsed["com.acme.core"]["ca"] == 1
    assert parsed["com.acme.core"]["ce"] == 2
    assert parsed["com.acme.core"]["i"] == 0.67
