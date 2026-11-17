from datetime import date, timedelta
from typing import Generator, List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import EmailStr
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

# ----------------------------------------------------------------------
# DATABASE CONFIGURATION
# ----------------------------------------------------------------------
sqlite_file_name = "biblioteca.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(
    sqlite_url, connect_args={"check_same_thread": False}, echo=False
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


# ----------------------------------------------------------------------
# MODELS & DTOs
# ----------------------------------------------------------------------
class LibroAutor(SQLModel, table=True):
    libro_id: Optional[int] = Field(
        default=None, foreign_key="libro.id", primary_key=True
    )
    autor_id: Optional[int] = Field(
        default=None, foreign_key="autor.id", primary_key=True
    )
    es_autor_principal: bool = Field(default=True)


class AutorBase(SQLModel):
    nombre: str
    nacionalidad: str


class Autor(AutorBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    libros: List["Libro"] = Relationship(
        back_populates="autores", link_model=LibroAutor
    )


class AutorCreate(AutorBase):
    pass


class AutorRead(AutorBase):
    id: int


class AutorUpdate(SQLModel):
    nombre: Optional[str] = None
    nacionalidad: Optional[str] = None


class LibroBase(SQLModel):
    titulo: str
    isbn: str = Field(index=True, unique=True)
    stock_disponible: int = Field(default=1, ge=0)


class Libro(LibroBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    autores: List[Autor] = Relationship(
        back_populates="libros", link_model=LibroAutor
    )


class LibroCreate(LibroBase):
    pass


class LibroRead(LibroBase):
    id: int


class LibroUpdate(SQLModel):
    titulo: Optional[str] = None
    isbn: Optional[str] = None
    stock_disponible: Optional[int] = None


class UsuarioBase(SQLModel):
    nombre: str
    email: EmailStr = Field(index=True, unique=True)
    es_socio: bool = Field(default=True)


class Usuario(UsuarioBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    prestamos: List["Prestamo"] = Relationship(back_populates="socio")


class UsuarioCreate(UsuarioBase):
    pass


class UsuarioRead(UsuarioBase):
    id: int


class UsuarioUpdate(SQLModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    es_socio: Optional[bool] = None


class PrestamoBase(SQLModel):
    socio_id: int = Field(foreign_key="usuario.id")
    libro_id: int = Field(foreign_key="libro.id")
    fecha_prestamo: date = Field(default_factory=date.today)
    fecha_devolucion: Optional[date] = None
    fecha_devuelto: Optional[date] = None
    es_renovacion: bool = Field(default=False)
    multa: float = Field(default=0.0)


class Prestamo(PrestamoBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    socio: Optional[Usuario] = Relationship(back_populates="prestamos")
    libro: Optional[Libro] = Relationship()


class PrestamoCreate(SQLModel):
    socio_id: int
    libro_id: int
    fecha_prestamo: Optional[date] = None


class DevolucionRequest(SQLModel):
    fecha_devuelto: Optional[date] = None


class PrestamoRead(PrestamoBase):
    id: int
    fecha_devolucion: date


# ----------------------------------------------------------------------
# FASTAPI APP & ENDPOINTS
# ----------------------------------------------------------------------
app = FastAPI(
    title="Sistema de Biblioteca REST API",
    description="API de catálogo y préstamos con reglas de negocio validadas.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# --- Autores ---
@app.post(
    "/autores", response_model=AutorRead, status_code=status.HTTP_201_CREATED
)
def crear_autor(autor: AutorCreate, session: Session = Depends(get_session)):
    db_autor = Autor.from_orm(autor)
    session.add(db_autor)
    session.commit()
    session.refresh(db_autor)
    return db_autor


@app.get("/autores", response_model=List[AutorRead])
def listar_autores(session: Session = Depends(get_session)):
    return session.exec(select(Autor)).all()


@app.get("/autores/{autor_id}", response_model=AutorRead)
def obtener_autor(autor_id: int, session: Session = Depends(get_session)):
    autor = session.get(Autor, autor_id)
    if not autor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Autor no encontrado"
        )
    return autor


@app.put("/autores/{autor_id}", response_model=AutorRead)
def actualizar_autor(
    autor_id: int,
    autor_data: AutorUpdate,
    session: Session = Depends(get_session),
):
    autor = session.get(Autor, autor_id)
    if not autor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Autor no encontrado"
        )

    data_dict = autor_data.dict(exclude_unset=True)
    for key, value in data_dict.items():
        setattr(autor, key, value)

    session.add(autor)
    session.commit()
    session.refresh(autor)
    return autor


@app.delete("/autores/{autor_id}")
def eliminar_autor(autor_id: int, session: Session = Depends(get_session)):
    autor = session.get(Autor, autor_id)
    if not autor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Autor no encontrado"
        )
    session.delete(autor)
    session.commit()
    return {"mensaje": "Autor eliminado correctamente"}


# --- Libros ---
@app.post(
    "/libros", response_model=LibroRead, status_code=status.HTTP_201_CREATED
)
def crear_libro(libro: LibroCreate, session: Session = Depends(get_session)):
    db_libro = Libro.from_orm(libro)
    session.add(db_libro)
    session.commit()
    session.refresh(db_libro)
    return db_libro


@app.get("/libros", response_model=List[LibroRead])
def listar_libros(session: Session = Depends(get_session)):
    return session.exec(select(Libro)).all()


@app.get("/libros/disponibles", response_model=List[LibroRead])
def listar_libros_disponibles(session: Session = Depends(get_session)):
    return session.exec(select(Libro).where(Libro.stock_disponible > 0)).all()


@app.get("/libros/{libro_id}", response_model=LibroRead)
def obtener_libro(libro_id: int, session: Session = Depends(get_session)):
    libro = session.get(Libro, libro_id)
    if not libro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado"
        )
    return libro


@app.put("/libros/{libro_id}", response_model=LibroRead)
def actualizar_libro(
    libro_id: int,
    libro_data: LibroUpdate,
    session: Session = Depends(get_session),
):
    libro = session.get(Libro, libro_id)
    if not libro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado"
        )

    data_dict = libro_data.dict(exclude_unset=True)
    for key, value in data_dict.items():
        setattr(libro, key, value)

    session.add(libro)
    session.commit()
    session.refresh(libro)
    return libro


@app.delete("/libros/{libro_id}")
def eliminar_libro(libro_id: int, session: Session = Depends(get_session)):
    libro = session.get(Libro, libro_id)
    if not libro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado"
        )
    session.delete(libro)
    session.commit()
    return {"mensaje": "Libro eliminado correctamente"}


@app.post("/libros/{id}/autores/{autor_id}")
def asociar_autor_a_libro(
    id: int,
    autor_id: int,
    es_principal: bool = True,
    session: Session = Depends(get_session),
):
    libro = session.get(Libro, id)
    if not libro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado"
        )

    autor = session.get(Autor, autor_id)
    if not autor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Autor no encontrado"
        )

    link_existente = session.get(LibroAutor, (id, autor_id))
    if link_existente:
        return {"mensaje": "El autor ya está asociado a este libro"}

    link = LibroAutor(
        libro_id=id, autor_id=autor_id, es_autor_principal=es_principal
    )
    session.add(link)
    session.commit()
    return {
        "mensaje": f"Autor '{autor.nombre}' asociado exitosamente al libro '{libro.titulo}'"
    }


# --- Usuarios ---
@app.post(
    "/usuarios", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED
)
def crear_usuario(
    usuario: UsuarioCreate, session: Session = Depends(get_session)
):
    email_existente = session.exec(
        select(Usuario).where(Usuario.email == usuario.email)
    ).first()
    if email_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya se encuentra registrado",
        )

    db_usuario = Usuario.from_orm(usuario)
    session.add(db_usuario)
    session.commit()
    session.refresh(db_usuario)
    return db_usuario


@app.get("/usuarios", response_model=List[UsuarioRead])
def listar_usuarios(session: Session = Depends(get_session)):
    return session.exec(select(Usuario)).all()


@app.get("/usuarios/{usuario_id}", response_model=UsuarioRead)
def obtener_usuario(usuario_id: int, session: Session = Depends(get_session)):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )
    return usuario


@app.put("/usuarios/{usuario_id}", response_model=UsuarioRead)
def actualizar_usuario(
    usuario_id: int,
    usuario_data: UsuarioUpdate,
    session: Session = Depends(get_session),
):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    if usuario_data.email and usuario_data.email != usuario.email:
        email_existente = session.exec(
            select(Usuario).where(Usuario.email == usuario_data.email)
        ).first()
        if email_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya se encuentra registrado",
            )

    data_dict = usuario_data.dict(exclude_unset=True)
    for key, value in data_dict.items():
        setattr(usuario, key, value)

    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


@app.get("/usuarios/{id}/prestamos_activos", response_model=List[PrestamoRead])
def obtener_prestamos_activos_socio(
    id: int, session: Session = Depends(get_session)
):
    usuario = session.get(Usuario, id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    prestamos_activos = session.exec(
        select(Prestamo).where(
            Prestamo.socio_id == id, Prestamo.fecha_devuelto == None
        )
    ).all()
    return prestamos_activos


# --- Prestamos ---
@app.post(
    "/prestamos",
    response_model=PrestamoRead,
    status_code=status.HTTP_201_CREATED,
)
def registrar_prestamo(
    prestamo_in: PrestamoCreate, session: Session = Depends(get_session)
):
    socio = session.get(Usuario, prestamo_in.socio_id)
    if not socio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Socio no encontrado"
        )

    if not socio.es_socio:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no está activo como socio",
        )

    prestamos_activos = session.exec(
        select(Prestamo).where(
            Prestamo.socio_id == prestamo_in.socio_id,
            Prestamo.fecha_devuelto == None,
        )
    ).all()
    if len(prestamos_activos) >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El socio ya cuenta con el límite de 3 préstamos activos",
        )

    libro = session.get(Libro, prestamo_in.libro_id)
    if not libro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado"
        )

    if libro.stock_disponible <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El libro no cuenta con stock disponible",
        )

    f_prestamo = prestamo_in.fecha_prestamo or date.today()
    f_devolucion = f_prestamo + timedelta(days=14)

    libro.stock_disponible -= 1
    session.add(libro)

    nuevo_prestamo = Prestamo(
        socio_id=prestamo_in.socio_id,
        libro_id=prestamo_in.libro_id,
        fecha_prestamo=f_prestamo,
        fecha_devolucion=f_devolucion,
    )
    session.add(nuevo_prestamo)
    session.commit()
    session.refresh(nuevo_prestamo)
    return nuevo_prestamo


@app.post("/prestamos/{id}/devolucion", response_model=PrestamoRead)
def registrar_devolucion(
    id: int,
    payload: DevolucionRequest,
    session: Session = Depends(get_session),
):
    prestamo = session.get(Prestamo, id)
    if not prestamo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Préstamo no encontrado",
        )

    if prestamo.fecha_devuelto is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El préstamo ya ha sido devuelto",
        )

    f_devuelto = payload.fecha_devuelto or date.today()
    prestamo.fecha_devuelto = f_devuelto

    if f_devuelto > prestamo.fecha_devolucion:
        dias_retraso = (f_devuelto - prestamo.fecha_devolucion).days
        prestamo.multa = float(dias_retraso * 100)
    else:
        prestamo.multa = 0.0

    libro = session.get(Libro, prestamo.libro_id)
    if libro:
        libro.stock_disponible += 1
        session.add(libro)

    session.add(prestamo)
    session.commit()
    session.refresh(prestamo)
    return prestamo
