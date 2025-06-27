from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List, Optional

# Configuración de la base de datos
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

app = FastAPI(title="Tommy Jeans API", version="1.0.0")

# Modelos de datos
class PersonaCreate(BaseModel):
    dni: str
    nombre: str
    apellido: str
    email: Optional[str] = None

class PersonaResponse(BaseModel):
    id: int
    dni: str
    nombre: str
    apellido: str
    email: Optional[str] = None

# Función para obtener conexión a la BD
def get_db_connection():
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        return connection
    except psycopg2.Error as e:
        print(f"Error conectando a la base de datos: {e}")
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

# Inicializar la tabla (ejecutar una sola vez)
def init_database():
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Crear tabla si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                id SERIAL PRIMARY KEY,
                dni VARCHAR(20) UNIQUE NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                apellido VARCHAR(100) NOT NULL,
                email VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
        print("Tabla 'personas' creada exitosamente")
    except psycopg2.Error as e:
        print(f"Error creando tabla: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

# Endpoints del Web Service

@app.get("/")
def read_root():
    return {"message": "Bienvenido al Web Service de Tommy Jeans"}

@app.get("/health")
def health_check():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT version()')
        db_version = cursor.fetchone()
        cursor.close()
        connection.close()
        return {
            "status": "healthy",
            "database": "connected",
            "db_version": db_version[0] if db_version else "unknown"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.post("/personas", response_model=PersonaResponse)
def crear_persona(persona: PersonaCreate):
    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            INSERT INTO personas (dni, nombre, apellido, email)
            VALUES (%s, %s, %s, %s)
            RETURNING id, dni, nombre, apellido, email
        """, (persona.dni, persona.nombre, persona.apellido, persona.email))
        
        nueva_persona = cursor.fetchone()
        connection.commit()
        return PersonaResponse(**nueva_persona)
    
    except psycopg2.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=400, detail="DNI ya existe")
    except psycopg2.Error as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    finally:
        cursor.close()
        connection.close()

@app.get("/personas", response_model=List[PersonaResponse])
def listar_personas():
    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT id, dni, nombre, apellido, email FROM personas ORDER BY id")
        personas = cursor.fetchall()
        return [PersonaResponse(**persona) for persona in personas]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    finally:
        cursor.close()
        connection.close()

@app.get("/personas/{dni}", response_model=PersonaResponse)
def obtener_persona_por_dni(dni: str):
    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute(
            "SELECT id, dni, nombre, apellido, email FROM personas WHERE dni = %s",
            (dni,)
        )
        persona = cursor.fetchone()
        
        if not persona:
            raise HTTPException(status_code=404, detail="Persona no encontrada")
        
        return PersonaResponse(**persona)
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    finally:
        cursor.close()
        connection.close()

@app.put("/personas/{dni}", response_model=PersonaResponse)
def actualizar_persona(dni: str, persona: PersonaCreate):
    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            UPDATE personas 
            SET nombre = %s, apellido = %s, email = %s
            WHERE dni = %s
            RETURNING id, dni, nombre, apellido, email
        """, (persona.nombre, persona.apellido, persona.email, dni))
        
        persona_actualizada = cursor.fetchone()
        
        if not persona_actualizada:
            raise HTTPException(status_code=404, detail="Persona no encontrada")
        
        connection.commit()
        return PersonaResponse(**persona_actualizada)
    except psycopg2.Error as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    finally:
        cursor.close()
        connection.close()

@app.delete("/personas/{dni}")
def eliminar_persona(dni: str):
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM personas WHERE dni = %s", (dni,))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Persona no encontrada")
        
        connection.commit()
        return {"message": f"Persona con DNI {dni} eliminada exitosamente"}
    except psycopg2.Error as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    finally:
        cursor.close()
        connection.close()

# Ejecutar al iniciar la aplicación
@app.on_event("startup")
def startup_event():
    init_database()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)