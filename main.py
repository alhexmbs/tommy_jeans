from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List, Optional

# Debug: Imprimir variables de entorno al inicio
print("=" * 50)
print("🔍 DEBUG: Variables de Entorno")
print("=" * 50)
print(f"DB_HOST: {repr(os.getenv('DB_HOST'))}")
print(f"DB_NAME: {repr(os.getenv('DB_NAME'))}")
print(f"DB_USER: {repr(os.getenv('DB_USER'))}")
print(f"DB_PASSWORD: {'***' if os.getenv('DB_PASSWORD') else repr(os.getenv('DB_PASSWORD'))}")
print(f"DB_PORT: {repr(os.getenv('DB_PORT'))}")
print(f"PORT: {repr(os.getenv('PORT'))}")
print("=" * 50)

# Función para obtener configuración de BD con validación
def get_db_config():
    """Obtiene y valida la configuración de la base de datos"""
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_port = os.getenv('DB_PORT', '5432')
    
    # Verificar que todas las variables críticas existan
    missing_vars = []
    if not db_host:
        missing_vars.append('DB_HOST')
    if not db_name:
        missing_vars.append('DB_NAME')
    if not db_user:
        missing_vars.append('DB_USER')
    if not db_password:
        missing_vars.append('DB_PASSWORD')
    
    if missing_vars:
        error_msg = f"❌ Variables de entorno faltantes: {', '.join(missing_vars)}"
        print(error_msg)
        raise Exception(error_msg)
    
    config = {
        'host': db_host,
        'database': db_name,
        'user': db_user,
        'password': db_password,
        'port': int(db_port),
        'connect_timeout': 30,
        'sslmode': 'require'  # Importante para RDS
    }
    
    print(f"✅ Configuración de BD preparada: {db_host}:{db_port}/{db_name}")
    return config

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

# Función mejorada para obtener conexión a la BD
def get_db_connection():
    try:
        db_config = get_db_config()
        print(f"🔄 Intentando conectar a: {db_config['host']}:{db_config['port']}")
        connection = psycopg2.connect(**db_config)
        print("✅ Conexión exitosa a la base de datos")
        return connection
    except Exception as e:
        error_msg = f"❌ Error conectando a la base de datos: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

# Inicializar la tabla con mejor manejo de errores
def init_database():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
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
        print("✅ Tabla 'personas' verificada/creada exitosamente")
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        # No lanzar excepción para que la app siga funcionando
        pass

# Endpoints del Web Service

@app.get("/")
def read_root():
    return {"message": "Bienvenido al Web Service de Tommy Jeans"}

@app.get("/debug-env")
def debug_environment():
    """Endpoint temporal para verificar variables de entorno"""
    return {
        "environment_variables": {
            "DB_HOST": os.getenv('DB_HOST', 'NOT_SET'),
            "DB_NAME": os.getenv('DB_NAME', 'NOT_SET'),
            "DB_USER": os.getenv('DB_USER', 'NOT_SET'),
            "DB_PASSWORD": "***SET***" if os.getenv('DB_PASSWORD') else 'NOT_SET',
            "DB_PORT": os.getenv('DB_PORT', 'NOT_SET'),
            "PORT": os.getenv('PORT', 'NOT_SET')
        },
        "status": "Variables loaded successfully" if all([
            os.getenv('DB_HOST'),
            os.getenv('DB_NAME'),
            os.getenv('DB_USER'),
            os.getenv('DB_PASSWORD')
        ]) else "Some variables are missing"
    }

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
            "db_version": db_version[0] if db_version else "unknown",
            "environment": "variables_loaded"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "environment": "check_variables"
        }

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
    print("🚀 Iniciando aplicación Tommy Jeans API...")
    init_database()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🌐 Iniciando servidor en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)