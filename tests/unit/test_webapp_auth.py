from webapp import create_app


def test_login_is_required(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "secret",
            "SECRET_KEY": "test-secret",
            "PROJECT_ROOT": tmp_path,
            "SRC_DIR": tmp_path / "src",
            "UPLOAD_TMP_DIR": tmp_path / ".webapp_uploads",
        }
    )
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_then_access_dashboard(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        (
            "prepare-java-bytecode:\n"
            "\t@# Prepare Java bytecode before collection.\n"
            "\t@echo prep\n\n"
            "collect-loc-cloc:\n"
            "\t@# Run a software metric collector.\n"
            "\t@echo loc\n\n"
            "collect-vulnerability-pmd-security:\n"
            "\t@# Run a vulnerability collector.\n"
            "\t@echo vuln\n\n"
            "clean:\n"
            "\t@# Remove generated outputs.\n"
            "\t@echo clean\n"
        ),
        encoding="utf-8",
    )
    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "secret",
            "SECRET_KEY": "test-secret",
            "PROJECT_ROOT": tmp_path,
            "MAKEFILE_PATH": makefile_path,
            "SRC_DIR": tmp_path / "src",
            "UPLOAD_TMP_DIR": tmp_path / ".webapp_uploads",
        }
    )
    client = app.test_client()

    login_page = client.get("/login")
    html = login_page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    token = html.split(marker, 1)[1].split('"', 1)[0]

    response = client.post(
        "/login",
        data={
            "username": "swadmin",
            "password": "secret",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Run Makefile Commands" in html
    assert "Remove generated outputs." in html
    assert "Preparation" in html
    assert "Software Metrics" in html
    assert "Vulnerabilities" in html
    assert "Vulnerability Metrics" in html
    assert "Selection Queue" in html
    assert "Queue Selected" in html
    assert "No commands selected yet." in html
    assert "Queue Selected Targets" not in html
