from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from main import app, get_session


# Configuración de base de datos SQLite efímera en memoria para testing aislado
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ----------------------------------------------------------------------
# Test: Creación y Asociación de Modelos
# ----------------------------------------------------------------------
def test_crear_y_asociar_autor_libro(client: TestClient):
    res_autor = client.post(
        "/autores", json={"nombre": "Jorge Luis Borges", "nacionalidad": "Argentina"}
    )
    assert res_autor.status_code == 201
    autor_id = res_autor.json()["id"]

    res_libro = client.post(
        "/libros",
        json={"titulo": "Ficciones", "isbn": "978-9500700010", "stock_disponible": 2},
    )
    assert res_libro.status_code == 201
    libro_id = res_libro.json()["id"]

    res_assoc = client.post(f"/libros/{libro_id}/autores/{autor_id}")
    assert res_assoc.status_code == 200


def test_regla_8_email_duplicado(client: TestClient):
    # R8: Email duplicado -> 400 Bad Request
    client.post(
        "/usuarios",
        json={"nombre": "Socio 1", "email": "socio@mail.com", "es_socio": True},
    )
    res_dup = client.post(
        "/usuarios",
        json={"nombre": "Socio 2", "email": "socio@mail.com", "es_socio": True},
    )
    assert res_dup.status_code == 400
    assert "email ya se encuentra registrado" in res_dup.json()["detail"]


def test_regla_3_socio_no_activo(client: TestClient):
    # R3: Socio inactivo -> 403 Forbidden
    res_usr = client.post(
        "/usuarios",
        json={"nombre": "Inactivo", "email": "inactivo@mail.com", "es_socio": False},
    )
    socio_id = res_usr.json()["id"]

    res_lib = client.post(
        "/libros", json={"titulo": "Rayuela", "isbn": "12345", "stock_disponible": 5}
    )
    libro_id = res_lib.json()["id"]

    res_prestamo = client.post(
        "/prestamos", json={"socio_id": socio_id, "libro_id": libro_id}
    )
    assert res_prestamo.status_code == 403


def test_regla_2_sin_stock(client: TestClient):
    # R2: Stock <= 0 -> 400 Bad Request
    res_usr = client.post(
        "/usuarios",
        json={"nombre": "Juan", "email": "juan@mail.com", "es_socio": True},
    )
    socio_id = res_usr.json()["id"]

    res_lib = client.post(
        "/libros", json={"titulo": "Sin Stock", "isbn": "9999", "stock_disponible": 0}
    )
    libro_id = res_lib.json()["id"]

    res_prestamo = client.post(
        "/prestamos", json={"socio_id": socio_id, "libro_id": libro_id}
    )
    assert res_prestamo.status_code == 400
    assert "stock disponible" in res_prestamo.json()["detail"]


def test_regla_1_maximo_tres_prestamos_activos(client: TestClient):
    # R1: Máximo 3 préstamos activos por socio -> 400 Bad Request
    res_usr = client.post(
        "/usuarios",
        json={"nombre": "Marcos", "email": "marcos@mail.com", "es_socio": True},
    )
    socio_id = res_usr.json()["id"]

    libros_ids = []
    for i in range(4):
        r = client.post(
            "/libros",
            json={"titulo": f"Libro {i}", "isbn": f"ISBN-{i}", "stock_disponible": 2},
        )
        libros_ids.append(r.json()["id"])

    for i in range(3):
        res = client.post(
            "/prestamos", json={"socio_id": socio_id, "libro_id": libros_ids[i]}
        )
        assert res.status_code == 201

    res_cuarto = client.post(
        "/prestamos", json={"socio_id": socio_id, "libro_id": libros_ids[3]}
    )
    assert res_cuarto.status_code == 400
    assert "límite de 3 préstamos" in res_cuarto.json()["detail"]


def test_regla_4_y_5_plazo_y_calculo_multa(client: TestClient):
    # R4: Plazo de 14 días. R5: Multa $100/día de retraso
    res_usr = client.post(
        "/usuarios",
        json={"nombre": "Ana", "email": "ana@mail.com", "es_socio": True},
    )
    socio_id = res_usr.json()["id"]

    res_lib = client.post(
        "/libros", json={"titulo": "Don Quijote", "isbn": "777", "stock_disponible": 1}
    )
    libro_id = res_lib.json()["id"]

    hoy = date.today()
    res_p = client.post(
        "/prestamos",
        json={"socio_id": socio_id, "libro_id": libro_id, "fecha_prestamo": str(hoy)},
    )
    assert res_p.status_code == 201
    prestamo_data = res_p.json()
    prestamo_id = prestamo_data["id"]

    fecha_esp = (hoy + timedelta(days=14)).isoformat()
    assert prestamo_data["fecha_devolucion"] == fecha_esp

    fecha_tardia = (hoy + timedelta(days=17)).isoformat()
    res_dev = client.post(
        f"/prestamos/{prestamo_id}/devolucion", json={"fecha_devuelto": fecha_tardia}
    )
    assert res_dev.status_code == 200
    assert res_dev.json()["multa"] == 300.0


def test_regla_6_prestamo_ya_devuelto(client: TestClient):
    # R6: Devolver préstamo ya devuelto -> 400 Bad Request
    res_usr = client.post(
        "/usuarios",
        json={"nombre": "Pedro", "email": "pedro@mail.com", "es_socio": True},
    )
    socio_id = res_usr.json()["id"]

    res_lib = client.post(
        "/libros",
        json={"titulo": "Cien años de soledad", "isbn": "888", "stock_disponible": 1},
    )
    libro_id = res_lib.json()["id"]

    res_p = client.post(
        "/prestamos", json={"socio_id": socio_id, "libro_id": libro_id}
    )
    prestamo_id = res_p.json()["id"]

    client.post(f"/prestamos/{prestamo_id}/devolucion", json={})

    res_re_dev = client.post(f"/prestamos/{prestamo_id}/devolucion", json={})
    assert res_re_dev.status_code == 400
    assert "ya ha sido devuelto" in res_re_dev.json()["detail"]


def test_regla_7_recurso_no_encontrado(client: TestClient):
    # R7: 404 Not Found
    res = client.get("/libros/99999")
    assert res.status_code == 404
